import asyncio
from collections import defaultdict
import datetime
from io import BytesIO

import random
import re
from typing import Dict, List, Optional, Set, Tuple, Union

from loguru import logger

from ..query.mzq.model import MzqBattleResult
from ..query.pcrfans.model import AttackData

from ..database.table import MzqCache, PcrfansCacheData


from ..model import ArenaQueryRecord, FormatSolution


from ..errorclass import (
    AllNoResultError,
    NoFreeCollisionError,
    NotEnoughUnitError,
)

from .tool import (
    get_pic,
    ids_to_str,
    long_id_to_short,
    str_to_ids,
    ids_to_names,
    names_to_ids,
)

from ..constants import CQ_PATTERN, ArenaQueryType, ArenaRecordType
from PIL import Image
from ..pic_recognize import extract_position

from ..database.sqla import arena_sqla, pcr_sqla
from ..query.pcrfans import pcrfans_query
from ..query.mzq import mzq_query
from hoshino.modules.priconne import chara

query_seq = {
    1: [2, 4, 3],  # 全服查询顺序为[B,日,台]
    2: [1, 3, 4],  # B服查询顺序为[全,台,日]
    3: [1, 2, 4],  # 台服查询顺序为[全,B,日]
    4: [1, 3, 2],  # 日服查询顺序为[全,台,B]
}


