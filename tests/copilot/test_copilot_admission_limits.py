# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot global admission-limit tests."""

import pytest

from app.models import User


class TestCopilotAdmissionControl:
    def test_copilot_per_user_limit_stricter_than_general(self):
        from app.config import get_settings
        from app.core.copilot.service import MAX_ACTIVE_RUNS_PER_USER

        settings = get_settings()
        assert settings.copilot_max_runs_per_user <= MAX_ACTIVE_RUNS_PER_USER

    def test_global_limit_enforced(self, db, novel):
        import os

        from app.config import reload_settings
        from app.core.copilot.runtime_errors import CopilotError
        from app.core.copilot.service import create_run, open_or_reuse_session

        orig = os.environ.get("COPILOT_MAX_RUNS_GLOBAL")
        os.environ["COPILOT_MAX_RUNS_GLOBAL"] = "1"
        try:
            reload_settings()
            s1, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "g1")
            create_run(db, s1, 1, "run 1")
            user2 = User(id=2, username="user2", hashed_password="x", role="user", is_active=True, generation_quota=999)
            db.add(user2)
            db.commit()
            s2, _ = open_or_reuse_session(db, novel.id, 2, "research", "whole_book", None, "zh", "g2")
            with pytest.raises(CopilotError) as exc_info:
                create_run(db, s2, 2, "run 2")
            assert exc_info.value.code == "too_many_global_runs"
        finally:
            if orig is None:
                os.environ.pop("COPILOT_MAX_RUNS_GLOBAL", None)
            else:
                os.environ["COPILOT_MAX_RUNS_GLOBAL"] = orig
            reload_settings()
