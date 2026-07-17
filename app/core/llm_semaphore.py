# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Semaphore-based concurrency gate for outbound LLM API calls.

Single-process architecture means asyncio.Semaphore is sufficient.
When the semaphore is full, new requests get HTTP 503 immediately
rather than queuing unboundedly and overwhelming the LLM provider.
"""

import asyncio
from time import perf_counter

from fastapi import HTTPException

from app.config import get_settings

_global_semaphore: asyncio.Semaphore | None = None
_background_lane_semaphore: asyncio.Semaphore | None = None
_semaphore_limits: tuple[int, int] | None = None


def _get_semaphore_limits() -> tuple[int, int]:
    settings = get_settings()
    return (
        int(settings.max_concurrent_llm_calls),
        int(settings.max_background_concurrent_llm_calls),
    )


def _ensure_semaphores() -> tuple[asyncio.Semaphore, asyncio.Semaphore]:
    global _global_semaphore, _background_lane_semaphore, _semaphore_limits
    limits = _get_semaphore_limits()
    if (
        _global_semaphore is None
        or _background_lane_semaphore is None
        or _semaphore_limits != limits
    ):
        total_limit, background_limit = limits
        _global_semaphore = asyncio.Semaphore(total_limit)
        _background_lane_semaphore = asyncio.Semaphore(background_limit)
        _semaphore_limits = limits
    return _global_semaphore, _background_lane_semaphore


def _get_global_semaphore() -> asyncio.Semaphore:
    global_sem, _background_sem = _ensure_semaphores()
    return global_sem


def _get_background_lane_semaphore() -> asyncio.Semaphore:
    _global_sem, background_sem = _ensure_semaphores()
    return background_sem


async def acquire_llm_slot() -> None:
    """Try to acquire an LLM concurrency slot. Raises 503 if full."""
    sem = _get_global_semaphore()
    if sem.locked():
        raise HTTPException(
            status_code=503,
            detail="Server is busy with other generation requests. Please retry in a few seconds.",
            headers={"Retry-After": "5"},
        )
    await sem.acquire()


def release_llm_slot() -> None:
    """Release a previously acquired LLM concurrency slot."""
    _get_global_semaphore().release()


async def acquire_background_llm_slot_blocking() -> float:
    """Acquire a background LLM slot after passing the background lane.

    Background jobs must not consume unlimited provider concurrency while a
    user is actively waiting on continuation. The background lane caps how many
    worker-owned LLM calls may contend for the shared global semaphore.
    """

    started = perf_counter()
    background_sem = _get_background_lane_semaphore()
    global_sem = _get_global_semaphore()
    await background_sem.acquire()
    try:
        await global_sem.acquire()
    except BaseException:
        background_sem.release()
        raise
    return max(perf_counter() - started, 0.0)


def release_background_llm_slot() -> None:
    """Release a previously acquired background LLM slot."""
    _get_global_semaphore().release()
    _get_background_lane_semaphore().release()