class CollisionFreeTeamGenerator:
    # 三队笛卡尔：每队只枚举「前若干条高分候选 + 末尾占位」，降低组合数且保留补位分支
    COMBO_PER_TEAM_CAP = 30

    def __init__(self, all_query_records: List[List[ArenaQueryRecord]]):
        self.all_query_records = all_query_records
        self.combinations: List[List[Union[int, float]]] = []
        n_teams = len(all_query_records)
        if n_teams == 2:
            for i, rec1 in enumerate(all_query_records[0]):
                self.combinations.extend(
                    [i, j, rec1.score + rec2.score]
                    for j, rec2 in enumerate(all_query_records[1])
                )
        elif n_teams == 3:
            r0, r1, r2 = (
                all_query_records[0],
                all_query_records[1],
                all_query_records[2],
            )
            ixs0 = self.combo_branch_indices(len(r0), self.COMBO_PER_TEAM_CAP)
            ixs1 = self.combo_branch_indices(len(r1), self.COMBO_PER_TEAM_CAP)
            ixs2 = self.combo_branch_indices(len(r2), self.COMBO_PER_TEAM_CAP)
            for i in ixs0:
                rec1 = r0[i]
                for j in ixs1:
                    rec2 = r1[j]
                    s12 = rec1.score + rec2.score
                    self.combinations.extend([i, j, k, s12 + r2[k].score] for k in ixs2)
        self.combinations.sort(key=lambda x: x[-1], reverse=True)

    @staticmethod
    def combo_branch_indices(row_len: int, cap: int) -> List[int]:
        return [i for i in range(min(row_len - 1, cap)) if i != row_len - 1]

    @staticmethod
    async def recommend1team(
        already_used_units: List[int],
    ) -> Optional[ArenaQueryRecord]:
        """推荐1个无冲配队"""
        frequent = await arena_sqla.get_frequent_win_solutions_from_mzq(limit=100)
        for record_6 in frequent:
            record_4 = str_to_ids(record_6)
            team_mix = already_used_units + record_4
            if len(team_mix) == len(set(team_mix)):
                return ArenaQueryRecord(
                    type=ArenaRecordType.pcrfans_often_used,
                    enemies=[],
                    solution=FormatSolution(
                        atk=record_4,
                        up=0,
                        down=0,
                        timestamp=0,
                    ),
                )
        return None

    @staticmethod
    async def recommend2teams(
        already_used_units: List[int],
    ) -> Tuple[Optional[ArenaQueryRecord], Optional[ArenaQueryRecord]]:
        """推荐2个无冲配队"""
        frequent_used_records = (
            await arena_sqla.get_frequent_win_solutions_from_mzq()
            + await arena_sqla.get_frequent_used_solutions_from_pcrfans()
        )

        try_combinations = []
        for record_1_index in range(len(frequent_used_records) - 1):
            try_combinations.extend(
                [record_1_index, record_2_index, record_1_index + record_2_index]
                for record_2_index in range(
                    record_1_index + 1, len(frequent_used_records)
                )
            )
        try_combinations = list(sorted(try_combinations, key=lambda x: x[-1]))

        for try_combination in try_combinations:
            record_6_1_index = try_combination[0]
            record_6_1 = frequent_used_records[record_6_1_index]
            record_4_1 = str_to_ids(record_6_1)

            record_6_2_index = try_combination[1]
            record_6_2 = frequent_used_records[record_6_2_index]
            record_4_2 = str_to_ids(record_6_2)

            team_mix = already_used_units + record_4_1 + record_4_2
            if len(team_mix) == len(set(team_mix)):
                return (
                    ArenaQueryRecord(
                        type=ArenaRecordType.pcrfans_often_used,
                        enemies=[],
                        solution=FormatSolution(
                            atk=record_4_1,
                            up=0,
                            down=0,
                            timestamp=0,
                        ),
                    ),
                    ArenaQueryRecord(
                        type=ArenaRecordType.pcrfans_often_used,
                        enemies=[],
                        solution=FormatSolution(
                            atk=record_4_2,
                            up=0,
                            down=0,
                            timestamp=0,
                        ),
                    ),
                )

        return None, None

    @staticmethod
    async def try_fill_teams(
        records: List[ArenaQueryRecord], team_mix: List[int], val: float
    ) -> bool:
        """尝试填充缺失的队伍。返回 True 表示成功"""
        teams = [record.solution.atk if record.solution else [] for record in records]
        empty_count = sum(not team for team in teams)

        if empty_count == 0:
            return True
        elif empty_count == 1 and val >= -50:
            if rec := await CollisionFreeTeamGenerator.recommend1team(team_mix):
                for i, team in enumerate(teams):
                    if not team:
                        records[i] = rec
                return True
        elif empty_count >= 2 and val >= -150:
            rec1, rec2 = await CollisionFreeTeamGenerator.recommend2teams(team_mix)
            if rec1 and rec2:
                filled = 0
                for i, team in enumerate(teams):
                    if not team and filled < 2:
                        records[i] = rec1 if filled == 0 else rec2
                        filled += 1
                return True
        return False

    async def generate(self, limit: int = 10) -> List[ArenaQueryRecord]:
        """
        生成无冲突的队伍组合

        Args:
            limit: 最多返回多少个组合

        Raises:
            NoFreeCollisionError: 无法找到无冲突的组合
        """
        valid_results = []
        partial_results = []

        for combo in self.combinations:
            indices = combo[:-1]
            score = combo[-1]

            if score < -250:
                break

            records = [
                self.all_query_records[i][indices[i]]
                for i in range(len(self.all_query_records))
            ]
            teams = [
                record.solution.atk if record.solution else [] for record in records
            ]
            team_mix = sum(teams, [])

            if len(team_mix) != len(set(team_mix)):
                continue

            if not await self.try_fill_teams(records, team_mix, score):
                if len(self.all_query_records) == 3 and score >= -50:
                    partial_results.extend(
                        records + [ArenaQueryRecord(type=ArenaRecordType.placehodlder)]
                    )
                continue

            valid_results.extend(
                records + [ArenaQueryRecord(type=ArenaRecordType.placehodlder)]
            )
            if len(valid_results) // (len(self.all_query_records) + 1) >= limit:
                break

        if valid_results:
            return valid_results[:-1]
        elif partial_results:
            return partial_results[:-1]
        else:
            raise NoFreeCollisionError()


def remove_duplicates(records: List[ArenaQueryRecord]) -> List[ArenaQueryRecord]:
    seen = set()
    unique_records = []
    for record in records:
        record_tuple = tuple(sorted(record.solution.atk)) if record.solution else ()
        if record_tuple not in seen:
            seen.add(record_tuple)
            unique_records.append(record)
    return unique_records


def check_cache_valid(record: Optional[MzqCache], now, days: int = 7) -> bool:
    """检查缓存是否有效"""
    return record.timestamp + 86400 * days >= now if record else False


def wrap_query_results(
    solutions: List[Union[PcrfansCacheData, AttackData, MzqCache, MzqBattleResult]],
    enemies: List[int],
    record_type: ArenaRecordType,
) -> List[ArenaQueryRecord]:
    """将查询结果转换为 ArenaQueryRecord 列表"""
    return [
        ArenaQueryRecord(
            enemies=enemies,
            type=record_type,
            solution=FormatSolution.from_data(solution),
        )
        for solution in solutions
    ]


def build_replace_map(
    enemies_ids: List[int], enemies: List[int], replace_unit: int
) -> Dict[int, int]:
    """构建替换映射"""
    replace_map = {replace_unit: enemy for enemy in enemies_ids if enemy not in enemies}
    return replace_map or {replace_unit: 170201}


