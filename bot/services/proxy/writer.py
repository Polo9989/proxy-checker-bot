"""
Async file writer service.

Writes check results into categorised output files using aiofiles
and batch buffering to avoid excessive syscalls.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import aiofiles

from bot.services.proxy.checker import CheckResult
from bot.services.proxy.parser import ProxyProtocol
from bot.utils.logger import get_logger

log = get_logger(__name__)

# File categories keyed by their filename stem
_CATEGORIES = [
    "working",
    "dead",
    "http",
    "https",
    "socks4",
    "socks5",
    "auth_failed",
    "timeout",
]


def _result_to_line(result: CheckResult) -> str:
    """Serialise a result into a single output line."""
    entry = result.entry
    parts = [f"{entry.host}:{entry.port}"]
    if entry.username:
        parts.append(f"  # auth={entry.username}:{entry.password}")
    if result.latency_ms:
        parts.append(f"  # {result.latency_ms:.0f}ms")
    if result.public_ip:
        parts.append(f"  # ip={result.public_ip}")
    return f"{entry.host}:{entry.port}"


def _classify(result: CheckResult) -> list[str]:
    """Return list of category names this result belongs to."""
    cats: list[str] = []
    if result.working:
        cats.append("working")
        proto_name = result.protocol.value
        cats.append(proto_name)
    else:
        cats.append("dead")
        if result.auth_failed:
            cats.append("auth_failed")
        elif result.timed_out:
            cats.append("timeout")
    return cats


async def write_results(
    results: list[CheckResult],
    invalid_raw: list[str],
    output_dir: Path,
    job_id: str,
    batch_size: int = 500,
) -> dict[str, Path]:
    """
    Write all results into categorised files under *output_dir / job_id*.

    Returns a mapping of category → file path.
    """
    job_dir = output_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Accumulate lines per category
    buckets: dict[str, list[str]] = {c: [] for c in _CATEGORIES}
    buckets["invalid_format"] = []

    for result in results:
        line = _result_to_line(result)
        for cat in _classify(result):
            buckets[cat].append(line)

    for raw in invalid_raw:
        buckets["invalid_format"].append(raw.strip())

    # Write each category file asynchronously
    paths: dict[str, Path] = {}
    write_tasks = []
    for cat, lines in buckets.items():
        if lines:
            fpath = job_dir / f"{cat}.txt"
            paths[cat] = fpath
            write_tasks.append(_write_file(fpath, lines, batch_size))

    await asyncio.gather(*write_tasks)
    log.info("results_written", job_id=job_id, categories=list(paths.keys()))
    return paths


async def _write_file(path: Path, lines: list[str], batch_size: int) -> None:
    async with aiofiles.open(path, "w", encoding="utf-8") as fh:
        for i in range(0, len(lines), batch_size):
            chunk = "\n".join(lines[i : i + batch_size]) + "\n"
            await fh.write(chunk)
