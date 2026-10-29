import base64
from io import BytesIO
import re
from typing import List
from hoshino.modules.priconne import chara

from ..constants import CLIENT
from PIL import Image
from ..errorclass import (
    NotEnoughUnitError,
    NotValidTeamError,
    TooManyUnitError,
    UnKnowUnitError,
    UnRelatedError,
)


async def get_pic(address):
    resp = await CLIENT.get(address, timeout=20)
    return resp.content


def outp_b64(outp_img: Image.Image) -> str:
    buf = BytesIO()
    outp_img.save(buf, format="PNG")
    base64_str = f"base64://{base64.b64encode(buf.getvalue()).decode()}"
    return f"[CQ:image,file={base64_str}]"


def ids_to_str(id_list: list[int]) -> str:
    return "".join(str(i) for i in sorted(id_list))


def str_to_ids(id_str: str, length: int = 6) -> list[int]:
    return [int(id_str[i : i + length]) for i in range(0, len(id_str), length)]


def short_id_to_long(short_id: int) -> int:
    """将短id转换为长id"""
    return short_id * 100 + 1


def long_id_to_short(long_id: int) -> int:
    """将长id转换为短id"""
    return long_id // 100


def names_to_ids(names: str) -> List[int]:
    units = re.sub(r"[?？，,_]", "", names)
    units, unknown = chara.roster.parse_team(units)
    if unknown:
        _, name, score = chara.guess_id(unknown)
        if score < 70 and not units:
            raise UnRelatedError()
        raise UnKnowUnitError(unknown, name, score)
    if len(units) > 5:
        raise TooManyUnitError()
    elif len(units) < 4:
        raise NotEnoughUnitError()
    if len(units) != len(set(units)):
        raise NotValidTeamError("编队中含重复角色")
    if any(chara.is_npc(i) for i in units):
        raise NotValidTeamError("编队中含未实装角色")
    return [short_id_to_long(unit_id) for unit_id in units]


def ids_to_names(units: List[int]) -> str:
    """将单位ID列表转换为角色名称字符串"""
    return "，".join(chara.fromid(long_id_to_short(uid)).name for uid in units)
