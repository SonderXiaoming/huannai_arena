from dataclasses import dataclass, field
import math
from random import random
import time
from typing import Dict, List, Optional

from .query.mzq.model import MzqBattleResult

from .query.pcrfans.model import AttackData

from .utils.tool import str_to_ids
from .constants import ArenaRecordType
from .database.table import MzqCache, PcrfansCacheData


# 轻量归一化参数与小偏移（不会产生显著性能开销）
# PCRFANS_SCALE: 预计 pcrfans cal_socre 的典型量级（用于线性缩放到 0-100）
# MZQ_BASE_MAX: mzq 的最大可能基础分（win_rate*100 + time_score），用于缩放到 0-100
PCRFANS_SCALE = 3.0
MZQ_BASE_MAX = 110.0

SMALL_OFFSETS = {
    ArenaRecordType.mzq: 6.0,
    ArenaRecordType.pcrfans: 16.0,
    ArenaRecordType.mzq_approximate: 4.0,
    ArenaRecordType.pcrfans_approximate: 32.0,
    ArenaRecordType.mzq_often_used: 2.0,
    ArenaRecordType.pcrfans_often_used: 1.0,
    ArenaRecordType.pcrfans_cache: 16.0,
    ArenaRecordType.pcrfans_old_cache: 16.0,
    ArenaRecordType.placehodlder: -1000,
}


@dataclass
class FormatSolution:
    id: Optional[int] = None
    atk: List[int] = field(default_factory=list)
    up: int = 0
    down: int = 0
    timestamp: int = 0
    cost_time: Optional[float] = None
    win_count: int = 0
    lose_count: int = 0
    timeout_count: int = 0

    @property
    def win_rate(self) -> float:
        total = self.win_count + self.lose_count + self.timeout_count
        return self.win_count / total if total > 0 else 0.0

    @classmethod
    def from_data(cls, data: object) -> "FormatSolution":
        if isinstance(data, PcrfansCacheData):
            return cls(
                id=data.id,
                atk=str_to_ids(data.attackers),
                up=data.up,
                down=data.down,
                timestamp=data.timestamp,
            )
        elif isinstance(data, AttackData):
            return cls(
                atk=data.atk,
                up=data.up,
                down=data.down,
                timestamp=int(time.time()),
            )
        elif isinstance(data, MzqCache):
            return cls(
                id=data.id,
                atk=str_to_ids(data.attackers),
                up=0,
                down=0,
                timestamp=data.timestamp,
                cost_time=data.battle_frames / 60,
                win_count=data.win_count,
                lose_count=data.lose_count,
                timeout_count=data.timeout_count,
            )
        elif isinstance(data, MzqBattleResult):
            return cls(
                atk=data.attackers,
                up=0,
                down=0,
                timestamp=int(time.time()),
                cost_time=data.battle_frames / 60,
                win_count=data.win_count,
                lose_count=data.lose_count,
                timeout_count=data.timeout_count,
            )


@dataclass
class ArenaQueryRecord:
    type: ArenaRecordType
    enemies: List[int] = field(default_factory=list)
    replace: Dict[int, int] = field(default_factory=dict)
    solution: Optional[FormatSolution] = None

    def cal_socre(self) -> int:
        val_1 = (
            self.solution.up / (self.solution.down + self.solution.up + 0.0001) * 2 - 1
        )  # 赞踩比占比 [-1, 1]
        val_2 = math.log(
            self.solution.up + self.solution.down + 0.01, 100
        )  # 置信度占比（log(100)）[-1,+inf]
        return val_1 + val_2 + random() / 1000  # 阵容推荐度权值

    @property
    def score(self) -> float:
        if self.type in [ArenaRecordType.pcrfans, ArenaRecordType.pcrfans_cache]:
            base = self.cal_socre()
            norm = base / PCRFANS_SCALE * 100
            return norm + SMALL_OFFSETS.get(self.type, 0)
        elif self.type == ArenaRecordType.pcrfans_old_cache:
            # 数据年龄(天)
            age_days = (time.time() - self.solution.timestamp) / 86400
            decay_factor = math.exp(-0.01 * (age_days - 5))  # 每天衰减约18%
            base = self.cal_socre() * decay_factor
            norm = base / PCRFANS_SCALE * 100
            return norm + SMALL_OFFSETS.get(self.type, 0)
        elif self.type == ArenaRecordType.pcrfans_approximate:
            base = self.cal_socre() * 0.75
            norm = base / PCRFANS_SCALE * 100
            return norm + SMALL_OFFSETS.get(self.type, 0)
        elif self.type == ArenaRecordType.pcrfans_often_used:
            base = self.cal_socre() * 0.5
            norm = base / PCRFANS_SCALE * 100
            return norm + SMALL_OFFSETS.get(self.type, 0)
        elif self.type == ArenaRecordType.mzq:
            # 胜率优先，然后考虑战斗时长
            win_rate_score = self.solution.win_rate * 100  # 0-100分
            time_score = max(0, 10 - (self.solution.cost_time or 0) / 1000)  # 0-10分
            base = win_rate_score + time_score
            norm = base / MZQ_BASE_MAX * 100
            return norm + SMALL_OFFSETS.get(self.type, 0)
        elif self.type == ArenaRecordType.mzq_approximate:
            # 近似解打折
            win_rate_score = self.solution.win_rate * 100 * 0.7
            time_score = max(0, 10 - (self.solution.cost_time or 0) / 1000) * 0.7
            base = win_rate_score + time_score
            norm = base / MZQ_BASE_MAX * 100
            return norm + SMALL_OFFSETS.get(self.type, 0)
        elif self.type == ArenaRecordType.mzq_often_used:
            # 高频解，折扣更大
            win_rate_score = self.solution.win_rate * 100 * 0.6
            time_score = max(0, 10 - (self.solution.cost_time or 0) / 1000) * 0.6
            base = win_rate_score + time_score
            norm = base / MZQ_BASE_MAX * 100
            return norm + SMALL_OFFSETS.get(self.type, 0)
        elif self.type == ArenaRecordType.placehodlder:
            return -1000
