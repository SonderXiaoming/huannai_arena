from enum import IntEnum
from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class UnitDTO(BaseModel):
    # Field names intentionally match PCRCaculator.UnitData JSON fields
    enemyid: int = 0
    unitId: int = 0
    level: int = 100
    rarity: int = 3
    rank: int = 1
    equipLevel: List[int] = Field(default_factory=lambda: [-1, -1, -1, -1, -1, -1])
    skillLevel: List[int] = Field(default_factory=lambda: [1, 1, 1, 1])
    playLoveDic: dict = Field(default_factory=dict)
    uniqueEqLv: int = 0
    uniqueEq2Lv: int = -1
    exEquip: List[int] = Field(default_factory=lambda: [0, 0, 0])
    exEquipLevel: List[int] = Field(default_factory=lambda: [0, 0, 0])
    exEquipSubs: dict = Field(default_factory=dict)
    PrefabId: int = 0


class EnemyDetailDTO(BaseModel):
    unit_id: int = 0
    unit_name: Optional[str] = None
    prefab_id: int = 0
    motion_type: int = 0
    se_type: int = 0
    move_speed: int = 0
    search_area_width: int = 0
    atk_type: int = 0
    normal_atk_cast_time: float = 0.0
    cutin: int = 0
    visual_change_flag: int = 0
    comment: Optional[str] = None


class GuildEnemyDTO(BaseModel):
    enemy_id: int
    unit_id: int = 0
    name: Optional[str] = None
    level: int = 1
    rarity: int = 1
    promotion_level: int = 0
    union_burst_level: int = 0
    main_skill_lvs: List[int] = Field(default_factory=list)
    ex_skill_lvs: List[int] = Field(default_factory=list)
    resist_status_id: int = 0
    resist_variation_id: int = 0
    unique_equipment_flag_1: int = 0
    break_durability: int = 0
    virtual_hp: int = 0
    detailData: EnemyDetailDTO = Field(default_factory=EnemyDetailDTO)


class GuildRandomSpecialDataDTO(BaseModel):
    fixTimeExec: bool = False
    startFream: int = 0
    endFream: int = 0
    fixCountExec: bool = False
    countEcexNum: int = 0
    sourceNum: int = 0  # UnitType 枚举，建议用int或自定义Enum
    sourceSkillNum: int = 0  # skillNameType 枚举
    sourceSkillType: int = 0  # skillType 枚举
    targetNum: int = 0  # UnitType 枚举
    resuleType: int = 0  # ResultType 枚举


class GuildRandomDataDTO(BaseModel):
    DataName: str = "默认世界线"
    UseFixedRandomSeed: bool = False
    # RandomSeed: Optional[list] = None
    ForceNoCritical_player: bool = False
    ForceNoCritical_enemy: bool = False
    ForceIgnoreDodge_player: bool = False
    ForceIgnoreDodge_enemy: bool = False
    ForceCritical_player: bool = False
    randomSpecialDatas: Optional[List[GuildRandomSpecialDataDTO]] = Field(
        default_factory=list
    )


class BattleRequestDTO(BaseModel):
    CalcStats: int = 1
    PlayerList: List[UnitDTO]
    EnemyList: List[UnitDTO] = Field(default_factory=list)
    GuildEnemyList: List[GuildEnemyDTO] = Field(default_factory=list)
    UBExecTimeList: List[List[float]] = Field(default_factory=list)
    SemanUBExecTimeList: List[List[int]] = Field(default_factory=list)
    TalentFullInfo: bool = False
    IsTalentQuest: bool = False
    ToMaxUnitAttr: bool = False
    IsAutoMode: bool = True
    IsSetMode: bool = False
    IsSemanMode: bool = False
    IsGuildBattle: bool = True
    Settings: GuildRandomDataDTO = Field(default_factory=lambda: GuildRandomDataDTO())
    TalentSkillLevels: Optional[dict] = Field(default_factory=dict, default_value=None)
    TalentSkillNodeLevels: Optional[dict] = Field(
        default_factory=dict, default_value=None
    )
    MasterSkillNodeLevels: Optional[dict] = Field(
        default_factory=dict, default_value=None
    )
    RoleMastery: Dict[int, List[int]] = Field(default_factory=dict)
    BattleTime: int = 0
    WaveGroupId: int = 0
    SetToggles: List[bool] = Field(default_factory=list)
    RepeatCount: int = 2


class eBattleResult(IntEnum):
    win = 0
    lose = 1
    timeout = 2
    retire = 3
    unknown = -1


class StatsDTO(BaseModel):
    TotalDamage: int
    TotalMagicBuff: int
    TotalPhysicsBuff: int
    TotalMagicDebuff: int
    TotalPhysicsDebuff: int

    ScorePhysicsExpectation: int
    ScoreMagicExpectation: int

    PlayerTpGained: List[int]
    PlayerDamageList: List[int]
    PlayerNonUbDamageList: List[int]

    UBToleranceFrames: List[List[int]]
    UBTime: List[List[float]]


class BattleResponseDTO(BaseModel):
    PlayerList: Optional[List[UnitDTO]] = Field(default_factory=list)
    EnemyList: Optional[List[UnitDTO]] = Field(default_factory=list)

    Success: bool = False
    Message: Optional[str] = None

    Stats: Optional[StatsDTO] = Field(default_factory=StatsDTO)

    BattleFrames: int = 0
    CurrentSeed: int = 0

    TalentLevel: Optional[str] = None
    TalentSkill: Optional[str] = None
    TeamSkill: Optional[str] = None

    SemanUBNum: Optional[List[int]] = None

    Result: eBattleResult = eBattleResult.unknown

    ResultList: Optional[List[eBattleResult]] = Field(default_factory=list)
    BattleFramesList: Optional[List[int]] = Field(default_factory=list)
    CurrentSeedList: Optional[List[int]] = Field(default_factory=list)

    OnceResult: Optional[object] = None


class MzqBattleResult(BaseModel):
    enemies: List[int] = Field(default_factory=list)
    attackers: List[int] = Field(default_factory=list)
    battle_frames: int  # 最后一次模拟的帧数
    win_count: int = 0  # 胜利次数
    lose_count: int = 0  # 失败次数
    timeout_count: int = 0  # 超时次数

    @property
    def total_simulations(self) -> int:
        return self.win_count + self.lose_count + self.timeout_count

    @property
    def win_rate(self) -> float:
        total = self.total_simulations
        return self.win_count / total if total > 0 else 0.0


class VersionResponseDTO(BaseModel):
    PlayerLevel: int = 0
    PlayerRank: Optional[str] = None
    PlayerUniqueEqLv: int = 0
    TalentLevel: Optional[str] = None
    TalentSkill: Optional[str] = None
    TeamSkill: Optional[str] = None

    def __hash__(self):
        return hash(
            (
                self.PlayerLevel,
                self.PlayerRank or "",
                self.PlayerUniqueEqLv,
                self.TalentLevel or "",
                self.TalentSkill or "",
                self.TeamSkill or "",
            )
        )
