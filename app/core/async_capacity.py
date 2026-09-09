# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Process-local admission shared safely across threads and asyncio loops."""

from __future__ import annotations

import asyncio
from collections import deque
from concurrent.futures import Future
from threading import Lock


class ProcessCapacity:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._available = capacity
        self._lock = Lock()
        self._waiters: deque[Future[None]] = deque()

    def try_acquire(self) -> bool:
        with self._lock:
            if not self._available:
                return False
            self._available -= 1
            return True

    async def acquire(self) -> None:
        with self._lock:
            if self._available:
                self._available -= 1
                return
            waiter: Future[None] = Future()
            self._waiters.append(waiter)
        try:
            await asyncio.wrap_future(waiter)
        except asyncio.CancelledError:
            # Cancellation may race with a completed transfer. Return a granted
            # slot; discard an ungranted waiter even if the holder is long-lived.
            if not waiter.cancel():
                self.release()
            else:
                with self._lock:
                    try:
                        self._waiters.remove(waiter)
                    except ValueError:
                        pass  # A concurrent release already skipped it.
            raise

    def release(self) -> None:
        with self._lock:
            while self._waiters:
                waiter = self._waiters.popleft()
                if waiter.set_running_or_notify_cancel():
                    waiter.set_result(None)
                    return
            self._available += 1
