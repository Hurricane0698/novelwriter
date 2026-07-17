from __future__ import annotations

import pytest

from app.core.bootstrap import BootstrapRunSummary
from app.core.llm_config import ResolvedLlmConfig
from app.core.world import bootstrap_application as bootstrap_app


class _DummySession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_run_bootstrap_background_job_records_completion_event():
    recorded: list[dict] = []
    session = _DummySession()

    async def _bootstrap_runner(*args, **kwargs):
        return BootstrapRunSummary(
            novel_id=12,
            mode="reextract",
            entities_found=3,
            relationships_found=2,
        )

    await bootstrap_app.run_bootstrap_background_job(
        99,
        session_factory=lambda: session,
        user_id=7,
        llm_config=ResolvedLlmConfig(
            base_url="https://example.com/v1",
            api_key="key",
            model="x",
            billing_source_hint="selfhost",
            source="selfhost_settings",
        ),
        bootstrap_runner=_bootstrap_runner,
        record_event_fn=lambda db, user_id, event, novel_id=None, meta=None: recorded.append(
            {
                "db": db,
                "user_id": user_id,
                "event": event,
                "novel_id": novel_id,
                "meta": meta,
            }
        ),
    )

    assert session.closed is True
    assert recorded == [
        {
            "db": session,
            "user_id": 7,
            "event": "bootstrap_run",
            "novel_id": 12,
            "meta": {
                "mode": "reextract",
                "entities_found": 3,
                "relationships_found": 2,
            },
        }
    ]


@pytest.mark.asyncio
async def test_run_bootstrap_background_job_skips_event_when_bootstrap_fails():
    session = _DummySession()
    recorded: list[dict] = []

    async def _bootstrap_runner(*args, **kwargs):
        return None

    await bootstrap_app.run_bootstrap_background_job(
        101,
        session_factory=lambda: session,
        user_id=7,
        bootstrap_runner=_bootstrap_runner,
        record_event_fn=lambda *args, **kwargs: recorded.append({"args": args, "kwargs": kwargs}),
    )

    assert session.closed is False
    assert recorded == []
