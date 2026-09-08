"""Outcome accounting must survive repeated events and historical metadata."""

from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.event_funnel import build_hosted_beta_funnel_report
from app.core import event_funnel
from app.database import Base
from app.models import Novel, User, UserEvent


def test_repeated_events_preserve_first_outcome_times_and_weighted_counts():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(User(id=1, username="funnel-test", hashed_password="unused"))
            db.add(
                Novel(
                    id=1,
                    owner_id=1,
                    title="test",
                    file_path="/tmp/test.txt",
                    total_chapters=1,
                )
            )
            start = datetime(2026, 9, 1)
            sequence = [
                ("project_start", {"start_mode": "demo", "channel": "test"}),
                ("chapter_save", {}),  # Saving before generation is not first value.
                ("generation", {}),
                ("chapter_save", {}),
                ("generation", {}),
                ("chapter_save", {}),
                ("demo_guide_completed", {}),
                ("demo_guide_completed", {}),
                ("demo_guide_step_complete", {"step": "chapter"}),
                ("demo_guide_step_complete", {"step": "unknown"}),
                ("draft_confirm", {"count": 3}),
                ("draft_confirm", {"count": -2}),
                ("draft_confirm", {"count": True}),
                ("copilot_apply", {"success_count": 0, "applied_count": 2}),
                ("copilot_apply", {"success_count": -3}),
                ("unknown_legacy_event", {}),
            ]
            for offset, (event, meta) in enumerate(sequence):
                db.add(
                    UserEvent(
                        user_id=1,
                        novel_id=1,
                        event=event,
                        meta=meta,
                        created_at=start + timedelta(seconds=offset),
                    )
                )
            db.commit()

            with patch.object(event_funnel, "_new_project", wraps=event_funnel._new_project) as factory:
                report = build_hosted_beta_funnel_report(db)
            assert factory.call_count == 1
            project = report["project_funnel_rows"][0]
            assert (
                project["first_generation_at"]
                == (start + timedelta(seconds=2)).isoformat()
            )
            assert (
                project["first_value_at"] == (start + timedelta(seconds=3)).isoformat()
            )
            assert (
                project["demo_guide_completed_at"]
                == (start + timedelta(seconds=6)).isoformat()
            )
            assert project["generation_count"] == 2
            assert project["chapter_save_count"] == 3
            assert project["demo_guide_step_count"] == 2
            assert project["demo_guide_step_chapter_count"] == 1
            assert project["draft_confirm_count"] == 5
            assert project["copilot_apply_count"] == 2
            assert report["segment_summary"][0]["generated_projects"] == 1
            assert report["segment_summary"][0]["first_value_projects"] == 1
            assert report["derived_metrics"]["copilot_applied"]["projects"] == 1
            assert report["funnel_summary"]["unknown_legacy_event"]["total"] == 1
    finally:
        engine.dispose()


def test_history_trust_and_late_appends_use_one_event_boundary(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            start = datetime.now() - timedelta(days=60)
            db.add_all([User(id=i, username=f"user-{i}", hashed_password="unused") for i in (1, 2)])
            # The deleted project's later trusted event must validate earlier public events.
            for user, novel, event, meta, age in [
                (1, None, "signup", {"channel": "historic"}, 0),
                (1, 10, "world_model_view", {}, 1),
                (2, 10, "world_model_view", {}, 1),  # Another user cannot borrow that trust.
                (1, 10, "project_start", {"start_mode": "demo"}, 2),
                (1, 10, "demo_guide_completed", {}, 3),
                (1, None, "upload_cta_click", {}, 4),
            ]:
                db.add(UserEvent(user_id=user, novel_id=novel, event=event, meta=meta, created_at=start + timedelta(days=age)))
            db.commit()
            summarize = event_funnel._summarize_events

            def append_after_first_pass(rows):
                result = summarize(rows)
                db.add(UserEvent(user_id=1, event="upload_cta_click", created_at=datetime.now()))
                db.commit()
                return result

            monkeypatch.setattr(event_funnel, "_summarize_events", append_after_first_pass)
            report = build_hosted_beta_funnel_report(db)
            assert report["funnel_summary"]["world_model_view"]["total"] == 1
            assert report["project_funnel_rows"][0]["channel"] == "historic"
            assert report["daily_breakdown_last_30d"] == {}
            assert report["funnel_summary"]["upload_cta_click"]["total"] == 1
            assert report["cross_project_user_metrics"]["demo_guide_to_upload_click"]["events"] == 1
            assert len(report["recent_events"]) == 5
    finally:
        engine.dispose()
