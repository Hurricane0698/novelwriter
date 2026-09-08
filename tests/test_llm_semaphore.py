import asyncio

import pytest
from fastapi import HTTPException

import app.core.llm_semaphore as llm_semaphore


def _configure_limits(monkeypatch, *, total: int, background: int) -> None:
    import app.config as config_mod
    from app.config import Settings

    monkeypatch.setattr(
        config_mod,
        "_settings_instance",
        Settings(
            max_concurrent_llm_calls=total,
            max_background_concurrent_llm_calls=background,
            _env_file=None,
        ),
    )
    monkeypatch.setattr(llm_semaphore, "_global_semaphore", None)
    monkeypatch.setattr(llm_semaphore, "_background_lane_semaphore", None)
    monkeypatch.setattr(llm_semaphore, "_semaphore_limits", None)


@pytest.mark.asyncio
async def test_background_lane_preserves_foreground_headroom(monkeypatch):
    _configure_limits(monkeypatch, total=2, background=1)

    await llm_semaphore.acquire_background_llm_slot_blocking()
    await llm_semaphore.acquire_llm_slot()

    with pytest.raises(HTTPException) as exc_info:
        await llm_semaphore.acquire_llm_slot()

    assert exc_info.value.status_code == 503

    llm_semaphore.release_llm_slot()
    llm_semaphore.release_background_llm_slot()


def test_background_gate_can_be_reused_by_successive_worker_event_loops(monkeypatch):
    _configure_limits(monkeypatch, total=2, background=1)

    async def run_pair():
        await llm_semaphore.acquire_background_llm_slot_blocking()
        queued = asyncio.create_task(
            llm_semaphore.acquire_background_llm_slot_blocking()
        )
        await asyncio.sleep(0)
        llm_semaphore.release_background_llm_slot()
        await asyncio.wait_for(queued, timeout=1)
        llm_semaphore.release_background_llm_slot()

    asyncio.run(run_pair())
    asyncio.run(run_pair())


@pytest.mark.asyncio
async def test_cancelled_handoff_returns_exactly_one_slot(monkeypatch):
    _configure_limits(monkeypatch, total=2, background=1)
    for _ in range(20):
        await llm_semaphore.acquire_background_llm_slot_blocking()
        queued = asyncio.create_task(
            llm_semaphore.acquire_background_llm_slot_blocking()
        )
        await asyncio.sleep(0)
        llm_semaphore.release_background_llm_slot()
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued

    await llm_semaphore.acquire_background_llm_slot_blocking()
    await llm_semaphore.acquire_llm_slot()
    with pytest.raises(HTTPException):
        await llm_semaphore.acquire_llm_slot()
    llm_semaphore.release_llm_slot()
    llm_semaphore.release_background_llm_slot()


def test_release_wakes_background_waiter_on_another_thread(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    _configure_limits(monkeypatch, total=2, background=1)
    asyncio.run(llm_semaphore.acquire_background_llm_slot_blocking())
    waiting = threading.Event()

    async def wait_and_release():
        asyncio.get_running_loop().call_soon(waiting.set)
        await llm_semaphore.acquire_background_llm_slot_blocking()
        llm_semaphore.release_background_llm_slot()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, wait_and_release())
        try:
            assert waiting.wait(2)
        finally:
            llm_semaphore.release_background_llm_slot()
        future.result(timeout=2)


@pytest.mark.asyncio
async def test_queued_background_wait_does_not_take_foreground_slot(monkeypatch):
    _configure_limits(monkeypatch, total=2, background=1)

    await llm_semaphore.acquire_background_llm_slot_blocking()

    async def waiter() -> float:
        return await llm_semaphore.acquire_background_llm_slot_blocking()

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0.05)

    await llm_semaphore.acquire_llm_slot()
    llm_semaphore.release_llm_slot()
    llm_semaphore.release_background_llm_slot()

    waited = await task
    assert waited >= 0.04
    llm_semaphore.release_background_llm_slot()
