# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

from app.core.copilot.messages import CopilotTextKey, get_copilot_text
from app.core.copilot.tracing import build_completed_trace


def test_copilot_registry_accepts_locale_aliases():
    assert get_copilot_text(
        CopilotTextKey.TRACE_FIND,
        locale="ja-JP",
        query="アリス",
    ) == "「アリス」を検索"
    assert get_copilot_text(
        CopilotTextKey.TRACE_FIND,
        locale="ko-KR",
        query="앨리스",
    ) == '"앨리스" 검색'


def test_copilot_registry_falls_back_to_zh_for_unsupported_locale():
    assert get_copilot_text(
        CopilotTextKey.WORKSPACE_EVIDENCE_COMPILED,
        locale="fr",
    ) == "已从相关线索中整理"


def test_copilot_runtime_registry_formats_registered_messages():
    assert get_copilot_text(
        CopilotTextKey.TRACE_FIND,
        locale="en",
        query="Alice",
    ) == 'Search "Alice"'
    assert get_copilot_text(
        CopilotTextKey.TRACE_FIND,
        locale="ja",
        query="アリス",
    ) == "「アリス」を検索"


def test_completed_trace_uses_registry_copy_for_japanese_locale():
    trace = build_completed_trace(
        workspace=None,
        execution_mode="one_shot_unsupported",
        degraded_reason=None,
        evidence_count=2,
        suggestion_count=1,
        interaction_locale="ja",
    )

    assert trace[0]["summary"] == "現在のモデルは段階的取得をサポートしていないため、直接分析に切り替えました"
    assert trace[1]["summary"] == "表示用の根拠を 2 件整理しました"
    assert trace[2]["summary"] == "分析が完了し、提案を 1 件生成しました"
