# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot runtime scenario derivation tests."""

class TestScenarioDerivation:
    def test_derive_scenarios(self):
        from app.core.copilot.runtime_scenario import derive_scenario
        assert derive_scenario("draft_cleanup", "whole_book", None) == "draft_cleanup"
        assert derive_scenario("research", "whole_book", None) == "whole_book"
        assert derive_scenario("current_entity", "current_entity", {"tab": "relationships"}) == "relationships"
        assert derive_scenario("current_entity", "current_entity", {"entity_id": 1}) == "current_entity"

    def test_derive_runtime_profiles(self):
        from app.core.copilot.scope import derive_runtime_profile

        assert derive_runtime_profile("draft_cleanup", "current_tab", {"tab": "review"}) == "draft_governance"
        assert derive_runtime_profile("research", "whole_book", None) == "broad_exploration"
        assert derive_runtime_profile("research", "current_tab", {"entity_id": 1, "tab": "relationships"}) == "focused_research"
