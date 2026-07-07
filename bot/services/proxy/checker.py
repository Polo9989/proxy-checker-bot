"""
Async proxy checker.

Architecture
------------
Producer   → asyncio.Queue (ProxyEntry)
Consumers  → asyncio.Semaphore-limited workers that validate each proxy
Collector  → accumulates results, updates live stats
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Optional

import httpx

from bot.services.proxy.parser import ProxyEntry, ProxyProtocol
from bot.utils.logger import get_logger

log = get_logger(__name__)


# ── result & stats ─────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    entry: ProxyEntry
    working: bool
    latency_ms: float = 0.0
    public_ip: Optional[str] = None
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    error: Optional[str] = None
    auth_failed: bool = False
    timed_out: bool = False


@dataclass
class CheckStats:
    total: int = 0
    checked: int = 0
    working: int = 0
    dead: int = 0
    http: int = 0
    https: int = 0
    socks4: int = 0
    socks5: int = 0
    auth_failed: int = 0
    timed_out: int = 0
    invalid_format: int = 0
    total_latency_ms: float = 0.0
    fastest_ms: float = float("inf")
    slowest_ms: float = 0.0
    start_time: float = field(default_factory=time.monotonic)
    cancelled: bool = False

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def speed(self) -> float:
        """Proxies per second."""
        return self.checked / max(self.elapsed, 0.001)

    @property
    def eta_seconds(self) -> float:
        remaining = self.total - self.checked
        return remaining / max(self.speed, 0.001)

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.working, 1)

    @property
    def progress_pct(self) -> float:
        return self.checked / max(self.total, 1) * 100


# ── checker ───────────────────────────────────────────────────────────────────

@dataclass
class CheckerConfig:
    test_url: str = "https://httpbin.org/ip"
    timeout: float = 10.0
    concurrency: int = 500
    retries: int = 2
    max_workers: int = 1000


class ProxyChecker:
    """
    Bulk async proxy checker using a producer→queue→consumer pipeline.
    """

    def __init__(self, config: CheckerConfig) -> None:
        self.config = config
        self._cancel_event = asyncio.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    async def check_bulk(
        self,
        proxies: list[ProxyEntry],
        on_progress: Optional[Callable[[CheckStats], None]] = None,
        progress_interval: int = 50,
    ) -> tuple[list[CheckResult], CheckStats]:
        """
        Check all proxies and return (results, stats).

        Parameters
        ----------
        proxies           : list of ProxyEntry to check
        on_progress       : optional callback called every *progress_interval* checks
        progress_interval : how often to call on_progress
        """
        stats = CheckStats(total=len(proxies))
        results: list[CheckResult] = []
        results_lock = asyncio.Lock()
        self._cancel_event.clear()

        queue: asyncio.Queue[Optional[ProxyEntry]] = asyncio.Queue(
            maxsize=self.config.max_workers * 2
        )
        semaphore = asyncio.Semaphore(
            min(self.config.concurrency, self.config.max_workers)
        )

        async def producer() -> None:
            for proxy in proxies:
                if self._cancel_event.is_set():
                    break
                await queue.put(proxy)
            # poison pills
            for _ in range(self.config.max_workers):
                await queue.put(None)

        async def worker() -> None:
            while True:
                entry = await queue.get()
                if entry is None:
                    queue.task_done()
                    break
                if self._cancel_event.is_set():
                    queue.task_done()
                    continue
                async with semaphore:
                    result = await self._check_one(entry)
                async with results_lock:
                    results.append(result)
                    _update_stats(stats, result)
                    if on_progress and stats.checked % progress_interval == 0:
                        try:
                            on_progress(stats)
                        except Exception as exc:
                            log.warning("progress_callback_error", exc=str(exc))
                queue.task_done()

        n_workers = min(self.config.max_workers, len(proxies), self.config.concurrency)
        worker_tasks = [asyncio.create_task(worker()) for _ in range(n_workers)]
        producer_task = asyncio.create_task(producer())

        try:
            await asyncio.gather(producer_task, *worker_tasks)
        except asyncio.CancelledError:
            self._cancel_event.set()
            stats.cancelled = True
            producer_task.cancel()
            for t in worker_tasks:
                t.cancel()
            await asyncio.gather(producer_task, *worker_tasks, return_exceptions=True)

        if self._cancel_event.is_set():
            stats.cancelled = True

        return results, stats

    async def _check_one(self, entry: ProxyEntry) -> CheckResult:
        """Validate a single proxy with retry logic."""
        last_error: str = "unknown"
        auth_failed = False
        timed_out = False

        for attempt in range(self.config.retries + 1):
            try:
                result = await self._attempt(entry)
                return result
            except httpx.ProxyError as exc:
                last_error = str(exc)
                if "407" in last_error or "auth" in last_error.lower():
                    auth_failed = True
                    break  # auth won't fix itself on retry
            except httpx.TimeoutException:
                last_error = "timeout"
                timed_out = True
            except Exception as exc:
                last_error = str(exc)

            if attempt < self.config.retries:
                await asyncio.sleep(0.1 * (attempt + 1))

        return CheckResult(
            entry=entry,
            working=False,
            protocol=entry.protocol,
            error=last_error,
            auth_failed=auth_failed,
            timed_out=timed_out,
        )

    async def _attempt(self, entry: ProxyEntry) -> CheckResult:
        """Single HTTP probe through the proxy."""
        proxy_url = entry.url
        t0 = time.monotonic()

        transport = httpx.AsyncHTTPTransport(proxy=proxy_url)
        timeout = httpx.Timeout(self.config.timeout)

        async with httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(self.config.test_url)

        latency_ms = (time.monotonic() - t0) * 1000

        if response.status_code == 407:
            raise httpx.ProxyError("407 Proxy Authentication Required")

        public_ip: Optional[str] = None
        try:
            data = response.json()
            public_ip = data.get("origin") or data.get("ip")
            if public_ip and "," in public_ip:
                public_ip = public_ip.split(",")[0].strip()
        except Exception:
            pass

        return CheckResult(
            entry=entry,
            working=True,
            latency_ms=latency_ms,
            public_ip=public_ip,
            protocol=entry.protocol,
        )


# ── stat helpers ──────────────────────────────────────────────────────────────

def _update_stats(stats: CheckStats, result: CheckResult) -> None:
    stats.checked += 1
    if result.working:
        stats.working += 1
        stats.total_latency_ms += result.latency_ms
        if result.latency_ms < stats.fastest_ms:
            stats.fastest_ms = result.latency_ms
        if result.latency_ms > stats.slowest_ms:
            stats.slowest_ms = result.latency_ms
        proto = result.protocol
        if proto == ProxyProtocol.HTTP:
            stats.http += 1
        elif proto == ProxyProtocol.HTTPS:
            stats.https += 1
        elif proto == ProxyProtocol.SOCKS4:
            stats.socks4 += 1
        elif proto == ProxyProtocol.SOCKS5:
            stats.socks5 += 1
    else:
        stats.dead += 1
        if result.auth_failed:
            stats.auth_failed += 1
        elif result.timed_out:
            stats.timed_out += 1
