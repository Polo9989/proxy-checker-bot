"""
Async SQLite database (aiosqlite) for persisting user settings.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import aiosqlite

from bot.services.proxy.checker import CheckerConfig
from bot.utils.logger import get_logger

log = get_logger(__name__)

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS user_settings (
    user_id     INTEGER PRIMARY KEY,
    timeout     REAL    DEFAULT 10.0,
    concurrency INTEGER DEFAULT 500,
    retries     INTEGER DEFAULT 2,
    test_url    TEXT    DEFAULT 'https://httpbin.org/ip',
    max_workers INTEGER DEFAULT 1000,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(_CREATE_SQL)
            await db.commit()
        log.info("database_ready", path=str(self._path))

    async def get_settings(self, user_id: int) -> CheckerConfig:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
        if row:
            return CheckerConfig(
                test_url=row["test_url"],
                timeout=row["timeout"],
                concurrency=row["concurrency"],
                retries=row["retries"],
                max_workers=row["max_workers"],
            )
        return CheckerConfig()  # defaults

    async def save_settings(self, user_id: int, cfg: CheckerConfig) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO user_settings (user_id, timeout, concurrency, retries, test_url, max_workers)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    timeout     = excluded.timeout,
                    concurrency = excluded.concurrency,
                    retries     = excluded.retries,
                    test_url    = excluded.test_url,
                    max_workers = excluded.max_workers,
                    updated_at  = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    cfg.timeout,
                    cfg.concurrency,
                    cfg.retries,
                    cfg.test_url,
                    cfg.max_workers,
                ),
            )
            await db.commit()
