"""Cancelled requests release admission records while a provider is still busy."""

import asyncio
from concurrent.futures import Future
import gc
import weakref

import pytest

from app.core import async_capacity


@pytest.mark.asyncio
async def test_cancelled_admissions_do_not_accumulate_behind_long_lived_holder(monkeypatch):
    records = []

    def tracked_future():
        future = Future()
        records.append(weakref.ref(future))
        return future

    monkeypatch.setattr(async_capacity, "Future", tracked_future)
    capacity = async_capacity.ProcessCapacity(1)
    await capacity.acquire()
    for _ in range(40):
        task = asyncio.create_task(capacity.acquire())
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        del task
    await asyncio.sleep(0)
    gc.collect()
    assert len(records) == 40
    assert all(record() is None for record in records)
    assert not capacity.try_acquire()
    capacity.release()
    assert capacity.try_acquire()
