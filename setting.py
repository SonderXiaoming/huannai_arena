from dataclasses import dataclass
import json
from typing import Dict, List
from pathlib import Path
from .constants import DATA_PATH


@dataclass
class PCRFANSConfig:
    api = "https://api.pcrdfans.com/x/v1/search"
    need_sign = True  # 可以配置第三方无sign版本
    need_lock = True  # 用api可以不用锁


@dataclass
class DefaultProgressionConfig:
    talent_skill_level = 1000

    talent_skill_node_levels = {638: 5}
    master_skill_node_levels = {100: 1}

    @property
    def role_mastery(self) -> Dict[int, List[int]]:
        return {
            10101: [5,2],
            10102: [5,2],
            10103: [5,2],
            10104: [5,2],
            10201: [5,2],
            10202: [5,2],
            10203: [5,2],
            10204: [5,2],
            10301: [5,2],
            10302: [5,2],
            10303: [5,2],
            10304: [5,2],
            10401: [5,2],
            10402: [5,2],
            10403: [5,2],
            10404: [5,2],
            10501: [5,2],
            10502: [5,2],
            10503: [5,2],
            10504: [5,2],
            10601: [5,2],
            10602: [5,2],
            10603: [5,2],
            10604: [5,2],
            10701: [5,2],
            10702: [5,2],
            10703: [5,2],
            10704: [5,2],
            10801: [5,2],
            10802: [5,2],
            10803: [5,2],
            10804: [5,2],
        }

    @property
    def talent_skill_levels(self) -> dict:
        return {
            1: self.talent_skill_level,
            2: self.talent_skill_level,
            3: self.talent_skill_level,
            4: self.talent_skill_level,
            5: self.talent_skill_level,
        }


@dataclass
class MzqConfig:
    api = []  # 在 config.json 中填写自己部署或申请到的摸轴器 API 地址
    timeout = 10  # 请求超时时间，单位秒
    poll_interval = 1.0  # 轮询间隔时间，单位秒
    max_wait = 120  # 最大等待时间，单位秒
    client_key = ""  # 可选的客户端密钥，在 config.json 中配置
    default_progression = DefaultProgressionConfig()


@dataclass
class dbConfig:  # 公主连结外部数据库配置

    pcr_url = f"sqlite+aiosqlite:///{DATA_PATH / 'pcr_data.db'}"  # 公主连结游戏数据库
    pcr_update_path = DATA_PATH / "pcr_data.db"  # 用于更新数据的数据库路径,可以为空

    arena_url = (
        f"sqlite+aiosqlite:///{DATA_PATH / 'arena.db'}"  # 竞技场数据数据库连接URL
    )
    use_pgsql = False  # 默认 SQLite；数据量大时推荐 PostgreSQL
    arena_pgsql_url = ""  # 在 config.json 中配置 postgresql+asyncpg:// 连接地址
    migrate_to_pgsql = False  # 为 True 时启动时尝试从 SQLite 迁移到 PostgreSQL
    arena_pool_size = 10  # PostgreSQL 连接池常驻连接数
    arena_max_overflow = 20  # PostgreSQL 连接池溢出连接数
    arena_pool_timeout = 60  # 等待可用连接的最长时间（秒）

    @property
    def effective_arena_url(self) -> str:
        return self.arena_pgsql_url if self.use_pgsql else self.arena_url


pcrfans_config = PCRFANSConfig()
mzq_config = MzqConfig()
db_config = dbConfig()


def load_local_config(path: Path) -> None:
    """只从本地配置读取部署信息；config.json 不应提交到 Git。"""
    if not path.is_file():
        return
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    targets = {"pcrfans": pcrfans_config, "mzq": mzq_config, "database": db_config}
    for section, values in config.items():
        if section not in targets or not isinstance(values, dict):
            raise ValueError(f"config.json 配置分组无效：{section}")
        target = targets[section]
        for name, value in values.items():
            if name.startswith("_") or name not in vars(type(target)) or isinstance(
                vars(type(target))[name], property
            ) or callable(vars(type(target))[name]):
                raise ValueError(f"config.json 配置项无效：{section}.{name}")
            setattr(target, name, value)


load_local_config(Path(__file__).with_name("config.json"))