class ArenaQuery:
    def __init__(self, region: int, command: str):
        self.region = region
        self.command = command
        self.enemies_ids = []
        self.extra = ""

    async def get_enemies_ids(self) -> Tuple[List[List[int]], str]:
        if self.enemies_ids:
            return self.enemies_ids, self.extra
        if ret := re.match(CQ_PATTERN, self.command):
            image = Image.open(BytesIO(await get_pic(ret[2].replace("&amp;", "&"))))
            self.enemies_ids, self.extra = await extract_position(image)
            if not self.enemies_ids:
                raise NotEnoughUnitError()

            if len(self.enemies_ids) > 3:
                raise ValueError(
                    "请截图pjjc详细对战记录（对战履历详情）（含敌我双方2或3队阵容）"
                )
            return self.enemies_ids, self.extra

        if "#" in self.command and "vs" in self.command:
            cmd = self.command.strip().split("vs")
            atk_part, def_part = cmd[0], cmd[1]
            atk_list = [
                names_to_ids(t.strip()) for t in atk_part.split("#") if t.strip()
            ]
            def_list = [
                names_to_ids(t.strip()) for t in def_part.split("#") if t.strip()
            ]
            if len(atk_list) > 8 or len(def_list) > 8:
                raise ValueError("进攻队或防守队队伍数量超过8")
            self.enemies_ids = [atk_list, def_list]
            atk_names = "\n".join(ids_to_names(atk) for atk in atk_list)
            def_names = "\n".join(ids_to_names(d) for d in def_list)
            self.extra = f"进攻队\n{atk_names}\nVS\n防守队\n{def_names}"
            return self.enemies_ids, self.extra
        elif "vs" in self.command:
            args = self.command.strip().split("vs")
            atk = names_to_ids(args[0])
            enemies = names_to_ids(args[1])
            self.enemies_ids = [
                atk,
                enemies,
            ]
            self.extra = f"【{ids_to_names(atk)}】VS【{ids_to_names(enemies)}】"
            return self.enemies_ids, self.extra

        elif "#" in self.command:
            args = self.command.strip().split("#")
            self.enemies_ids = [names_to_ids(arg) for arg in args if arg.strip()]
            if len(self.enemies_ids) > 3:
                raise ValueError("队伍数量超过3")
            self.extra = (
                "多队查询，敌方队伍分别为：【"
                + "】、【".join(ids_to_names(ids) for ids in self.enemies_ids)
                + "】"
            )
            return self.enemies_ids, self.extra
        ids = names_to_ids(self.command)
        self.enemies_ids = [
            ids,
        ]
        self.extra = f"防守方【{'，'.join([chara.fromid(long_id_to_short(unit_id)).name for unit_id in ids])}】"
        return self.enemies_ids, self.extra

    async def run_single_simulation(self) -> Tuple[ArenaQueryRecord, str]:
        """简化版同步战斗模拟"""
        (atk, enemies), msg = await self.get_enemies_ids()

        await pcr_sqla.get_all_units()
        result = await self.run_sumulate_battle(user_teams=[atk], enemy_teams=[enemies])
        return result[0], msg

    async def matrix_simulate(
        self,
    ) -> Tuple[
        List[List[int]],
        List[List[int]],
        List[List[Optional[ArenaQueryRecord]]],
        str,
    ]:
        (atk_list, def_list), extra = await self.get_enemies_ids()
        await pcr_sqla.get_all_units()

        user_teams: List[List[int]] = []
        enemy_teams: List[List[int]] = []
        for atk in atk_list:
            for defn in def_list:
                user_teams.append(atk)
                enemy_teams.append(defn)

        records = await self.run_sumulate_battle(
            user_teams=user_teams, enemy_teams=enemy_teams
        )
        result_map: Dict[Tuple[str, str], ArenaQueryRecord] = {
            (ids_to_str(r.solution.atk), ids_to_str(r.enemies)): r
            for r in records
            if r.solution
        }
        matrix: List[List[Optional[ArenaQueryRecord]]] = [
            [result_map.get((ids_to_str(atk), ids_to_str(defn))) for defn in def_list]
            for atk in atk_list
        ]

        return atk_list, def_list, matrix, extra

    async def run_sumulate_battle(
        self, user_teams: List[List[int]], enemy_teams: List[List[int]]
    ) -> List[ArenaQueryRecord]:
        """简化版多组同步战斗模拟，批量提交到服务器"""
        if not user_teams or not enemy_teams:
            return []

        user_teams = [pcr_sqla.deck_sort_unit(t, strict=True) for t in user_teams]
        enemy_teams = [pcr_sqla.deck_sort_unit(t, strict=True) for t in enemy_teams]
        result = await mzq_query.run_simulate_battle(
            user_ids=user_teams,
            enemy_ids=enemy_teams,
        )
        if not result:
            raise ValueError("模拟对战提交失败，请稍后再试")
        await arena_sqla.add_mzq_records(result, self.region)
        return [
            ArenaQueryRecord(
                type=ArenaRecordType.mzq,
                enemies=res.enemies,
                solution=FormatSolution.from_data(res),
            )
            for res in result
        ]

    async def mzq_check(
        self, use_cache: bool = True
    ) -> Tuple[List[ArenaQueryRecord], str]:
        t0 = datetime.datetime.now().timestamp()
        query_dict: Dict[str, List[ArenaQueryRecord]] = {}
        enemies_teams, extra = await self.get_enemies_ids()
        await pcr_sqla.get_all_units()

        for enemy_team in enemies_teams:
            if len(enemy_team) < 5:
                return [], f"{extra}请提供完整的5人编队进行模拟对战提交"
            if not pcr_sqla.check_units_exist(enemy_team):
                return [], f"{extra}敌方队伍包含数据库不存在的单位"

        team_results = await asyncio.gather(
            *(self.single_arena_query(query_team=team) for team in enemies_teams)
        )
        for enemy_team, results in zip(enemies_teams, team_results):
            query_dict[ids_to_str(enemy_team)] = sorted(
                [r for r in results if r.solution],
                key=lambda x: x.score,
                reverse=True,
            )

        teams_to_simulate: Dict[str, List[ArenaQueryRecord]] = {
            key: [] for key in query_dict
        }

        win_count: Dict[str, int] = {key: 0 for key in query_dict}
        existing_atk: Dict[str, Set[str]] = defaultdict(set)
        now = datetime.datetime.now().timestamp()

        if use_cache:
            pair_keys = [
                (ids_to_str(result.solution.atk), key)
                for key, results in query_dict.items()
                for result in results
            ]
            cache_map: Dict[Tuple[str, str], MzqCache] = (
                await arena_sqla.get_mzq_caches_by_pair_keys(pair_keys)
            )

            for key, results in query_dict.items():
                for result in results:
                    atk_s = ids_to_str(result.solution.atk)
                    record = cache_map.get((atk_s, key))
                    if check_cache_valid(record, now):
                        existing_atk[key].add(atk_s)
                        if record.win_rate >= 0.8:
                            win_count[key] += 1
                    else:
                        teams_to_simulate[key].append(result)
        else:
            for key, results in query_dict.items():
                for result in results:
                    teams_to_simulate[key].append(result)

        atk_teams: List[List[int]] = []
        enemy_teams: List[List[int]] = []
        for key, lst in teams_to_simulate.items():
            lst = [r for r in lst if pcr_sqla.check_units_exist(r.solution.atk)]
            if not lst:
                continue
            lst = (
                random.sample(lst, min(len(lst), 38)) if use_cache else lst
            )  # 如果使用缓存，则随机采样38条
            def_ids = str_to_ids(key)
            for r in lst:
                existing_atk[key].add(ids_to_str(r.solution.atk))
                atk_teams.append(r.solution.atk)
                enemy_teams.append(def_ids)
        logger.info(
            f"需要模拟的队伍数：{len(atk_teams)}, 解生成时间：{datetime.datetime.now().timestamp() - t0:.2f}s"
        )
        t0 = datetime.datetime.now().timestamp()
        sim_records = await self.run_sumulate_battle(
            user_teams=atk_teams,
            enemy_teams=enemy_teams,
        )
        logger.info(
            f"模拟对战完成，时间：{datetime.datetime.now().timestamp() - t0:.2f}s"
        )
        qkeys = frozenset(query_dict)
        for r in sim_records:
            sol = r.solution
            if sol and sol.win_rate >= 0.8:
                en = ids_to_str(r.enemies)
                if en in qkeys:
                    win_count[en] += 1
        if supplement_needed := {k: v for k, v in win_count.items() if v < 10}:
            logger.info(
                f"敌方队伍胜利结果不足，补充模拟：{len(supplement_needed)}个队伍"
            )
            t0 = datetime.datetime.now().timestamp()
            frequent_teams = await arena_sqla.get_frequent_win_solutions_from_mzq(
                limit=100
            )
            if use_cache:
                sup_pairs: List[Tuple[str, str]] = []
                for key in supplement_needed:
                    sup_pairs.extend(
                        (atk_str, key)
                        for atk_str in frequent_teams
                        if atk_str not in existing_atk[key]
                        and pcr_sqla.check_units_exist(str_to_ids(atk_str))
                    )
                sup_cache_map = await arena_sqla.get_mzq_caches_by_pair_keys(sup_pairs)
            else:
                sup_cache_map = {}

            atk_teams.clear()
            enemy_teams.clear()

            for key in supplement_needed:
                num = 0
                cap = 38 - win_count[key]
                def_ids = str_to_ids(key)
                for atk_str in frequent_teams:
                    if num >= cap:
                        break
                    if atk_str in existing_atk[key]:
                        continue
                    atk_ids = str_to_ids(atk_str)
                    if not pcr_sqla.check_units_exist(atk_ids) or check_cache_valid(
                        sup_cache_map.get((atk_str, key)), now
                    ):
                        continue
                    num += 1
                    atk_teams.append(atk_ids)
                    enemy_teams.append(def_ids)
                    existing_atk[key].add(atk_str)

            logger.info(
                f"补充模拟队伍数：{len(atk_teams)}, 时间：{datetime.datetime.now().timestamp() - t0:.2f}s"
            )
            t0 = datetime.datetime.now().timestamp()
            await self.run_sumulate_battle(
                user_teams=atk_teams,
                enemy_teams=enemy_teams,
            )
            logger.info(
                f"补充模拟对战完成，时间：{datetime.datetime.now().timestamp() - t0:.2f}s"
            )
        return await self.arena_query(
            allow=(ArenaQueryType.mzq,),
            limit=10,
        )

    async def single_arena_query(
        self, query_team: List[int], allow: Tuple[ArenaQueryType] = None
    ) -> List[ArenaQueryRecord]:
        if allow is None:
            allow = (ArenaQueryType.mzq, ArenaQueryType.pcrfans)
        records = []
        if len(set(query_team)) != 1 or query_team[0] != 100001:
            has_mzq = ArenaQueryType.mzq in allow
            has_pcr = ArenaQueryType.pcrfans in allow
            if has_mzq and has_pcr:
                mzq_part, pcr_part = await asyncio.gather(
                    self.single_mzq_cache_query(query_team),
                    self.single_pcrfans_arena_query(query_team),
                )
                records += mzq_part + pcr_part
            else:
                for atype in allow:
                    if atype == ArenaQueryType.mzq:
                        records += await self.single_mzq_cache_query(query_team)
                    elif atype == ArenaQueryType.pcrfans:
                        records += await self.single_pcrfans_arena_query(query_team)
            records = remove_duplicates(records)
        return records

    async def arena_query(
        self, allow: Tuple[ArenaQueryType] = None, limit: int = 10
    ) -> Tuple[List[ArenaQueryRecord], str]:
        if allow is None:
            allow = (ArenaQueryType.mzq, ArenaQueryType.pcrfans)

        enemies_teams, extra = await self.get_enemies_ids()
        all_query_records = []
        team_has_result = 0

        record_lists = await asyncio.gather(
            *(
                self.single_arena_query(query_team, allow)
                for query_team in enemies_teams
            )
        )
        for records in record_lists:
            if records:
                team_has_result += 1
                records = sorted(records, key=lambda x: x.score, reverse=True)
            all_query_records.append(
                records + [ArenaQueryRecord(type=ArenaRecordType.placehodlder)]
            )

        # 处理查询结果
        if team_has_result == 0 and len(enemies_teams) == 3:
            raise AllNoResultError()

        if len(enemies_teams) == 1:
            records = all_query_records[0]
            return (records[:limit] if len(records) > 1 else []), extra

        if team_has_result == 1:
            for index, records in enumerate(all_query_records, start=1):
                if len(records) > 1:
                    return records[:limit], f"仅第{index}队查询到解法！"

        # 处理多队情况，生成无冲突组合
        collision_free_generator = CollisionFreeTeamGenerator(all_query_records)
        return (
            await collision_free_generator.generate(limit=limit),
            extra,
        )

    async def find_mzq_approximate_team(
        self, _enemies: List[int], replae_unit: int = 100001
    ) -> List[ArenaQueryRecord]:
        enemies = [e for e in _enemies if e != replae_unit]
        full_enemies_list = await arena_sqla.get_mzq_approximate_team(enemies)

        result_list = []
        for full_enemies in full_enemies_list:
            enemies_ids = str_to_ids(full_enemies.enemies)
            if replae_unit not in enemies_ids:
                result_list.append(
                    ArenaQueryRecord(
                        enemies=enemies_ids,
                        type=ArenaRecordType.mzq_approximate,
                        solution=FormatSolution.from_data(full_enemies),
                        replace=build_replace_map(enemies_ids, enemies, replae_unit),
                    )
                )
        return result_list

    async def find_pcrfans_approximate_team(
        self, _enemies: List[int], replae_unit: int = 100001
    ) -> List[ArenaQueryRecord]:
        enemies = [e for e in _enemies if e != replae_unit]
        logger.info(f"查询近似解：{sorted(enemies)}")

        full_enemies_list = await arena_sqla.get_pcrfans_approximate_team(
            enemies, self.region
        )

        result_list = []
        for full_enemies in full_enemies_list:
            logger.info(f"近似解敌人组：{full_enemies.enemies} id={full_enemies.id}")
            enemies_ids = str_to_ids(full_enemies.enemies)

            if replae_unit not in enemies_ids:
                for solution in await arena_sqla.get_pcrfans_cache_data_by_id(
                    full_enemies.id
                ):
                    result_list.append(
                        ArenaQueryRecord(
                            enemies=enemies_ids,
                            type=ArenaRecordType.pcrfans_approximate,
                            solution=FormatSolution.from_data(solution),
                            replace=build_replace_map(
                                enemies_ids, enemies, replae_unit
                            ),
                        )
                    )

        if len(result_list) < 10:
            logger.info("结果较少，查询pcrfans近似解补充")
            resp = await pcrfans_query(enemies, 1, self.region, 1)
            result_list.extend(
                ArenaQueryRecord(
                    enemies=record.def_,
                    type=ArenaRecordType.pcrfans_approximate,
                    solution=FormatSolution.from_data(record),
                    replace=build_replace_map(record.def_, enemies, replae_unit),
                )
                for record in resp
            )
            await arena_sqla.add_pcrfans_record(resp, self.region)
        return result_list

    async def single_mzq_cache_query(
        self, enemies: List[int]
    ) -> List[ArenaQueryRecord]:
        # 执行查询
        logger.info("Doing query...")
        if len(enemies) <= 4:
            return await self.find_mzq_approximate_team(enemies)

        enemies_str = ids_to_str(enemies)
        mzq_query = await arena_sqla.get_mzq_team_by_enemies(enemies_str)
        mzq_result = wrap_query_results(mzq_query, enemies, ArenaRecordType.mzq)

        approx_parts = await asyncio.gather(
            *(
                self.find_mzq_approximate_team(enemies, replae_unit=enemy_unit)
                for enemy_unit in enemies
            )
        )
        for part in approx_parts:
            mzq_result += part
        return mzq_result

    async def single_pcrfans_arena_query(
        self, enemies: List[int]
    ) -> List[ArenaQueryRecord]:
        logger.info("Doing query...")
        if len(enemies) <= 4:
            return await self.find_pcrfans_approximate_team(enemies)

        enemies_str = ids_to_str(enemies)

        # 尝试查询缓存（5天内）
        result = await arena_sqla.get_pcrfans_cache_data_by_enemies(
            enemies_str, self.region, 5
        )
        if result:
            return wrap_query_results(result, enemies, ArenaRecordType.pcrfans_cache)

        # 尝试新查询
        result = await pcrfans_query(enemies, 1, self.region, 1)
        await arena_sqla.add_pcrfans_record(result, self.region)
        if result:
            return wrap_query_results(result, enemies, ArenaRecordType.pcrfans)

        # 尝试全部缓存
        result = await arena_sqla.get_pcrfans_cache_data_by_enemies(
            enemies_str, self.region
        )
        if result:
            return wrap_query_results(result, enemies, ArenaRecordType.pcrfans_cache)

        # 尝试其他服务器
        logger.info("尝试其他服务器查询")
        for other_region in query_seq.get(self.region, []):
            result = await arena_sqla.get_pcrfans_cache_data_by_enemies(
                enemies_str, other_region
            )
            if result:
                return wrap_query_results(
                    result, enemies, ArenaRecordType.pcrfans_cache
                )

        # 返回近似解
        result = []
        for enemy_unit in enemies:
            result += await self.find_pcrfans_approximate_team(
                enemies, replae_unit=enemy_unit
            )
        return random.sample(result, min(len(result), 50))
