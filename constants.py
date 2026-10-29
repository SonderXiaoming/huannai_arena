from enum import Enum
from pathlib import Path
from httpx import AsyncClient


CLIENT = AsyncClient()

FILE_PATH = Path(__file__).parent / "resources"
IMG_PATH = FILE_PATH / "img"
DATA_PATH = FILE_PATH / "data"
FONT_PATH = FILE_PATH / "font"

DATA_PATH.mkdir(parents=True, exist_ok=True)


CQ_PATTERN = (
    r"(?i)\[CQ:image,"
    r"(?=[^\]]*\bfile=([^,\]]+))"
    r"(?=[^\]]*\burl=([^,\]]+))"
    r"[^\]]*\]"
)
UNIT_PATTERN = r"^icon_unit_(\d{6}).png$"


class RoleMasteryType(Enum):
    attack = 1
    break_defense = 2
    enhance = 3
    debuff = 4
    reinforce = 5
    heal = 6
    tank = 7
    disturbance = 8
    unknown = 9

    @property
    def name(self) -> str:
        if self == RoleMasteryType.attack:
            return "攻击"
        elif self == RoleMasteryType.break_defense:
            return "破防"
        elif self == RoleMasteryType.enhance:
            return "增益"
        elif self == RoleMasteryType.debuff:
            return "减益"
        elif self == RoleMasteryType.reinforce:
            return "强化"
        elif self == RoleMasteryType.heal:
            return "治疗"
        elif self == RoleMasteryType.tank:
            return "坦克"
        elif self == RoleMasteryType.disturbance:
            return "干扰"
        else:
            return "未知"

    @staticmethod
    def from_value(value: int) -> "RoleMasteryType":
        value = value % 1000 // 100
        if value == 1:
            return RoleMasteryType.attack
        elif value == 2:
            return RoleMasteryType.break_defense
        elif value == 3:
            return RoleMasteryType.enhance
        elif value == 4:
            return RoleMasteryType.debuff
        elif value == 5:
            return RoleMasteryType.reinforce
        elif value == 6:
            return RoleMasteryType.heal
        elif value == 7:
            return RoleMasteryType.tank
        elif value == 8:
            return RoleMasteryType.disturbance
        else:
            return RoleMasteryType.unknown


class ArenaQueryType:
    pcrfans = "pcrfans"
    mzq = "mzq"


class ArenaRecordType:
    pcrfans = "pcrfans"
    pcrfans_cache = "pcrfans_cache"
    pcrfans_old_cache = "pcrfans_old_cache"
    pcrfans_approximate = "pcrfans_approximate"
    pcrfans_often_used = "pcrfans_often_used"

    mzq = "mzq"
    mzq_approximate = "mzq_approximate"
    mzq_often_used = "mzq_often_used"

    placehodlder = "placeholder"
