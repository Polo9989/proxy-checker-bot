"""
Proxy Checker Telegram Bot — main entrypoint.

Run with:
    python main.py
"""
from __future__ import annotations

import asyncio
import sys

try:
    import uvloop  # type: ignore

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass  # uvloop is optional but recommended

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.database.db import Database
from bot.handlers import get_router
from bot.middlewares import RateLimitMiddleware
from bot.services.proxy.job_manager import JobManager
from bot.utils.logger import get_logger, setup_logging

log = get_logger(__name__)


async def main() -> None:
    setup_logging(settings.log_level, settings.log_file)
    log.info("bot_starting", version="1.0.0")

    # ── Dependencies ─────────────────────────────────────────────────────────
    db = Database(settings.database_path)
    await db.init()

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    jobs = JobManager(settings.output_dir)

    # ── Bot & Dispatcher ─────────────────────────────────────────────────────
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Inject shared dependencies into every handler via middleware data
    dp.update.middleware(RateLimitMiddleware(max_calls=20, window_seconds=60))
    dp["db"] = db
    dp["jobs"] = jobs

    dp.include_router(get_router())

    log.info("polling_started")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        log.info("bot_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
