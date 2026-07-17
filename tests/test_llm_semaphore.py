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
