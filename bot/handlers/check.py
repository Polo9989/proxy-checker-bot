"""
/check command handler.

Accepts:
  - text messages with proxy lists
  - .txt file uploads
Drives the full checker pipeline and streams progress back to the user.
"""
from __future__ import annotations

import asyncio
import io
import os
import time
from pathlib import Path
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    Document,
    Message,
)

from bot.config import settings
from bot.database.db import Database
from bot.services.proxy.checker import CheckStats
from bot.services.proxy.job_manager import JobManager, JobStatus
from bot.utils.formatting import final_report, progress_message
from bot.utils.logger import get_logger

log = get_logger(__name__)
router = Router(name="check")

# seconds between Telegram progress message edits
_PROGRESS_EDIT_INTERVAL = 3.0


class CheckFSM(StatesGroup):
    waiting_proxies = State()


# ── /check command ─────────────────────────────────────────────────────────────

@router.message(Command("check"))
async def cmd_check(message: Message, state: FSMContext, jobs: JobManager) -> None:
    if jobs.has_active_job(message.from_user.id):  # type: ignore[union-attr]
        await message.answer("⚠️ You already have a job running. Use /cancel first.")
        return
    await state.set_state(CheckFSM.waiting_proxies)
    await message.answer(
        "📋 <b>Send your proxy list.</b>\n\n"
        "You can:\n"
        "• Paste proxies directly (one per line)\n"
        "• Upload a <code>.txt</code> file\n\n"
        "Supports up to <b>100,000</b> proxies.",
        parse_mode="HTML",
    )


# ── file upload ────────────────────────────────────────────────────────────────

@router.message(CheckFSM.waiting_proxies, F.document)
async def receive_file(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: Database,
    jobs: JobManager,
) -> None:
    doc: Document = message.document  # type: ignore[assignment]
    if not doc.file_name or not doc.file_name.endswith(".txt"):
        await message.answer("❌ Only <code>.txt</code> files are supported.", parse_mode="HTML")
        return
    if doc.file_size and doc.file_size > settings.max_file_size_bytes:
        await message.answer(
            f"❌ File too large. Max {settings.max_file_size_mb} MB."
        )
        return

    await message.answer("📥 Downloading file…")
    file = await bot.get_file(doc.file_id)
    bio = io.BytesIO()
    await bot.download_file(file.file_path, bio)  # type: ignore[arg-type]
    bio.seek(0)
    try:
        raw_text = bio.read().decode("utf-8", errors="replace")
    except Exception:
        await message.answer("❌ Could not read the file. Ensure it is UTF-8 encoded.")
        return

    await state.clear()
    await _launch_check(message, raw_text, db, jobs, bot)


# ── pasted text ───────────────────────────────────────────────────────────────

@router.message(CheckFSM.waiting_proxies, F.text)
async def receive_text(
    message: Message,
    state: FSMContext,
    db: Database,
    jobs: JobManager,
    bot: Bot,
) -> None:
    raw_text = message.text or ""
    if "\n" not in raw_text and ":" not in raw_text:
        await message.answer("❌ No valid proxies detected. Please send a proper list.")
        return
    await state.clear()
    await _launch_check(message, raw_text, db, jobs, bot)


# ── core launch logic ─────────────────────────────────────────────────────────

async def _launch_check(
    message: Message,
    raw_text: str,
    db: Database,
    jobs: JobManager,
    bot: Bot,
) -> None:
    uid = message.from_user.id  # type: ignore[union-attr]
    cfg = await db.get_settings(uid)

    # Send initial progress message that we'll edit
    prog_msg = await message.answer("⏳ Parsing proxies…")

    last_edit = time.monotonic()

    def on_progress(stats: CheckStats) -> None:
        nonlocal last_edit
        now = time.monotonic()
        if now - last_edit < _PROGRESS_EDIT_INTERVAL:
            return
        last_edit = now
        asyncio.create_task(
            _safe_edit(bot, prog_msg.chat.id, prog_msg.message_id, progress_message(stats))
        )

    try:
        job = await jobs.start_job(
            user_id=uid,
            raw_text=raw_text,
            config=cfg,
            on_progress=on_progress,
            max_proxies=settings.max_proxies_per_user,
        )
    except RuntimeError as exc:
        await prog_msg.edit_text(f"❌ {exc}")
        return

    if job.stats and job.stats.total == 0:
        await prog_msg.edit_text("❌ No valid proxies found in your input.")
        return

    await prog_msg.edit_text(
        f"🚀 <b>Started!</b> Checking <b>{job.stats.total if job.stats else '?':,}</b> proxies…\n"
        f"Settings: timeout={cfg.timeout}s | concurrency={cfg.concurrency} | retries={cfg.retries}",
        parse_mode="HTML",
    )

    # wait for the job task
    if job.task:
        await asyncio.shield(job.task)

    # send final report
    stats = job.stats
    if stats is None:
        await message.answer("❌ Job failed before producing stats.")
        return

    report = final_report(stats)
    await message.answer(report, parse_mode="HTML")

    # send output files
    if job.output_paths:
        await message.answer("📁 <b>Output files:</b>", parse_mode="HTML")
        for cat, path in sorted(job.output_paths.items()):
            if path.exists() and path.stat().st_size > 0:
                content = path.read_bytes()
                await bot.send_document(
                    message.chat.id,
                    BufferedInputFile(content, filename=path.name),
                    caption=f"<code>{path.name}</code>",
                    parse_mode="HTML",
                )


async def _safe_edit(bot: Bot, chat_id: int, msg_id: int, text: str) -> None:
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
    except Exception:
        pass
