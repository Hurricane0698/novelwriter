"""Cancel real SQL work before commit and observe the rolled-back database."""

import asyncio
from datetime import timedelta
import threading

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.copilot.run_state import claim_run_for_execution, fail_run, utcnow_naive
from app.core.copilot.sync_runtime import SyncExecutionChannel
from app.models import CopilotRun, QuotaReservation, User
from tests.copilot.test_resource_lifecycle import (
    _seed_runtime,
    runtime_database as runtime_database,
)
from tests.copilot.test_sync_runtime import wait_started


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", [
    "claim-after-select",
    "claim-after-update",
    "stale-claim-after-quota-select",
    "fail-after-quota-select",
])
async def test_cancelled_claim_and_failure_leave_no_committed_transition(runtime_database, boundary):
    engine, factory, _ = runtime_database
    _, run_id, _, _, _ = _seed_runtime(factory)
    failure = boundary == "fail-after-quota-select"
    with factory() as db:
        db.add(User(id=1, username="quota-owner", hashed_password="unused", generation_quota=1))
        reservation = QuotaReservation(user_id=1, reserved_count=1, charged_count=0, lease_token="test")
        db.add(reservation)
        db.flush()
        reservation_id = reservation.id
        run = db.query(CopilotRun).filter_by(run_id=run_id).one()
        run.quota_reservation_id = reservation_id
        if failure:
            run.status, run.lease_owner = "running", "worker"
        elif boundary == "stale-claim-after-quota-select":
            run.lease_expires_at = utcnow_naive() - timedelta(seconds=60)
        db.commit()

    started, release = threading.Event(), threading.Event()
    statements = []

    def pause_after_sql(_conn, _cursor, sql, *_args):
        statements.append(sql)
        matches = (
            sql.startswith("UPDATE copilot_runs") if boundary == "claim-after-update"
            else sql.startswith("SELECT") and (
                "FROM copilot_runs" in sql if boundary == "claim-after-select"
                else "FROM quota_reservations" in sql
            )
        )
        if matches and not started.is_set():
            started.set()
            assert release.wait(2)

    def work():
        with factory() as db:
            if failure:
                run = db.query(CopilotRun).filter_by(run_id=run_id).one()
                fail_run(db, run, "synthetic", "failure", worker_id="worker")
            else:
                claim_run_for_execution(db, run_id=run_id, worker_id="worker")

    channel = SyncExecutionChannel(max_workers=1)
    event.listen(engine, "after_cursor_execute", pause_after_sql)
    task = asyncio.create_task(channel.run(work))
    try:
        await wait_started(started)
        assert engine.pool.checkedout() == 1
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        event.remove(engine, "after_cursor_execute", pause_after_sql)
        channel._executor.shutdown(wait=True)

    assert engine.pool.checkedout() == 0
    if boundary == "claim-after-update":
        assert any(sql.startswith("UPDATE copilot_runs") for sql in statements)
    with factory() as db:
        run = db.query(CopilotRun).filter_by(run_id=run_id).one()
        assert run.status == ("running" if failure else "queued")
        assert run.lease_owner == ("worker" if failure else None)
        assert run.error is None and run.workspace_json is None
        reservation = db.get(QuotaReservation, reservation_id)
        assert reservation.released_at is None and reservation.charged_count == 0
        assert db.get(User, 1).generation_quota == 1


@pytest.mark.asyncio
async def test_cancel_after_database_commit_drains_without_claiming_rollback(runtime_database):
    engine, factory, _ = runtime_database
    _, run_id, _, _, _ = _seed_runtime(factory)
    committed, release = threading.Event(), threading.Event()

    def after_commit(db):
        if db.bind is engine and not committed.is_set():
            committed.set()
            assert release.wait(2)

    def claim():
        with factory() as db:
            claim_run_for_execution(db, run_id=run_id, worker_id="worker")

    channel = SyncExecutionChannel(max_workers=1)
    event.listen(Session, "after_commit", after_commit)
    task = asyncio.create_task(channel.run(claim))
    try:
        await wait_started(committed)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        event.remove(Session, "after_commit", after_commit)
        channel._executor.shutdown(wait=True)

    assert engine.pool.checkedout() == 0
    with factory() as db:
        run = db.query(CopilotRun).filter_by(run_id=run_id).one()
        assert run.status == "running" and run.lease_owner == "worker"
