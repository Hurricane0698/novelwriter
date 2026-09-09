"""Persist one turn once, while recovering the exact full provider context."""

import hashlib
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.copilot.run_store import persist_running_workspace
from app.core.copilot.session_runtime import build_follow_up_conversation_messages
from app.core.copilot.workspace import Workspace
from app.database import Base
from app.models import CopilotRun, CopilotSession, Novel


@pytest.fixture
def history_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(Novel(id=1, title="Book", file_path="unused"))
        db.add(CopilotSession(
            id=1, session_id="session", novel_id=1, user_id=1,
            mode="research", scope="whole_book", signature="signature",
        ))
        prior = [CopilotRun(
            id=i, run_id=f"prior-{i}", copilot_session_id=1, novel_id=1, user_id=1,
            status="completed", prompt=f"OLD_HISTORY_{i}" * 1000, answer=f"old answer {i}",
        ) for i in (1, 2)]
        db.add_all(prior)
        db.add(CopilotRun(
            id=3, run_id="current", copilot_session_id=1, novel_id=1, user_id=1,
            status="running", prompt="new question", lease_owner="worker",
        ))
        db.flush()
        history = build_follow_up_conversation_messages(prior)
        db.commit()
    workspace = Workspace(
        messages=[{"role": "system", "content": "instructions"}, *history,
                  {"role": "user", "content": "new question and current world context"},
                  {"role": "assistant", "content": "", "tool_calls": [
                      {"id": "pending", "type": "function", "function": {"name": "read", "arguments": "{}"}},
                  ]}],
        pending_tool_calls=[{"id": "pending", "name": "read", "arguments": "{}"}],
        round_count=1,
    )
    # New preparation supplies these frozen references from the prior run rows.
    # Assign separately so the old writer reaches the behavioral failure below.
    workspace.history = {
        "run_ids": [1, 2],
        "message_count": len(history),
        "sha256": hashlib.sha256(json.dumps(
            history, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest(),
    }
    try:
        yield factory, workspace
    finally:
        engine.dispose()


def test_persisted_workspace_deduplicates_history_and_restores_pending_turn(history_database):
    factory, workspace = history_database
    assert persist_running_workspace(factory, "current", workspace, worker_id="worker")
    with factory() as db:
        run = db.get(CopilotRun, 3)
        stored = run.workspace_json
        assert "OLD_HISTORY" not in json.dumps(stored)
        assert stored["storage_version"] == 2
        from app.core.copilot.workspace import load_run_workspace
        restored = load_run_workspace(db, run)
    assert restored["messages"] == workspace.messages
    assert restored["pending_tool_calls"] == workspace.pending_tool_calls
    assert restored["round_count"] == 1


@pytest.mark.parametrize("invalid_history", ["missing", "changed", "different_user", "different_session"])
def test_history_references_never_silently_drop_or_replace_context(history_database, invalid_history):
    from app.core.copilot.workspace import load_run_workspace

    factory, workspace = history_database
    assert persist_running_workspace(factory, "current", workspace, worker_id="worker")
    with factory() as db:
        prior = db.get(CopilotRun, 1)
        if invalid_history == "missing":
            db.delete(prior)
        elif invalid_history == "changed":
            prior.answer = "unexpected edit"
        elif invalid_history == "different_user":
            prior.user_id = 99
        else:
            prior.copilot_session_id = 99
        db.commit()
        with pytest.raises(ValueError, match="history"):
            load_run_workspace(db, db.get(CopilotRun, 3))


def test_legacy_workspace_and_fresh_follow_up_keep_full_messages(history_database):
    from app.core.copilot.workspace import build_follow_up_workspace_seed, load_run_workspace

    factory, workspace = history_database
    legacy = workspace.to_dict()
    legacy.pop("history", None)
    with factory() as db:
        run = db.get(CopilotRun, 3)
        run.workspace_json = legacy
        db.commit()
        assert load_run_workspace(db, run) == legacy
        prior = db.query(CopilotRun).filter(CopilotRun.id.in_([1, 2])).order_by(CopilotRun.id).all()
        seed = build_follow_up_workspace_seed(legacy, history_runs=prior)
        assert seed["messages"] == []
        assert seed["pending_tool_calls"] == []
        assert seed["history"] == workspace.history


@pytest.mark.asyncio
@pytest.mark.parametrize("resume", [False, True], ids=["fresh-follow-up", "resume-pending-tool"])
async def test_full_provider_context_survives_new_storage_and_execution(history_database, monkeypatch, resume):
    from copy import deepcopy

    from app.core.ai_client import ToolLLMResponse
    from app.core.copilot.service import create_run, execute_copilot_run
    from app.core.copilot.workspace import load_run_workspace
    from tests.copilot.runtime_support import TEST_LLM_CONFIG, noop_coro

    factory, workspace = history_database
    if resume:
        assert persist_running_workspace(factory, "current", workspace, worker_id="worker")
    with factory() as db:
        db.get(CopilotRun, 3).status = "interrupted"
        db.commit()
        current = create_run(
            db, db.get(CopilotSession, 1), 1, "new question",
            resume_run_id="current" if resume else None,
        )
        current_id, run_id = current.id, current.run_id
    captured = []

    async def generate(self, **kwargs):
        captured.append(deepcopy(kwargs["messages"]))
        return ToolLLMResponse(content='{"answer":"final answer","suggestions":[]}')

    monkeypatch.setattr("app.database.SessionLocal", factory)
    monkeypatch.setattr("app.core.llm_semaphore.acquire_llm_slot", noop_coro)
    monkeypatch.setattr("app.core.llm_semaphore.release_llm_slot", lambda: None)
    monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", generate)
    await execute_copilot_run(run_id, 1, 1, TEST_LLM_CONFIG)

    assert len(captured) == 1
    assert captured[0][1:5] == workspace.messages[1:5]
    if resume:
        assert captured[0][:-1] == workspace.messages
        assert captured[0][-1]["role"] == "tool"
        assert captured[0][-1]["tool_call_id"] == "pending"
    else:
        assert captured[0][-1]["content"].startswith("new question")
    with factory() as db:
        completed = db.get(CopilotRun, current_id)
        assert completed.status == "completed"
        assert completed.answer == "final answer"
        assert "OLD_HISTORY" not in json.dumps(completed.workspace_json)
        restored = load_run_workspace(db, completed)
        assert restored["messages"][:-1] == captured[0]
        assert restored["pending_tool_calls"] == []
        if resume:
            assert restored["tool_journal"][0]["tool"] == "read"


@pytest.mark.parametrize("write_kind", ["lease", "preloaded", "workspace", "completed"])
@pytest.mark.parametrize("cancel_check", [1, 2], ids=["before-mutation", "before-commit"])
def test_cancelled_writers_close_without_committing(history_database, monkeypatch, write_kind, cancel_check):
    from app.core.copilot import run_store
    from app.core.copilot.sync_runtime import SyncWorkCancelled

    factory, workspace = history_database
    checks = 0

    def cancellation_checkpoint():
        nonlocal checks
        checks += 1
        if checks == cancel_check:
            raise SyncWorkCancelled()

    monkeypatch.setattr(run_store, "check_sync_cancelled", cancellation_checkpoint)
    with pytest.raises(SyncWorkCancelled):
        if write_kind == "lease":
            run_store.renew_run_lease(factory, run_id="current", worker_id="worker")
        elif write_kind == "preloaded":
            with factory() as db:
                run_store.persist_preloaded_evidence(db, db.get(CopilotRun, 3), [])
        elif write_kind == "workspace":
            run_store.persist_running_workspace(factory, "current", workspace, worker_id="worker")
        else:
            run_store.persist_completed_run(
                factory, run_id="current", worker_id="worker", answer="changed",
                evidence=[], compiled_suggestions=[], workspace=workspace,
                execution_mode="tool_loop", degraded_reason=None,
            )
    with factory() as db:
        run = db.get(CopilotRun, 3)
        assert run.status == "running"
        assert run.answer is None and run.workspace_json is None
        assert run.lease_owner == "worker" and run.lease_expires_at is None
    assert checks == cancel_check
