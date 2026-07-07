"""
Telegram message formatting helpers.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bot.services.proxy.checker import CheckStats


def progress_bar(pct: float, length: int = 12) -> str:
    filled = math.floor(pct / 100 * length)
    bar = "█" * filled + "░" * (length - filled)
    return bar


def eta_str(seconds: float) -> str:
    if seconds < 0 or math.isinf(seconds):
        return "—"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def progress_message(stats: CheckStats) -> str:
    bar = progress_bar(stats.progress_pct)
    return (
        f"<b>🔍 Checking proxies…</b>\n\n"
        f"<code>{bar}</code> {stats.progress_pct:.1f}%\n\n"
        f"📦 <b>Loaded:</b>   {stats.total:,}\n"
        f"✅ <b>Checked:</b>  {stats.checked:,}\n"
        f"🟢 <b>Working:</b>  {stats.working:,}\n"
        f"🔴 <b>Dead:</b>     {stats.dead:,}\n"
        f"⚡ <b>Speed:</b>    {stats.speed:.0f} proxies/sec\n"
        f"⏳ <b>ETA:</b>      {eta_str(stats.eta_seconds)}"
    )


def final_report(stats: CheckStats) -> str:
    fastest = f"{stats.fastest_ms:.0f}ms" if stats.fastest_ms < float('inf') else "—"
    slowest = f"{stats.slowest_ms:.0f}ms" if stats.slowest_ms else "—"
    status = "✅ Complete" if not stats.cancelled else "⚠️ Cancelled"
    return (
        f"<b>📊 {status}</b>\n\n"
        f"<b>Proxies</b>\n"
        f"  Total:     {stats.total:,}\n"
        f"  Working:   {stats.working:,}\n"
        f"  Dead:      {stats.dead:,}\n"
        f"  Auth fail: {stats.auth_failed:,}\n"
        f"  Timeout:   {stats.timed_out:,}\n"
        f"  Invalid:   {stats.invalid_format:,}\n\n"
        f"<b>By Protocol</b>\n"
        f"  HTTP:    {stats.http:,}\n"
        f"  HTTPS:   {stats.https:,}\n"
        f"  SOCKS4:  {stats.socks4:,}\n"
        f"  SOCKS5:  {stats.socks5:,}\n\n"
        f"<b>Performance</b>\n"
        f"  Avg latency: {stats.avg_latency_ms:.0f}ms\n"
        f"  Fastest:     {fastest}\n"
        f"  Slowest:     {slowest}\n"
        f"  Speed:       {stats.speed:.0f} p/s\n"
        f"  Elapsed:     {eta_str(stats.elapsed)}"
    )


def settings_message(cfg) -> str:  # noqa: ANN001
    return (
        f"<b>⚙️ Your Settings</b>\n\n"
        f"<b>Test URL:</b>     <code>{cfg.test_url}</code>\n"
        f"<b>Timeout:</b>      {cfg.timeout}s\n"
        f"<b>Concurrency:</b>  {cfg.concurrency}\n"
        f"<b>Max workers:</b>  {cfg.max_workers}\n"
        f"<b>Retries:</b>      {cfg.retries}\n"
    )
