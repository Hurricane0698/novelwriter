"""Actual task cancellation and bounded admission, including waiter races."""

import asyncio
import threading

import pytest

from app.core.copilot.sync_runtime import SyncExecutionChannel, check_sync_cancelled


async def wait_started(event):
    async with asyncio.timeout(2):
        while not event.is_set():
            await asyncio.sleep(0.001)


@pytest.mark.asyncio
async def test_cancellation_drains_worker_and_prevents_later_write():
    channel = SyncExecutionChannel(max_workers=1)
    started, release, closed = threading.Event(), threading.Event(), threading.Event()
    writes = []

    def work():
        try:
            started.set()
            assert release.wait(2)
            check_sync_cancelled()
            writes.append("persisted")
        finally:
            closed.set()

    task = asyncio.create_task(channel.run(work))
    try:
        await wait_started(started)
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()  # repeated shutdown cancellation must not abandon ownership
        await asyncio.sleep(0.01)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()
        assert writes == []
        assert await channel.run(lambda: "available") == "available"
    finally:
        release.set()
        channel._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_channel_bounds_running_work_and_discards_cancelled_waiters():
    channel = SyncExecutionChannel(max_workers=2)
    release = threading.Event()
    both_started = threading.Event()
    started = []
    active = peak = 0
    lock = threading.Lock()

    def work(index):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            started.append(index)
            if len(started) == 2:
                both_started.set()
        try:
            assert release.wait(2)
            return index
        finally:
            with lock:
                active -= 1

    tasks = [asyncio.create_task(channel.run(work, index)) for index in range(7)]
    try:
        await wait_started(both_started)
        tasks[3].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[3]
        assert len(started) == 2
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert peak == 2
        assert 3 not in started
        assert [result for result in results if isinstance(result, int)] == [
            0,
            1,
            2,
            4,
            5,
            6,
        ]
    finally:
        release.set()
        channel._executor.shutdown(wait=True)
