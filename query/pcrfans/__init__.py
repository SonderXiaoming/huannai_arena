import asyncio
import time
import traceback
import json
from random import choices
import string

from loguru import logger

from .utils import sign
from ...constants import CLIENT
from ...setting import pcrfans_config
from .model import AttackData, PcrfansResponse
from typing import List

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    "Referer": "https://pcrdfans.com/",
    "Origin": "https://pcrdfans.com",
    "Accept": "*/*",
    "Content-Type": "application/json; charset=utf-8",
    "Authorization": "",
    "Host": "api.pcrdfans.com",
}

digits_36 = string.digits + string.ascii_lowercase
lock = asyncio.Lock()


async def pcrfans_query(_def, page, region, sort) -> List[AttackData]:
    data = {
        "def": _def,
        "language": 0,
        "nonce": "".join(choices(digits_36, k=16)),
        "page": page,
        "region": region,
        "sort": sort,
        "ts": int(time.time()),
    }

    if pcrfans_config.need_sign:
        data["_sign"] = sign(
            json.dumps(data, ensure_ascii=False).replace(" ", ""),
            data["nonce"],
        )
    try:
        if pcrfans_config.need_lock:
            async with lock:
                result = await CLIENT.post(
                    pcrfans_config.api,
                    headers=HEADERS,
                    data=json.dumps(data, ensure_ascii=False)
                    .replace(" ", "")
                    .encode("utf8"),
                    timeout=5,
                )
        else:
            result = await CLIENT.post(
                pcrfans_config.api,
                headers=HEADERS,
                data=json.dumps(data, ensure_ascii=False)
                .replace(" ", "")
                .encode("utf8"),
                timeout=5,
            )

        result.raise_for_status()
        result = result.json()
        if result.get("code"):
            return []
        result = PcrfansResponse(**result)
        return [
            AttackData(
                atk=[item.id for item in res.atk],
                **{"def": [item.id for item in res.def_]},
                up=res.up,
                down=res.down,
            )
            for res in result.data.result
        ]
    except Exception as e:
        traceback.print_exc()
        logger.error(f"✗ pcrfans查询失败: {str(e)}")
        return []
