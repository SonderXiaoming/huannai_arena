from functools import wraps
import time
from typing import (
    Any,
    Awaitable,
    Callable,
    Concatenate,
    Dict,
    List,
    ParamSpec,
    Tuple,
    TypeVar,
    overload,
)

from sqlalchemy import delete, func, or_, tuple_
from sqlalchemy.future import select

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlmodel import distinct

from ..query.mzq.model import MzqBattleResult

from ..utils.tool import ids_to_str

from ..query.pcrfans.model import AttackData
from .table import (
    ArenaModel,
    MzqCache,
    MzqDetail,
    PcrfansCache,
    UnitData,
    PcrfansDetail,
    PcrfansCacheData,
    UnitTalent,
)
from ..setting import db_config

T = TypeVar("T")
P = ParamSpec("P")


@overload
def session(
    func: Callable[Concatenate[Any, "AsyncSession", P], Awaitable[T]],
) -> Callable[Concatenate[Any, P], Awaitable[T]]: ...


def session(
    func: Callable[Concatenate[Any, AsyncSession, P], Awaitable[T]],
) -> Callable[Concatenate[Any, P], Awaitable[T]]:
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        async with self.async_session() as _session:
            async with _session.begin():
                return await func(self, _session, *args, **kwargs)

    return wrapper  # 返回包装后的函数


class PCRDatabase:
    def __init__(self, url: str):
        # 增加连接池限制，减少资源占用
        self.engine = create_async_engine(
            url,
            pool_recycle=1500,
            # pool_size=5,  # 最大连接数
            # max_overflow=2,  # 允许的最大溢出连接数
        )
        self.async_session = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        self.units: Dict[int, UnitData] = {}

    def check_units_exist(self, unit_ids: List[int]) -> bool:
        """检查单位ID是否都存在于数据库中"""
        return all(unit_id in self.units for unit_id in unit_ids)

    @session
    async def get_all_units(self, session: AsyncSession) -> Dict[int, UnitData]:
        result = await session.execute(
            select(
                UnitData.unit_id,
                UnitData.search_area_width,
                UnitTalent.talent_id,
            ).where(UnitData.unit_id == UnitTalent.unit_id)
        )
        units = result.fetchall()
        self.units = {
            unit.unit_id: (unit.search_area_width, unit.talent_id) for unit in units
        }
        return self.units

    def deck_sort_unit(self, units: List[int], strict: bool = False) -> List[int]:
        not_found = [unit_id for unit_id in units if unit_id not in self.units]
        if strict and not_found:  # 严格模式
            raise ValueError(f"一些单位ID在数据库中未找到: {not_found}")

        if strict:
            # strict 模式下已确保所有单位存在，直接排序
            return sorted(
                units,
                key=lambda x: self.units[x][0],
            )
        else:
            return sorted(
                units,
                key=lambda x: self.units.get(x, (9999, None))[0],
            )

    def get_unit_talent(self, unit_id: int) -> int:
        """获取单位的天赋ID，未找到返回0"""
        return self.units.get(unit_id, (None, 0))[1]


