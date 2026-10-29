import logging
import sys
import types
from pathlib import Path
from typing import List, Optional, Type

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_DATABASE_ROOT = Path(__file__).resolve().parent


def _install_package_stubs() -> None:
    """脚本直跑时注册包桩，避免执行 huannai_arena/__init__.py（依赖 hoshino）。"""
    for name, path in (
        ("huannai_arena", _PACKAGE_ROOT),
        ("huannai_arena.database", _DATABASE_ROOT),
    ):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = [str(path)]
            sys.modules[name] = mod


if __package__ in (None, ""):
    _install_package_stubs()
    from huannai_arena.database.table import (
        ArenaModel,
        CommentSetting,
        MzqCache,
        MzqDetail,
        PcrfansCache,
        PcrfansCacheData,
        PcrfansDetail,
    )
else:
    from .table import (
        ArenaModel,
        CommentSetting,
        MzqCache,
        MzqDetail,
        PcrfansCache,
        PcrfansCacheData,
        PcrfansDetail,
    )

MIGRATION_MODELS: List[Type[ArenaModel]] = [
    # CommentSetting,
    PcrfansCache,
    PcrfansCacheData,
    PcrfansDetail,
    MzqCache,
    MzqDetail,
]

logger = logging.getLogger(__name__)

BATCH_SIZE = 500_000

SEQUENCE_TABLES = (
    "huannai_arena_mzq_cache",
    "huannai_arena_pcrfans_cache",
    "huannai_arena_pcrfans_cache_data",
    "huannai_arena_pcrfans_detail",
    "huannai_arena_mzq_detail",
)


def _sqlite_path_from_url(url: str) -> Optional[Path]:
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return None
    return Path(url[len(prefix) :])


async def _copy_table_in_batches(
    src_conn,
    dst_engine: AsyncEngine,
    table,
) -> int:
    """流式读取源表，按 BATCH_SIZE 分批写入目标库。返回迁移总行数。"""
    total = 0
    batch_no = 0
    stream = await src_conn.stream(select(table))
    async for partition in stream.partitions(BATCH_SIZE):
        rows = [dict(row._mapping) for row in partition]
        if not rows:
            continue
        batch_no += 1
        async with dst_engine.begin() as dst_conn:
            await dst_conn.execute(insert(table), rows)
        total += len(rows)
        logger.info(
            "表 %s 第 %d 批写入 %d 行（累计 %d）",
            table.name,
            batch_no,
            len(rows),
            total,
        )
    return total


async def _reset_pg_sequences(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for table_name in SEQUENCE_TABLES:
            await conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table_name}), 1))"
                )
            )


async def migrate_arena_to_pgsql(sqlite_url: str, pgsql_url: str) -> bool:
    """从 SQLite arena 库迁移表数据到 PostgreSQL。目标表已有数据则跳过该表。"""
    sqlite_path = _sqlite_path_from_url(sqlite_url)
    if sqlite_path and not sqlite_path.exists():
        logger.info("arena SQLite 文件不存在，跳过迁移: %s", sqlite_path)
        return False

    src_engine = create_async_engine(sqlite_url)
    dst_engine = create_async_engine(pgsql_url)
    migrated_any = False
    try:
        async with dst_engine.begin() as conn:
            await conn.run_sync(ArenaModel.metadata.create_all)

        async with src_engine.connect() as src_conn:
            for model in MIGRATION_MODELS:
                table = model.__table__
                async with dst_engine.connect() as dst_conn:
                    existing = await dst_conn.execute(
                        select(func.count()).select_from(table)
                    )
                    if existing.scalar_one() > 0:
                        logger.info("表 %s 已有数据，跳过", table.name)
                        continue

                total = await _copy_table_in_batches(src_conn, dst_engine, table)
                if not total:
                    continue

                migrated_any = True
                logger.info("已迁移表 %s，共 %d 行", table.name, total)

        if migrated_any:
            await _reset_pg_sequences(dst_engine)
        return migrated_any
    finally:
        await src_engine.dispose()
        await dst_engine.dispose()


if __name__ == "__main__":
    import asyncio

    if __package__ in (None, ""):
        _install_package_stubs()
        from huannai_arena.setting import db_config
    else:
        from ..setting import db_config

    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate_arena_to_pgsql(db_config.arena_url, db_config.arena_pgsql_url))
