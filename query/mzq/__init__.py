import datetime
import traceback
from typing import List, Optional
from .model import (
    BattleRequestDTO,
    BattleResponseDTO,
    GuildRandomDataDTO,
    MzqBattleResult,
    UnitDTO,
    VersionResponseDTO,
    eBattleResult,
)
from ...constants import CLIENT
from ...setting import mzq_config
from loguru import logger


class APIError(Exception):
    """API 请求失败异常"""

    pass


class Query:

    def __init__(self):
        self.api_list = (
            mzq_config.api if isinstance(mzq_config.api, list) else [mzq_config.api]
        )

    async def query(self, query_data, timeout: float):
        """
        发送 POST 请求到 API，支持多个 API URL 的重试机制

        Args:
            json_data: 请求体数据
            timeout: 请求超时时间（秒）
            success_msg: 成功日志消息
            error_msg_prefix: 错误日志消息前缀
            response_parser: 可选的响应处理函数，接收 response.json()，返回处理后的数据

        Returns:
            如果提供了 response_parser，返回其处理结果；否则返回原始响应 JSON

        Raises:
            APIError: 所有 API 都请求失败时抛出
        """
        # 获取 API 列表
        if not self.api_list:
            raise APIError("未配置摸轴器 API，请在 config.json 的 mzq.api 中填写服务地址")

        # 依次尝试每个 API

        for api_url in self.api_list:
            try:
                time = datetime.datetime.now().timestamp()
                response = await CLIENT.post(
                    f"{api_url}/simulate",
                    json=query_data,
                    timeout=timeout,
                    headers=(
                        {"X-Client-Key": mzq_config.client_key}
                        if mzq_config.client_key
                        else {}
                    ),
                )
                response.raise_for_status()
                logger.info(
                    f"✓ 使用 API {api_url} 请求成功, 耗时 {datetime.datetime.now().timestamp() - time:.2f}s"
                )
                return [BattleResponseDTO(**res) for res in response.json()]
            except Exception as e:
                traceback.print_exc()
                logger.warning(f"✗ API {api_url} 请求失败: {str(e)}")
                continue

        raise APIError("所有 API 请求失败")

    async def run_simulate_battle(
        self,
        user_ids: List[List[int]],
        enemy_ids: List[List[int]],
        simulations_per_team: int = 10,
    ) -> List[Optional[MzqBattleResult]]:
        """每个队伍组合模拟N次，统计胜率"""

        # 构建请求列表，每个队伍组合一个请求，使用 RepeatCount 指定重复次数
        all_requests = [
            BattleRequestDTO(
                PlayerList=[UnitDTO(unitId=uid) for uid in user_team],
                EnemyList=[UnitDTO(unitId=eid) for eid in enemy_team],
                GuildEnemyList=[],
                UBExecTimeList=[],
                SemanUBExecTimeList=[],
                ToMaxUnitAttr=True,
                IsAutoMode=True,
                IsSetMode=False,
                IsSemanMode=False,
                IsGuildBattle=False,
                Settings=GuildRandomDataDTO(),
                RepeatCount=simulations_per_team,
                TalentSkillLevels=mzq_config.default_progression.talent_skill_levels,
                TalentSkillNodeLevels=mzq_config.default_progression.talent_skill_node_levels,
                MasterSkillNodeLevels=mzq_config.default_progression.master_skill_node_levels,
                RoleMastery=mzq_config.default_progression.role_mastery,
            ).dict()
            for user_team, enemy_team in zip(user_ids, enemy_ids)
        ]
        # 定义响应处理器

        results_data = await self.query(
            query_data=all_requests,
            timeout=mzq_config.timeout * len(all_requests),
        )

        results_stats = {
            idx: {
                "win_count": 0,
                "lose_count": 0,
                "timeout_count": 0,
                "win_frames": [],
                "lose_frames": [],
            }
            for idx in range(len(user_ids))
        }
        # 统计每个队伍组合的结果，现在使用 RepeatCount 返回的结果列表
        for idx, result_data in enumerate(results_data):
            if not result_data:
                logger.info(f"✗ 战斗请求无响应，跳过统计第 {idx+1} 组")
                continue
            if result_data.Success:
                if result_list := (result_data.ResultList or [result_data.Result]):
                    battle_frames_list = result_data.BattleFramesList or [
                        result_data.BattleFrames
                    ]
                    for frames, result_code in zip(battle_frames_list, result_list):
                        if result_code == eBattleResult.win:  # 胜利
                            results_stats[idx]["win_count"] += 1
                            results_stats[idx]["win_frames"].append(frames)
                        elif result_code == eBattleResult.lose:  # 失败
                            results_stats[idx]["lose_count"] += 1
                            results_stats[idx]["lose_frames"].append(frames)
                        elif result_code == eBattleResult.timeout:  # 超时
                            results_stats[idx]["timeout_count"] += 1
                        else:
                            logger.warning(
                                f"✗ 第 {idx+1} 组战斗返回未知结果代码: {result_code}"
                            )

        # 生成最终结果
        results = []
        for idx, (user_team, enemy_team) in enumerate(zip(user_ids, enemy_ids)):
            stats = results_stats[idx]

            if stats["win_count"] + stats["lose_count"] + stats["timeout_count"] > 0:
                battle_frames = (
                    int(sum(stats["win_frames"]) / stats["win_count"])
                    if stats["win_count"] > 0
                    else (
                        int(sum(stats["lose_frames"]) / stats["lose_count"])
                        if stats["lose_count"] > 0
                        else 90 * 60
                    )  # 如果没有胜利和失败，则使用最大等待时间作为平均帧数
                )
                result = MzqBattleResult(
                    enemies=enemy_team,
                    attackers=user_team,
                    battle_frames=battle_frames,
                    win_count=stats["win_count"],
                    lose_count=stats["lose_count"],
                    timeout_count=stats["timeout_count"],
                )
                results.append(result)
                logger.info(
                    f"✓ 第 {idx+1} 组战斗完成: 胜{stats['win_count']}/负{stats['lose_count']}/超时{stats['timeout_count']} "
                    f"胜率{result.win_rate:.1%}"
                )
            else:
                logger.warning(f"✗ 第 {idx+1} 组战斗全部失败")

        logger.info(f"✓ 批量战斗完成，共 {len(results)} 组")
        return results

    async def get_default_development(self) -> VersionResponseDTO:
        """获取默认练度信息"""
        request = [
            BattleRequestDTO(
                PlayerList=[UnitDTO(unitId=170101)],
                EnemyList=[UnitDTO(unitId=170101)],
                GuildEnemyList=[],
                UBExecTimeList=[],
                SemanUBExecTimeList=[],
                ToMaxUnitAttr=True,
                IsAutoMode=True,
                IsSetMode=False,
                IsSemanMode=False,
                IsGuildBattle=False,
                RepeatCount=1,
                TalentSkillLevels=mzq_config.default_progression.talent_skill_levels,
                TalentSkillNodeLevels=mzq_config.default_progression.talent_skill_node_levels,
                MasterSkillNodeLevels=mzq_config.default_progression.master_skill_node_levels,
                RoleMastery=mzq_config.default_progression.role_mastery,
            ).dict()
        ]

        result_data = await self.query(
            query_data=request,
            timeout=mzq_config.timeout,
        )
        result_data = result_data[0]
        if result_data.Success:
            data = result_data.PlayerList[0] if result_data.PlayerList else None
            if not data:
                raise APIError("API 返回成功但没有玩家数据")
            version_info = VersionResponseDTO(
                PlayerLevel=data.level,
                PlayerRank=f"{data.rank}-{len(data.equipLevel)-len([e for e in data.equipLevel if e == -1])}",
                PlayerUniqueEqLv=data.uniqueEqLv,
                TalentLevel=result_data.TalentLevel,
                TalentSkill=result_data.TalentSkill,
                TeamSkill=result_data.TeamSkill,
            )
            logger.info("✓ 获取默认练度信息成功")
            return version_info


mzq_query = Query()
