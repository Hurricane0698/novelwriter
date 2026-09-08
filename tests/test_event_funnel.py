"""Outcome accounting must survive repeated events and historical metadata."""

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.event_funnel import build_hosted_beta_funnel_report
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

            report = build_hosted_beta_funnel_report(db)
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