class ArenaDatabase:
    def __init__(self, url: str):
        is_pg = url.startswith("postgresql")
        pool_kwargs = (
            {
                "pool_size": db_config.arena_pool_size,
                "max_overflow": db_config.arena_max_overflow,
                "pool_timeout": db_config.arena_pool_timeout,
            }
            if is_pg
            else {}
        )
        self.engine = create_async_engine(
            url,
            pool_recycle=1500,
            **pool_kwargs,
        )
        self.async_session = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def create_all(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(ArenaModel.metadata.create_all)

    @session
    async def get_pcrfans_approximate_team(
        self, session: AsyncSession, id_list: List[int], region: int
    ) -> List[PcrfansCache]:
        need_num = len(id_list)
        matching_ids = (
            select(PcrfansDetail.id)
            .where(PcrfansDetail.unit.in_(id_list))
            .group_by(PcrfansDetail.id)
            .having(func.count(distinct(PcrfansDetail.unit)) >= need_num)
        )
        result = await session.execute(
            select(PcrfansCache)
            .where(
                PcrfansCache.id.in_(matching_ids),
                or_(PcrfansCache.region == region, PcrfansCache.region == 1),
            )
            .limit(100)
        )
        return result.scalars().all()

    @session
    async def get_pcrfans_cache_data_by_enemies(
        self, session: AsyncSession, enemies: str, region: int, days: int = 0
    ) -> List[PcrfansCacheData]:
        sql = select(PcrfansCacheData).where(
            PcrfansCache.enemies == enemies,
            PcrfansCacheData.id == PcrfansCache.id,
            or_(PcrfansCache.region == region, PcrfansCache.region == 1),
        )
        if days > 0:
            cutoff = int(time.time()) - days * 86400
            sql = sql.where(PcrfansCacheData.timestamp >= cutoff)
        sql = sql.limit(100)
        result = await session.execute(sql)
        return result.scalars().all()

    @session
    async def get_pcrfans_cache_data_by_id(
        self, session: AsyncSession, enemies_id: int
    ) -> List[PcrfansCacheData]:
        result = await session.execute(
            select(PcrfansCacheData).where(PcrfansCacheData.id == enemies_id).limit(100)
        )
        return result.scalars().all()

    @session
    async def get_all_pcrfans_record(
        self, session: AsyncSession, region: int
    ) -> List[PcrfansCache]:
        result = await session.execute(
            select(PcrfansCache).where(
                or_(
                    PcrfansCache.region == region, PcrfansCache.region == 1
                ),  # 1是全服不区分
            )
        )
        return result.scalars().all()

    @session
    async def add_pcrfans_record(
        self, session: AsyncSession, data: List[AttackData], region: int
    ):
        # 优化：不一次性加载所有记录，按enemies+region分批查找
        data_dict: Dict[str, List[AttackData]] = {}
        for item in data:
            enemies = ids_to_str(item.def_)
            if enemies not in data_dict:
                data_dict[enemies] = []
            data_dict[enemies].append(item)

        for enemies, items in data_dict.items():
            # 只查当前enemies+region和enemies+1
            result = await session.execute(
                select(PcrfansCache)
                .where(
                    PcrfansCache.enemies == enemies,
                    or_(PcrfansCache.region == region, PcrfansCache.region == 1),
                )
                .limit(2)
            )
            record = None
            for r in result.scalars():
                if r.region == region:
                    record = r
                    break
                elif r.region == 1:
                    record = r
            if record:
                await session.execute(
                    delete(PcrfansCacheData).where(PcrfansCacheData.id == record.id)
                )
                await session.execute(
                    delete(PcrfansDetail).where(PcrfansDetail.id == record.id)
                )
            else:
                record = PcrfansCache(
                    enemies=enemies,
                    region=region,
                )
                session.add(record)
                await session.flush()  # 确保record.id被分配

            seen = set()
            new_items = []
            for item in items:
                atk_str = ids_to_str(item.atk)
                if atk_str in seen:
                    continue
                seen.add(atk_str)
                new_items.append(item)
            items = new_items

            session.add_all(
                [
                    PcrfansCacheData(
                        id=record.id,
                        attackers=ids_to_str(item.atk),
                        timestamp=int(time.time()),
                        up=item.up,
                        down=item.down,
                    )
                    for item in items
                ]
            )
            # 只插入一次PcrfansDetail，避免item.def_不同导致多次插入
            if items:
                session.add_all(
                    [
                        PcrfansDetail(id=record.id, unit=unit_id)
                        for unit_id in items[0].def_
                    ]
                )

    @session
    async def get_frequent_used_solutions_from_pcrfans(
        self, session: AsyncSession, limit: int = 10
    ) -> List[str]:
        result = await session.execute(
            select(PcrfansCacheData.attackers)
            .where(
                PcrfansCacheData.timestamp
                >= int(time.time()) - 86400 * 30  # 过去30天的数据
            )
            .group_by(PcrfansCacheData.attackers)
            .order_by(func.count(PcrfansCacheData.attackers).desc())
            .limit(limit)
        )
        return result.scalars().all()

    @session
    async def get_frequent_win_solutions_from_mzq(
        self,
        session: AsyncSession,
        limit: int = 50,
        days: int = 30,
        min_win_rate: float = 0.8,
    ) -> List[str]:
        """
        获取mzq缓存中高胜率队伍

        Args:
            limit: 返回数量限制
            days: 查询过去多少天的数据
            min_win_rate: 最小胜率要求

        Returns:
            攻击队伍字符串列表，按胜率从高到低排序
        """
        # 计算胜率 = win_count / (win_count + lose_count + timeout_count)
        # 只选择胜率 >= min_win_rate 的队伍
        result = await session.execute(
            select(MzqCache.attackers)
            .where(
                MzqCache.timestamp >= int(time.time()) - 86400 * days,
                MzqCache.win_count > 0,  # 至少有一次胜利
            )
            .group_by(MzqCache.attackers)
            .having(
                (
                    func.sum(MzqCache.win_count)
                    / (
                        func.sum(MzqCache.win_count)
                        + func.sum(MzqCache.lose_count)
                        + func.sum(MzqCache.timeout_count)
                    )
                )
                >= min_win_rate
            )
            .order_by(
                (
                    func.sum(MzqCache.win_count)
                    / (
                        func.sum(MzqCache.win_count)
                        + func.sum(MzqCache.lose_count)
                        + func.sum(MzqCache.timeout_count)
                    )
                ).desc(),
                func.count(MzqCache.attackers).desc(),  # 胜率相同时按出现频率排序
            )
            .limit(limit)
        )
        result = result.scalars().all()
        if len(result) < limit:
            # 如果不足limit条，再补充一些时间更长的数据
            additional_result = await session.execute(
                select(MzqCache.attackers)
                .where(
                    MzqCache.timestamp < int(time.time()) - 86400 * days,
                    MzqCache.win_count > 0,
                )
                .group_by(MzqCache.attackers)
                .having(
                    (
                        func.sum(MzqCache.win_count)
                        / (
                            func.sum(MzqCache.win_count)
                            + func.sum(MzqCache.lose_count)
                            + func.sum(MzqCache.timeout_count)
                        )
                    )
                    >= min_win_rate
                )
                .order_by(
                    (
                        func.sum(MzqCache.win_count)
                        / (
                            func.sum(MzqCache.win_count)
                            + func.sum(MzqCache.lose_count)
                            + func.sum(MzqCache.timeout_count)
                        )
                    ).desc()
                )
                .limit(limit - len(result))
            )
            result += additional_result.scalars().all()
        return result

    @session
    async def get_mzq_team_by_enemies(
        self,
        session: AsyncSession,
        enemies: str,
        region: int = 2,
        min_win_rate: float = 0.8,
    ) -> List[MzqCache]:
        """获取针对指定敌方队伍的高胜率解决方案"""
        total_count = MzqCache.win_count + MzqCache.lose_count + MzqCache.timeout_count
        _result = await session.execute(
            select(MzqCache)
            .where(
                MzqCache.enemies == enemies,
                MzqCache.region == region,
                MzqCache.win_count > 0,
                total_count > 0,
                MzqCache.win_count >= min_win_rate * total_count,
            )
            # 先筛选胜率再截断，避免前 100 条低胜率记录遮住有效解。
            .order_by(MzqCache.timestamp.desc(), MzqCache.id.desc())
            .limit(100)
        )
        return list(_result.scalars().all())

    @session
    async def get_mzq_caches_by_pair_keys(
        self,
        session: AsyncSession,
        pair_keys: List[Tuple[str, str]],
        region: int = 2,
        chunk_size: int = 400,
    ) -> Dict[Tuple[str, str], MzqCache]:
        """按 (attackers, enemies) 批量查询 MzqCache，减少往返。"""
        if not pair_keys:
            return {}
        unique_pairs = list(dict.fromkeys(pair_keys))
        out: Dict[Tuple[str, str], MzqCache] = {}
        for i in range(0, len(unique_pairs), chunk_size):
            chunk = unique_pairs[i : i + chunk_size]
            _result = await session.execute(
                select(MzqCache).where(
                    MzqCache.region == region,
                    tuple_(MzqCache.attackers, MzqCache.enemies).in_(chunk),
                )
            )
            for row in _result.scalars().all():
                out[(row.attackers, row.enemies)] = row
        return out

    @session
    async def get_mzq_approximate_team(
        self, session: AsyncSession, id_list: List[int], min_win_rate: float = 0.5
    ) -> List[MzqCache]:
        """获取近似解，返回高胜率队伍"""
        total_count = MzqCache.win_count + MzqCache.lose_count + MzqCache.timeout_count
        need_num = len(id_list)
        matching_ids = (
            select(MzqDetail.id)
            .where(MzqDetail.unit.in_(id_list))
            .group_by(MzqDetail.id)
            .having(func.count(distinct(MzqDetail.unit)) >= need_num)
        )
        result = await session.execute(
            select(MzqCache)
            .where(
                MzqCache.id.in_(matching_ids),
                MzqCache.win_count > 0,
                total_count > 0,
                MzqCache.win_count >= min_win_rate * total_count,
            )
            .limit(100)
        )
        return list(result.scalars().all())

    @session
    async def add_mzq_records(
        self,
        session: AsyncSession,
        results: List[MzqBattleResult],
        region: int = 2,
        chunk_size: int = 400,
    ) -> None:
        """批量写入/更新 mzq 模拟结果，单事务一次往返完成。

        - 一次性 SELECT 已存在 (attackers, enemies) 行
        - 直接修改 ORM 对象属性（依赖单 session 的脏标记）
        - 新增行集中 add，flush 一次拿 ID 后批量插 MzqDetail
        - 同批 (attackers, enemies) 重复时以最后一条为准
        """
        if not results:
            return

        latest: Dict[Tuple[str, str], MzqBattleResult] = {}
        for r in results:
            key = (ids_to_str(r.attackers), ids_to_str(r.enemies))
            latest[key] = r

        pairs = list(latest.keys())
        existing: Dict[Tuple[str, str], MzqCache] = {}
        for i in range(0, len(pairs), chunk_size):
            chunk = pairs[i : i + chunk_size]
            _result = await session.execute(
                select(MzqCache).where(
                    MzqCache.region == region,
                    tuple_(MzqCache.attackers, MzqCache.enemies).in_(chunk),
                )
            )
            for row in _result.scalars().all():
                existing[(row.attackers, row.enemies)] = row

        now_ts = int(time.time())
        new_caches: List[Tuple[MzqCache, List[int]]] = []
        for (atk_s, en_s), r in latest.items():
            if row := existing.get((atk_s, en_s)):
                row.timestamp = now_ts
                row.win_count = r.win_count
                row.lose_count = r.lose_count
                row.timeout_count = r.timeout_count
                row.battle_frames = r.battle_frames
            else:
                cache = MzqCache(
                    enemies=en_s,
                    attackers=atk_s,
                    region=region,
                    timestamp=now_ts,
                    win_count=r.win_count,
                    lose_count=r.lose_count,
                    timeout_count=r.timeout_count,
                    battle_frames=r.battle_frames,
                )
                session.add(cache)
                new_caches.append((cache, list(r.enemies)))

        if new_caches:
            await session.flush()
            session.add_all(
                [
                    MzqDetail(id=cache.id, unit=unit_id)
                    for cache, enemies_list in new_caches
                    for unit_id in enemies_list
                ]
            )


pcr_sqla = PCRDatabase(db_config.pcr_url)
arena_sqla = ArenaDatabase(db_config.effective_arena_url)
