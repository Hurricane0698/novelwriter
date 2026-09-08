"""Poll/list and post-commit responses do not decode private runtime payloads."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session

from app.api.copilot import _run_to_response
from app.core.copilot.run_state import check_stale_run, utcnow_naive
from app.core.copilot.session_runtime import list_session_runs, load_latest_run, load_run
from app.database import Base
from app.models import CopilotRun, CopilotSession, Novel


@pytest.mark.parametrize("read_kind", ["poll", "latest", "list"])
def test_response_loaders_skip_private_json_even_after_stale_commit(tmp_path, read_kind):
    decoded = []

    def deserialize(value):
        payload = json.loads(value)
        if isinstance(payload, dict) and "private_marker" in payload:
            decoded.append(payload["private_marker"])
        return payload

    engine = create_engine(f"sqlite:///{tmp_path / 'copilot.db'}", json_deserializer=deserialize)
    Base.metadata.create_all(engine)
    with Session(engine) as seed:
        seed.add(Novel(id=1, title="Book", file_path="unused"))
        seed.add(CopilotSession(
            id=1, session_id="session", novel_id=1, user_id=1,
            mode="research", scope="whole_book", signature="signature",
            context_json={"private_marker": "session-context"},
        ))
        seed.add(CopilotRun(
            id=1, run_id="run", copilot_session_id=1, novel_id=1, user_id=1,
            status="running", prompt="question", answer="answer",
            workspace_json={"private_marker": "workspace", "messages": ["x" * 100000]},
            context_json={"private_marker": "run-context"},
            lease_expires_at=utcnow_naive() - timedelta(seconds=60),
        ))
        seed.commit()
    decoded.clear()
    with Session(engine) as db:
        if read_kind == "poll":
            run = load_run(db, 1, 1, "session", "run")
        elif read_kind == "latest":
            run = load_latest_run(db, 1)
        else:
            run, = list_session_runs(db, 1)
        assert {"workspace_json", "context_json"} <= inspect(run).unloaded
        assert check_stale_run(run) is True
        db.commit()
        response = _run_to_response(run)
        assert response.status == "interrupted"
        assert response.prompt == "question" and response.answer == "answer"
        assert decoded == []
        # Execution/resume callers can still explicitly read both payloads.
        assert run.workspace_json["private_marker"] == "workspace"
        assert run.context_json["private_marker"] == "run-context"
        assert decoded == ["workspace", "run-context"]
        assert load_run(db, 1, 2, "session", "run") is None
        assert load_run(db, 2, 1, "session", "run") is None
    engine.dispose()


@pytest.mark.parametrize("action", ["poll", "apply", "dismiss"])
@pytest.mark.parametrize("foreign_scope", ["user", "novel", "session"])
def test_projected_api_reads_preserve_run_ownership(client, db, novel, action, foreign_scope):
    other = Novel(title="Other book", file_path="unused")
    db.add(other)
    db.flush()
    session = CopilotSession(
        session_id="foreign-session", novel_id=other.id if foreign_scope == "novel" else novel.id,
        user_id=99 if foreign_scope == "user" else 1,
        mode="research", scope="whole_book", signature="foreign-signature",
    )
    db.add(session)
    db.flush()
    run = CopilotRun(
        run_id="foreign-run", copilot_session_id=session.id, novel_id=session.novel_id,
        user_id=session.user_id, status="completed", prompt="private question",
        answer="private answer", suggestions_json=[{"suggestion_id": "suggestion", "status": "pending"}],
        workspace_json={"private_marker": "workspace"}, context_json={"private_marker": "context"},
    )
    db.add(run)
    db.commit()
    session_id = "different-session" if foreign_scope == "session" else session.session_id
    url = f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/foreign-run"
    response = client.get(url) if action == "poll" else client.post(
        f"{url}/{action}", json={"suggestion_ids": ["suggestion"]},
    )
    assert response.status_code == 404
    db.refresh(run)
    assert run.suggestions_json == [{"suggestion_id": "suggestion", "status": "pending"}]


def test_stale_history_list_does_not_reload_every_completed_run(tmp_path):
    from app.api.copilot import run_list

    engine = create_engine(f"sqlite:///{tmp_path / 'history-list.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Novel(id=1, title="Book", file_path="unused"))
        db.add(CopilotSession(
            id=1, session_id="session", novel_id=1, user_id=1,
            mode="research", scope="whole_book", signature="signature",
        ))
        db.add_all([CopilotRun(
            id=i, run_id=f"run-{i}", copilot_session_id=1, novel_id=1, user_id=1,
            status="running" if i == 26 else "completed", prompt=f"question-{i}",
            answer=f"answer-{i}", lease_expires_at=utcnow_naive() - timedelta(seconds=60),
        ) for i in range(1, 27)])
        db.commit()
    statements = []
    event.listen(engine, "before_cursor_execute", lambda _c, _u, sql, *_args: statements.append(sql))
    with Session(engine) as db:
        responses = run_list(1, "session", novel=None, user=SimpleNamespace(id=1), db=db)
        assert [item.prompt for item in responses] == [f"question-{i}" for i in range(1, 27)]
        assert responses[-1].status == "interrupted"
    run_reads = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT") and "FROM copilot_runs" in sql]
    assert len(run_reads) == 1
    with Session(engine) as db:
        assert db.get(CopilotRun, 26).status == "interrupted"
    engine.dispose()
