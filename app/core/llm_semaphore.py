# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Semaphore-based concurrency gate for outbound LLM API calls.

Single-process architecture means asyncio.Semaphore is sufficient.
When the semaphore is full, new requests get HTTP 503 immediately
rather than queuing unboundedly and overwhelming the LLM provider.
"""

import asyncio

from fastapi import HTTPException

from app.config import get_settings

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().max_concurrent_llm_calls)
    return _semaphore


async def acquire_llm_slot() -> None:
    """Try to acquire an LLM concurrency slot. Raises 503 if full."""
    sem = _get_semaphore()
    if sem.locked():
        raise HTTPException(
            status_code=503,
            detail="Server is busy with other generation requests. Please retry in a few seconds.",
            headers={"Retry-After": "5"},
        )
    await sem.acquire()


async def acquire_llm_slot_blocking() -> None:
    """Acquire an LLM concurrency slot, waiting if necessary.

    Use this for background tasks (e.g. bootstrap) where there is no
    HTTP request to return 503 to — the task simply waits its turn.
    """
    await _get_semaphore().acquire()


def release_llm_slot() -> None:
    """Release a previously acquired LLM concurrency slot."""
    _get_semaphore().release()
