"""
Simple per-user rate limit middleware (10 messages/min).
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message


class RateLimitMiddleware(BaseMiddleware):
    """Allow at most *max_calls* per *window_seconds* per user."""

    def __init__(self, max_calls: int = 10, window_seconds: float = 60.0) -> None:
        self._max_calls = max_calls
        self._window = window_seconds
        self._records: dict[int, list[float]] = defaultdict(list)

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        uid = event.from_user.id if event.from_user else 0
        now = time.monotonic()
        timestamps = self._records[uid]
        # Drop old entries
        self._records[uid] = [t for t in timestamps if now - t < self._window]
        if len(self._records[uid]) >= self._max_calls:
            await event.answer("⚠️ Too many requests. Please slow down.")
            return None
        self._records[uid].append(now)
        return await handler(event, data)
