from typing import Optional

from sqlalchemy import Index
from sqlalchemy.orm import registry
from sqlmodel import Field, SQLModel


class PCRModel(SQLModel, registry=registry()):
    pass


class UnitData(PCRModel, table=True):
    __tablename__ = "unit_data"
    unit_id: int = Field(primary_key=True)
    unit_name: str
    kana: Optional[str] = None
    prefab_id: Optional[int] = None
    prefab_id_battle: Optional[int] = None
    is_limited: Optional[int] = None
    rarity: Optional[int] = None
    motion_type: Optional[int] = None
    se_type: Optional[int] = None
    move_speed: Optional[int] = None
    search_area_width: Optional[int] = None
    atk_type: Optional[int] = None
    normal_atk_cast_time: Optional[float] = None
    cutin_1: Optional[int] = None
    cutin_2: Optional[int] = None
    cutin1_star6: Optional[int] = None
    cutin2_star6: Optional[int] = None
    guild_id: Optional[int] = None
    exskill_display: Optional[int] = None
    comment: Optional[str] = None
    only_disp_owned: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    original_unit_id: Optional[int] = None


class UnitTalent(PCRModel, table=True):
    __tablename__ = "unit_talent"
    setting_id: int = Field(primary_key=True)
    unit_id: int
    talent_id: int


class ArenaModel(SQLModel, registry=registry()):
    pass


class CommentSetting(ArenaModel, table=True):
    __tablename__ = "huannai_arena_commit_setting"
    id: int = Field(primary_key=True, default=1)
    group_id: int
    enable: bool = True


class PcrfansCache(ArenaModel, table=True):
    __tablename__ = "huannai_arena_pcrfans_cache"
    id: int = Field(primary_key=True)
    enemies: str
    region: int


class PcrfansCacheData(ArenaModel, table=True):
    __tablename__ = "huannai_arena_pcrfans_cache_data"
    id: int = Field(primary_key=True)
    attackers: str = Field(primary_key=True)
    timestamp: int
    up: int
    down: int


class PcrfansDetail(ArenaModel, table=True):
    __tablename__ = "huannai_arena_pcrfans_detail"
    id: int = Field(primary_key=True)
    unit: int = Field(primary_key=True)


class MzqCache(ArenaModel, table=True):
    __tablename__ = "huannai_arena_mzq_cache"
    __table_args__ = (
        Index("ix_mzq_cache_enemies_region", "enemies", "region"),
        Index("ix_mzq_cache_atk_enemies_region", "attackers", "enemies", "region"),
    )
    id: int = Field(primary_key=True, default=None)
    enemies: str
    attackers: str
    region: int
    timestamp: int
    win_count: int = 0  # 胜利次数
    lose_count: int = 0  # 失败次数
    timeout_count: int = 0  # 超时次数
    battle_frames: int

    @property
    def total_count(self) -> int:
        return self.win_count + self.lose_count + self.timeout_count

    @property
    def win_rate(self) -> float:
        return self.win_count / self.total_count if self.total_count > 0 else 0.0


class MzqDetail(ArenaModel, table=True):
    __tablename__ = "huannai_arena_mzq_detail"
    __table_args__ = (Index("ix_mzq_detail_unit", "unit"),)
    id: int = Field(primary_key=True, default=1)
    unit: int = Field(primary_key=True)
