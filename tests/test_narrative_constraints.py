"""Tests for narrative constraints extraction and prompt separation."""

from app.api.novels import _extract_narrative_constraints


class TestExtractNarrativeConstraints:
    def test_empty_when_no_systems(self):
        assert _extract_narrative_constraints({"systems": []}) == ""

    def test_empty_when_no_constraints(self):
        ctx = {
            "systems": [
                {"name": "修炼体系", "constraints": [], "data": {"nodes": []}},
            ]
        }
        assert _extract_narrative_constraints(ctx) == ""

    def test_extracts_constraints_from_single_system(self):
        ctx = {
            "systems": [
                {
                    "name": "叙事约束",
                    "constraints": ["暗线不得在对话里直白说出", "每章最多一次时间跳转"],
                    "data": None,
                },
            ]
        }
        result = _extract_narrative_constraints(ctx)
        assert "<narrative_constraints>" in result
        assert "1. 暗线不得在对话里直白说出" in result
        assert "2. 每章最多一次时间跳转" in result

    def test_merges_constraints_across_systems(self):
        ctx = {
            "systems": [
                {"name": "叙事约束", "constraints": ["规则A"]},
                {"name": "角色禁忌", "constraints": ["规则B", "规则C"]},
            ]
        }
        result = _extract_narrative_constraints(ctx)
        assert "1. 规则A" in result
        assert "2. 规则B" in result
        assert "3. 规则C" in result

    def test_skips_empty_and_whitespace_constraints(self):
        ctx = {
            "systems": [
                {"name": "test", "constraints": ["有效规则", "", "  ", None, "另一条"]},
            ]
        }
        result = _extract_narrative_constraints(ctx)
        assert "1. 有效规则" in result
        assert "2. 另一条" in result
        # Should only have 2 numbered rules
        assert "3." not in result

    def test_empty_when_writer_ctx_missing_systems_key(self):
        assert _extract_narrative_constraints({}) == ""

    def test_handles_non_dict_system_entries(self):
        ctx = {"systems": [None, "bad", {"name": "ok", "constraints": ["rule"]}]}
        result = _extract_narrative_constraints(ctx)
        assert "1. rule" in result
