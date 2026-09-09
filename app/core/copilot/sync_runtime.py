# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded synchronous work, with no worker escaping a cancelled Copilot run.

Only session factories and owned value snapshots cross this boundary. Every
database session is opened and closed by the synchronous callable itself.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
from threading import Event
from typing import Callable, TypeVar

from app.core.async_capacity import ProcessCapacity

_T = TypeVar("_T")
_cancel_event: ContextVar[Event | None] = ContextVar(
    "copilot_sync_cancel", default=None
)


class SyncWorkCancelled(BaseException):
    """Internal cooperative cancellation; never trigger the one-shot fallback."""


def check_sync_cancelled() -> None:
    event = _cancel_event.get()
    if event is not None and event.is_set():
        raise SyncWorkCancelled()


class SyncExecutionChannel:
    """Limit submissions across event loops, without blocking their threads.

    Waiting coroutines do not enter the executor queue. Cancellation while
    queued discards the waiter; cancellation while running signals the worker
    and drains it before releasing capacity or propagating CancelledError.
    """

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="copilot-sync"
        )
        self._capacity = ProcessCapacity(max_workers)

    async def run(self, function: Callable[..., _T], /, *args, **kwargs) -> _T:
        await self._capacity.acquire()
        cancelled = Event()

        def invoke() -> _T:
            _cancel_event.set(cancelled)
            check_sync_cancelled()
            return function(*args, **kwargs)

        try:
            future = asyncio.wrap_future(
                self._executor.submit(copy_context().run, invoke)
            )
            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                cancelled.set()
                # A database commit already in progress cannot be interrupted.
                # Keep ownership until it has finished and all sessions closed.
                while not future.done():
                    try:
                        await asyncio.shield(future)
                    except asyncio.CancelledError:
                        continue
                    except BaseException:
                        break
                if not future.cancelled():
                    future.exception()  # consume the cooperative stop or failure
                raise
        finally:
            self._capacity.release()


_channel = SyncExecutionChannel()


async def run_sync(function: Callable[..., _T], /, *args, **kwargs) -> _T:
    return await _channel.run(function, *args, **kwargs)
