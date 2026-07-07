"""
/stats and /cancel command handlers.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.proxy.job_manager import JobManager, JobStatus
from bot.utils.formatting import final_report, progress_message

router = Router(name="stats")


@router.message(Command("stats"))
async def cmd_stats(message: Message, jobs: JobManager) -> None:
    uid = message.from_user.id  # type: ignore[union-attr]
    job = jobs.get_job(uid)
    if not job:
        await message.answer("ℹ️ No recent job found. Start one with /check.")
        return

    if job.status == JobStatus.RUNNING and job.stats:
        await message.answer(progress_message(job.stats), parse_mode="HTML")
    elif job.stats:
        await message.answer(final_report(job.stats), parse_mode="HTML")
    else:
        await message.answer(f"Job status: {job.status.name}")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, jobs: JobManager) -> None:
    uid = message.from_user.id  # type: ignore[union-attr]
    if jobs.cancel_job(uid):
        await message.answer("🛑 Cancellation requested. Results so far will be saved.")
    else:
        await message.answer("ℹ️ No active job to cancel.")
