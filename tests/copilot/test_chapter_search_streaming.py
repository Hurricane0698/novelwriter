"""Differential checks for recall, ranking and normalized excerpt offsets."""

import random

import pytest
from sqlalchemy import event

from app.core.copilot import research_tools as tools
from app.core.copilot.workspace import EvidencePack, make_pack_id
from app.models import Chapter


@pytest.mark.parametrize(
    "language,text,terms",
    [
        ("zh", "甲" * 250 + "張三张三" * 500 + "李四。", ["张三", "李四", "三张"]),
        (
            "en",
            "Scatter cat CAT cats. straße STRASSE ﬃ foo-bar foo",
            ["cat", "strasse", "ffi", "foo", "foo-bar"],
        ),
        (
            "zh",
            "ＡＢＣ中文ＡＢＣ 中文测试测试" * 50,
            ["abc", "中文", "中文测试", "测试"],
        ),
        ("en", "no occurrence", ["absent"]),
        ("zh", "", ["名字"]),
    ],
)
def test_scan_preserves_match_count_term_order_and_excerpt(language, text, terms):
    policy = tools.get_language_policy(language)
    query_terms = [
        tools.QueryTerm(raw=value, normalized=policy.normalize_for_matching(value))
        for value in terms
    ]
    legacy = tools._find_term_matches(text, query_terms, language=language)
    count, matched_terms, first_matches = tools._scan_chapter_matches(
        text, query_terms, language=language
    )
    assert count == len(legacy)
    assert matched_terms == tools._summarize_matched_terms(legacy)
    assert first_matches == legacy[:4]
    assert tools._resolve_excerpt_window(
        text, first_matches
    ) == tools._resolve_excerpt_window(text, legacy)


def _legacy_find(db, novel, query_terms):
    scored = []
    for chapter in (
        db.query(Chapter).filter_by(novel_id=novel.id).order_by(Chapter.chapter_number)
    ):
        matches = tools._find_term_matches(
            chapter.content, query_terms, language=novel.language
        )
        if not matches:
            continue
        terms = tools._summarize_matched_terms(matches)
        start, end = tools._resolve_excerpt_window(chapter.content, matches)
        text = chapter.content[start:end]
        pack = EvidencePack(
            pack_id=make_pack_id(f"pk_ch_{chapter.id}_{start}_{end}", text[:100]),
            source_refs=[
                {
                    "type": "chapter",
                    "chapter_id": chapter.id,
                    "chapter_number": chapter.chapter_number,
                    "start_pos": start,
                    "end_pos": end,
                }
            ],
            preview_excerpt=text[:500],
            anchor_terms=terms[:5],
            support_count=len(terms),
            related_targets=[{"type": "chapter", "chapter_id": chapter.id}],
        )
        scored.append((len(terms), len(matches), chapter.chapter_number, pack))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [item[3] for item in scored[: tools.MAX_EVIDENCE_PACKS]]


def test_full_book_stream_keeps_global_top_k_and_never_loads_chapter_orm(
    db, novel, monkeypatch
):
    rng = random.Random(1948)
    terms = [
        tools.QueryTerm(raw=value, normalized=value)
        for value in ["张三", "李四", "王五"]
    ]
    # Best result is deliberately outside an initial chapter window. Sparse
    # numbers and equal scores also check the existing stable number ordering.
    for number in range(1, 90, 2):
        content = "开篇" * rng.randrange(10, 250) + "。".join(
            rng.choice(["张三", "李四", "王五", "路人"])
            for _ in range(rng.randrange(0, 18))
        )
        if number == 89:
            content += "张三李四王五" * 50
        db.add(Chapter(novel_id=novel.id, chapter_number=number, content=content))
    db.commit()
    expected = _legacy_find(db, novel, terms)
    observed_loads = []
    statements = []

    def on_load(row, context):
        observed_loads.append(row.id)

    def on_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    monkeypatch.setattr(tools, "_extract_query_terms", lambda *args: terms)
    event.listen(Chapter, "load", on_load)
    event.listen(db.bind, "before_cursor_execute", on_sql)
    try:
        actual = tools._find_from_chapters("query", db, novel)
    finally:
        event.remove(Chapter, "load", on_load)
        event.remove(db.bind, "before_cursor_execute", on_sql)
    assert actual == expected
    assert actual[0].source_refs[0]["chapter_number"] == 89
    assert not observed_loads
    assert len(statements) == 1
    assert "chapters.content" in statements[0]
    assert "chapters.title" not in statements[0]
