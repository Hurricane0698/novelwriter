"""Direct PyO3 contract coverage for the Rust state-proto builder."""

from __future__ import annotations

import json
import threading
import time

import pytest
import _novwr_state_proto

from app.core.state_proto_contract import STATE_PROTO_PAYLOAD_FORMAT_VERSION
from app.core.indexing.builder import ChapterText
from app.core.indexing.state_proto import (
    SLOT_ENTITY_CURRENT_LOCATION,
    TARGET_KIND_ARTIFACT,
    StateProtoIndex,
    TargetSpec,
    execute_state_proto_build,
)
from app.core.indexing.state_proto_rust_contract import (
    RUST_STATE_PROTO_BUILD_REQUEST_FORMAT_VERSION,
    RustStateProtoAssembleResult,
    RustStateProtoUpdatePlan,
    assemble_rust_state_proto_payload,
    build_rust_zh_block_refinement_inputs,
    build_rust_state_proto_full,
    build_rust_state_proto_request,
    count_rust_zh_candidates,
    plan_rust_state_proto_update,
    rust_state_proto_is_available,
    summarize_rust_zh_windows,
    update_rust_state_proto_incremental,
)
import app.core.indexing.state_proto_rust_module as rust_module_bridge


def test_rust_and_python_payload_format_versions_match():
    assert (
        RUST_STATE_PROTO_BUILD_REQUEST_FORMAT_VERSION
        == STATE_PROTO_PAYLOAD_FORMAT_VERSION
    )
    assert (
        _novwr_state_proto.payload_format_version()
        == STATE_PROTO_PAYLOAD_FORMAT_VERSION
    )


def test_build_rust_state_proto_request_serializes_explicit_targets_only():
    request = build_rust_state_proto_request(
        chapters=[
            ChapterText(chapter_id=1, text="林秋在云港司守夜。"),
            ChapterText(chapter_id=2, text="玄铁令如今归沈砚所有。"),
        ],
        target_specs=[
            TargetSpec(id="lin_qiu", canonical_name="林秋"),
            TargetSpec(
                id="token",
                canonical_name="玄铁令",
                kind=TARGET_KIND_ARTIFACT,
            ),
        ],
        novel_language="zh",
    )

    payload = request.to_wire()

    assert payload["format_version"] == RUST_STATE_PROTO_BUILD_REQUEST_FORMAT_VERSION
    assert payload["requested_language"] == "zh"
    assert payload["chapters"][0]["chapter_id"] == 1
    assert payload["chapters"][0]["signature"]
    assert payload["targets"] == [
        {
            "id": "lin_qiu",
            "canonical_name": "林秋",
            "kind": "entity",
            "aliases": [],
        },
        {
            "id": "token",
            "canonical_name": "玄铁令",
            "kind": "artifact",
            "aliases": [],
        },
    ]

    assert json.loads(request.to_json_bytes().decode("utf-8")) == payload


def test_execute_state_proto_build_without_catalog_keeps_empty_target_set():
    if not rust_state_proto_is_available():
        return

    output = execute_state_proto_build(
        chapters=[
            ChapterText(
                chapter_id=1,
                text="玄力玄力玄力。云澈在云荒镇休养。",
            ),
            ChapterText(
                chapter_id=2,
                text="茉莉还活着。",
            ),
        ],
        novel_language="zh",
        target_specs=(),
    )

    index = StateProtoIndex.from_msgpack(output.index_payload)
    assert output.target_count == 0
    assert output.claim_atom_count == 0
    assert index.targets == {}


def test_rust_tokenize_zh_text_matches_expected_surfaces():
    if not rust_state_proto_is_available():
        return

    tokens = _novwr_state_proto.tokenize_zh_text("林秋在云港司守夜，顾衡来找林秋。")

    assert tokens[:10] == [
        "林秋",
        "在",
        "云港司",
        "守夜",
        "，",
        "顾衡",
        "来",
        "找",
        "林秋",
        "。",
    ]


def test_count_rust_zh_candidates_matches_expected_counts():
    if not rust_state_proto_is_available():
        return

    counts = count_rust_zh_candidates(
        chapters=[
            ChapterText(
                chapter_id=1,
                text="林秋在云港司守夜。顾衡来找林秋。云港司里再次提起顾衡。",
            )
        ],
        common_words=["在", "里", "再次", "提起"],
        max_batch_chars=1024,
    )

    assert counts is not None
    by_name = {item.name: item.count for item in counts}
    assert by_name["林秋"] == 2
    assert by_name["顾衡"] == 2


def test_count_rust_zh_candidates_is_stable_across_chapter_batches():
    if not rust_state_proto_is_available():
        return

    chapters = [
        ChapterText(chapter_id=1, text="林秋在云港司守夜。"),
        ChapterText(chapter_id=2, text="顾衡来找林秋。"),
        ChapterText(chapter_id=3, text="云港司里再次提起顾衡。"),
    ]

    large_batch = count_rust_zh_candidates(
        chapters=chapters,
        common_words=["在", "里", "再次", "提起"],
        max_batch_chars=4096,
    )
    small_batch = count_rust_zh_candidates(
        chapters=chapters,
        common_words=["在", "里", "再次", "提起"],
        max_batch_chars=8,
    )

    assert large_batch == small_batch


def test_count_rust_zh_candidates_batching_keeps_chapter_boundaries():
    if not rust_state_proto_is_available():
        return

    chapters = [
        ChapterText(chapter_id=1, text="云港"),
        ChapterText(chapter_id=2, text="司守夜，林秋又回到云港。"),
        ChapterText(chapter_id=3, text="顾衡仍在云港司守夜。"),
    ]

    large_batch = count_rust_zh_candidates(
        chapters=chapters,
        common_words=["又", "回到", "仍", "在"],
        max_batch_chars=4096,
    )
    tiny_batch = count_rust_zh_candidates(
        chapters=chapters,
        common_words=["又", "回到", "仍", "在"],
        max_batch_chars=2,
    )

    assert large_batch == tiny_batch
    assert large_batch is not None
    by_name = {item.name: item.count for item in large_batch}
    assert by_name["云港"] == 2
    assert by_name["云港司"] == 1


def test_count_rust_zh_candidates_recovers_split_person_names():
    if not rust_state_proto_is_available():
        return

    counts = count_rust_zh_candidates(
        chapters=[
            ChapterText(
                chapter_id=1,
                text=(
                    "慕容雪晴来到大厅。慕容雪晴看着欧阳明月，欧阳明月也看着慕容雪晴。"
                    "顾慎为与荷女对视。顾慎为没有说话。"
                ),
            )
        ],
        common_words=["来到", "看着", "也", "与", "没有", "说话"],
        max_batch_chars=1024,
    )

    assert counts is not None
    by_name = {item.name: item.count for item in counts}
    assert by_name["慕容雪晴"] == 3
    assert by_name["欧阳明月"] == 2
    assert by_name["顾慎为"] == 2


def test_count_rust_zh_candidates_recovers_bound_fragment_full_names():
    if not rust_state_proto_is_available():
        return

    counts = count_rust_zh_candidates(
        chapters=[
            ChapterText(
                chapter_id=1,
                text=(
                    "拉蒂莉娅看见坎贝斯莉太太。"
                    "拉蒂莉娅向坎贝斯莉太太行礼。"
                    "拉蒂莉娅又遇见坎贝斯莉太太。"
                ),
            )
        ],
        common_words=["看见", "行礼", "遇见"],
        max_batch_chars=1024,
    )

    assert counts is not None
    by_name = {item.name: item.count for item in counts}
    assert by_name["拉蒂莉娅"] == 3
    assert by_name["坎贝斯莉太太"] == 3
    assert "拉蒂" not in by_name
    assert "贝斯" not in by_name
    assert "太太" not in by_name


def test_count_rust_zh_candidates_merges_person_name_trailing_noise_variants():
    if not rust_state_proto_is_available():
        return

    counts = count_rust_zh_candidates(
        chapters=[
            ChapterText(
                chapter_id=1,
                text="罗碧不，凤凌。罗碧一，凤凌。罗碧看，凤凌。罗碧没，凤凌。罗碧，凤凌。",
            )
        ],
        common_words=[],
        max_batch_chars=1024,
    )

    assert counts is not None
    by_name = {item.name: item.count for item in counts}
    assert by_name["罗碧"] >= 5
    assert by_name["凤凌"] >= 5
    assert "罗碧不" not in by_name
    assert "罗碧一" not in by_name
    assert "罗碧看" not in by_name
    assert "罗碧没" not in by_name


def test_count_rust_zh_candidates_normalizes_variant_characters():
    if not rust_state_proto_is_available():
        return

    counts = count_rust_zh_candidates(
        chapters=[
            ChapterText(
                chapter_id=1,
                text="凤雪児看向云澈。凤雪児再次叫住云澈。凤雪児握住云澈的手。",
            )
        ],
        common_words=[],
        max_batch_chars=1024,
    )

    assert counts is not None
    by_name = {item.name: item.count for item in counts}
    assert by_name["凤雪儿"] >= 3
    assert "凤雪児" not in by_name


def test_count_rust_zh_candidates_uses_single_python_bridge_call(monkeypatch):
    calls: list[list[str]] = []

    class _FakeRustModule:
        @staticmethod
        def count_zh_candidates(
            chapters: list[str],
            common_words: list[str],
            max_batch_chars: int,
        ) -> list[tuple[str, int]]:
            del common_words, max_batch_chars
            calls.append(list(chapters))
            counts: dict[str, int] = {}
            for chapter in chapters:
                counts[chapter] = counts.get(chapter, 0) + 1
            return sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    monkeypatch.setattr(rust_module_bridge, "_novwr_state_proto", _FakeRustModule())

    counts = count_rust_zh_candidates(
        chapters=[
            ChapterText(chapter_id=1, text="甲"),
            ChapterText(chapter_id=2, text="甲"),
            ChapterText(chapter_id=3, text="乙"),
        ],
        common_words=[],
        max_batch_chars=1,
        limit=2,
    )

    assert calls == [["甲", "甲", "乙"]]
    assert counts is not None
    assert [(item.name, item.count) for item in counts] == [("甲", 2), ("乙", 1)]


def test_count_rust_zh_candidates_topk_matches_full_prefix():
    if not rust_state_proto_is_available():
        return

    chapters = [
        ChapterText(
            chapter_id=1,
            text=(
                "林秋在云港司守夜。顾衡来找林秋。云港司里再次提起顾衡。"
                "旧案旧案旧案，河湾书院也被提起。"
            ),
        )
    ]

    full_counts = count_rust_zh_candidates(
        chapters=chapters,
        common_words=["在", "里", "再次", "提起", "也", "被"],
        max_batch_chars=1024,
    )
    topk_counts = count_rust_zh_candidates(
        chapters=chapters,
        common_words=["在", "里", "再次", "提起", "也", "被"],
        max_batch_chars=1024,
        limit=3,
    )

    assert full_counts is not None
    assert topk_counts is not None
    assert topk_counts == full_counts[:3]


def test_count_rust_zh_candidates_topk_prefers_recovered_full_name_on_tie():
    if not rust_state_proto_is_available():
        return

    counts = count_rust_zh_candidates(
        chapters=[
            ChapterText(
                chapter_id=1,
                text="慕容雪晴来到大厅。慕容雪晴看着众人，慕容雪晴没有回头。",
            )
        ],
        common_words=["来到", "看着", "没有", "回头"],
        max_batch_chars=1024,
        limit=1,
    )

    assert counts is not None
    assert [(item.name, item.count) for item in counts] == [("慕容雪晴", 3)]


def test_count_rust_zh_candidates_honors_ascii_common_word_casefold():
    if not rust_state_proto_is_available():
        return

    counts = count_rust_zh_candidates(
        chapters=[
            ChapterText(
                chapter_id=1,
                text="ABC又回来了。abc再次出现。云港司仍在。",
            )
        ],
        common_words=["abc", "又", "回来", "了", "再次", "出现", "仍", "在"],
        max_batch_chars=1024,
    )

    assert counts is not None
    by_name = {item.name: item.count for item in counts}
    assert "ABC" not in by_name
    assert "abc" not in by_name
    assert by_name["云港司"] == 1


def test_count_rust_zh_candidates_keeps_mixed_ascii_cjk_segmentation():
    if not rust_state_proto_is_available():
        return

    counts = count_rust_zh_candidates(
        chapters=[
            ChapterText(
                chapter_id=1,
                text="abc网球拍卖会def abc网球拍卖会def",
            )
        ],
        common_words=[],
        max_batch_chars=1024,
    )

    assert counts is not None
    by_name = {item.name: item.count for item in counts}
    assert by_name["abc"] == 2
    assert by_name["网球"] == 2
    assert by_name["拍卖会"] == 2
    assert by_name["def"] == 2


def test_count_rust_zh_candidates_keeps_unmatched_nfkc_tokens():
    if not rust_state_proto_is_available():
        return

    counts = count_rust_zh_candidates(
        chapters=[
            ChapterText(
                chapter_id=1,
                text="Ⅳ Ⅳ ＡＢＣ",
            )
        ],
        common_words=[],
        max_batch_chars=1024,
    )

    assert counts is not None
    by_name = {item.name: item.count for item in counts}
    assert by_name["IV"] == 2
    assert "ABC" not in by_name


def test_summarize_rust_zh_windows_matches_expected_pairs():
    if not rust_state_proto_is_available():
        return

    summary = summarize_rust_zh_windows(
        chapters=[
            ChapterText(
                chapter_id=1,
                text=("林秋在云港司守夜，顾衡来找林秋。顾衡与林秋又在云港司说起旧案。")
                * 12,
            )
        ],
        shortlisted_candidates=["林秋", "顾衡", "云港司", "旧案"],
        window_size=500,
        window_step=250,
        threshold=1,
    )

    assert summary is not None
    assert summary.importance["林秋"] > 0
    assert summary.importance["顾衡"] > 0
    assert summary.cooccurrence_pairs[0][2] >= summary.cooccurrence_pairs[-1][2]
    assert any(
        {left, right} == {"林秋", "顾衡"}
        for left, right, _ in summary.cooccurrence_pairs
    )


def test_summarize_rust_zh_windows_wrapper_matches_structured_extension_output():
    if not rust_state_proto_is_available():
        return

    chapters = [
        ChapterText(
            chapter_id=1,
            text=("林秋在云港司守夜，顾衡来找林秋。顾衡与林秋又在云港司说起旧案。")
            * 12,
        )
    ]
    shortlisted_candidates = ["林秋", "顾衡", "云港司", "旧案"]
    summary = summarize_rust_zh_windows(
        chapters=chapters,
        shortlisted_candidates=shortlisted_candidates,
        window_size=500,
        window_step=250,
        threshold=1,
    )

    raw_importance, raw_pairs = _novwr_state_proto.summarize_zh_windows(
        [chapter.text or "" for chapter in chapters],
        shortlisted_candidates,
        500,
        250,
        1,
    )

    assert summary is not None
    assert summary.importance == {
        str(name): int(count) for name, count in raw_importance
    }
    assert summary.cooccurrence_pairs == [
        (str(left), str(right), int(count)) for left, right, count in raw_pairs
    ]


def test_summarize_rust_zh_windows_keeps_ascii_shortlist_semantics():
    if not rust_state_proto_is_available():
        return

    chapter_text = "hello " + ("a" * 1200)
    long_ascii_candidate = "a" * 400
    summary = summarize_rust_zh_windows(
        chapters=[ChapterText(chapter_id=1, text=chapter_text)],
        shortlisted_candidates=["hello", long_ascii_candidate],
        window_size=500,
        window_step=250,
        threshold=1,
    )

    assert summary is not None
    assert summary.importance["hello"] >= 1
    assert summary.importance[long_ascii_candidate] >= 1
    assert any(
        {left, right} == {"hello", long_ascii_candidate}
        for left, right, _ in summary.cooccurrence_pairs
    )


def test_summarize_rust_zh_windows_drops_candidates_longer_than_window():
    if not rust_state_proto_is_available():
        return

    too_long_candidate = "a" * 900
    summary = summarize_rust_zh_windows(
        chapters=[ChapterText(chapter_id=1, text="hello " + ("a" * 1200))],
        shortlisted_candidates=["hello", too_long_candidate],
        window_size=500,
        window_step=250,
        threshold=1,
    )

    assert summary is not None
    assert too_long_candidate not in summary.importance


def test_summarize_rust_zh_windows_uses_single_python_bridge_call(monkeypatch):
    calls: list[list[str]] = []

    class _FakeRustModule:
        @staticmethod
        def summarize_zh_windows(
            chapters: list[str],
            shortlisted_candidates: list[str],
            window_size: int,
            window_step: int,
            threshold: int,
        ) -> tuple[list[tuple[str, int]], list[tuple[str, str, int]]]:
            del window_size, window_step, threshold
            calls.append(list(chapters))
            candidate_names = sorted(
                {candidate for candidate in shortlisted_candidates if candidate}
            )
            importance: dict[str, int] = {}
            pairs: dict[tuple[str, str], int] = {}
            for chapter in chapters:
                present = sorted(
                    candidate for candidate in candidate_names if candidate in chapter
                )
                for candidate in present:
                    importance[candidate] = importance.get(candidate, 0) + 1
                for index, left in enumerate(present):
                    for right in present[index + 1 :]:
                        pair = (left, right)
                        pairs[pair] = pairs.get(pair, 0) + 1
            return (
                sorted(importance.items()),
                [
                    (left, right, count)
                    for (left, right), count in sorted(pairs.items())
                ],
            )

    monkeypatch.setattr(rust_module_bridge, "_novwr_state_proto", _FakeRustModule())

    summary = summarize_rust_zh_windows(
        chapters=[
            ChapterText(chapter_id=1, text="ab"),
            ChapterText(chapter_id=2, text="bc"),
        ],
        shortlisted_candidates=["a", "b", "c"],
        window_size=32,
        window_step=16,
        threshold=1,
    )

    assert calls == [["ab", "bc"]]
    assert summary is not None
    assert summary.importance == {"a": 1, "b": 2, "c": 1}
    assert set(summary.cooccurrence_pairs) == {("a", "b", 1), ("b", "c", 1)}


def test_build_rust_zh_block_refinement_inputs_collapses_shadow_name_surfaces():
    if not rust_state_proto_is_available():
        return

    text = (
        "罗碧看向凤凌。凤凌回应罗碧。罗碧说凤凌别急。"
        "凤凌看着罗碧。罗碧与凤凌登上炙皇星。"
    ) * 12
    summary = build_rust_zh_block_refinement_inputs(
        chapters=[ChapterText(chapter_id=1, text=text)],
        common_words=[],
        limit=64,
    )

    assert summary is not None
    assert "罗碧" in summary.importance
    assert "凤凌" in summary.importance
    assert "罗碧看" not in summary.importance
    assert "罗碧看" in summary.canonical_surfaces["罗碧"]
    assert any(
        {left, right} == {"罗碧", "凤凌"}
        for left, right, _ in summary.cooccurrence_pairs
    )


def test_build_rust_zh_block_refinement_inputs_uses_block_local_pair_evidence():
    if not rust_state_proto_is_available():
        return

    summary = build_rust_zh_block_refinement_inputs(
        chapters=[
            ChapterText(
                chapter_id=1,
                text=("林秋在云港司守夜。顾衡来找林秋。林秋与顾衡继续守夜。" * 12),
            ),
            ChapterText(
                chapter_id=2,
                text=("林秋独自翻旧案卷宗。云港司里再次提起旧案。林秋继续追查旧案。" * 12),
            ),
        ],
        common_words=[],
        limit=64,
    )

    assert summary is not None
    pair_set = {(left, right) for left, right, _ in summary.cooccurrence_pairs}
    assert "林秋" in summary.importance
    assert "顾衡" in summary.importance
    assert "旧案" in summary.importance
    assert any(pair == ("云港司", "林秋") or pair == ("林秋", "云港司") for pair in pair_set)
    assert any(pair == ("顾衡", "林秋") or pair == ("林秋", "顾衡") for pair in pair_set)
    assert any(pair == ("旧案", "林秋") or pair == ("林秋", "旧案") for pair in pair_set)
    assert ("顾衡", "旧案") not in pair_set and ("旧案", "顾衡") not in pair_set


def test_build_rust_zh_block_refinement_inputs_recovers_generic_suffix_compounds():
    if not rust_state_proto_is_available():
        return

    summary = build_rust_zh_block_refinement_inputs(
        chapters=[
            ChapterText(
                chapter_id=1,
                text=(
                    "三体世界向叶文洁发来警告，科学边界讨论着三体世界。"
                    "红岸基地监听到三体世界的回音，科学边界又向汪淼展示资料。"
                    "云澈见到小妖后，小妖后回到幻妖界，小妖后再次现身。"
                )
                * 12,
            ),
        ],
        common_words=[],
        limit=64,
    )

    assert summary is not None
    assert "三体世界" in summary.importance
    assert "科学边界" in summary.importance
    assert "红岸基地" in summary.importance
    assert "小妖后" in summary.importance
    assert "三体世界" in summary.canonical_surfaces
    assert "小妖后" in summary.canonical_surfaces


def test_build_rust_zh_block_refinement_inputs_uses_single_python_bridge_call(monkeypatch):
    calls: list[list[str]] = []

    class _FakeRustModule:
        @staticmethod
        def build_zh_block_refinement_inputs_compact(
            chapters: list[str],
            common_words: list[str],
            limit: int,
        ):
            del common_words, limit
            calls.append(list(chapters))
            return (
                ["甲", "乙"],
                [(0, 2), (1, 1)],
                [(0, 1, 1)],
                [(0, [0]), (1, [1])],
            )

    monkeypatch.setattr(rust_module_bridge, "_novwr_state_proto", _FakeRustModule())

    summary = build_rust_zh_block_refinement_inputs(
        chapters=[
            ChapterText(chapter_id=1, text="甲"),
            ChapterText(chapter_id=2, text="乙"),
        ],
        common_words=[],
        limit=16,
    )

    assert calls == [["甲", "乙"]]
    assert summary is not None
    assert summary.importance == {"甲": 2, "乙": 1}
    assert summary.cooccurrence_pairs == [("甲", "乙", 1)]
    assert summary.canonical_surfaces == {"甲": ("甲",), "乙": ("乙",)}


def test_build_rust_zh_block_refinement_inputs_can_return_more_than_legacy_cap():
    if not rust_state_proto_is_available():
        return

    surnames = [
        "赵", "钱", "孙", "李", "周", "吴", "郑", "王", "冯", "陈", "褚", "卫",
        "蒋", "沈", "韩", "杨", "朱", "秦", "尤", "许", "何", "吕", "施", "张",
        "孔", "曹", "严", "华", "金", "魏", "陶", "姜", "戚", "谢", "邹", "喻",
        "柏", "水", "窦", "章",
    ]
    given_prefixes = ["安", "宁", "远", "峰", "兰", "青", "玄", "云", "星", "月"]
    given_suffixes = ["灵", "雪", "瑶", "岚", "歌", "庭", "微", "澄", "昭", "槿"]
    names = [
        f"{surname}{prefix}{suffix}"
        for surname in surnames
        for prefix in given_prefixes
        for suffix in given_suffixes
    ]
    text = "。".join(name for name in names for _ in range(3)) + "。"

    summary = build_rust_zh_block_refinement_inputs(
        chapters=[ChapterText(chapter_id=1, text=text)],
        common_words=[],
        limit=500,
    )

    assert summary is not None
    assert len(summary.importance) > 384


def test_execute_state_proto_build_fails_fast_when_rust_module_is_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(
        rust_module_bridge,
        "_novwr_state_proto",
        None,
    )

    with pytest.raises(
        RuntimeError,
        match="Rust state-proto executor is required for state-proto index builds",
    ):
        execute_state_proto_build(
            chapters=[ChapterText(chapter_id=1, text="林秋在云港旧街盘货。")],
            novel_language="zh",
            target_specs=(TargetSpec(id="lin_qiu", canonical_name="林秋"),),
        )


def test_update_plan_and_payload_assembly_round_trip_with_incremental_append():
    if not rust_state_proto_is_available():
        return

    base_request = build_rust_state_proto_request(
        chapters=[ChapterText(chapter_id=1, text="林秋在云港旧街盘货。")],
        target_specs=[TargetSpec(id="lin_qiu", canonical_name="林秋")],
        novel_language="zh",
    )
    base_payload, base_result = assemble_rust_state_proto_payload(
        request=base_request,
        chapter_shards=[
            {
                "chapter_id": 1,
                "chapter_number": 1,
                "signature": None,
                "segments": [[65537, 1, 1, 0, 10, 0, None, None]],
                "mentions": [["lin_qiu", 65537, 1.0, 0.1, 0]],
                "claims": [
                    [
                        1048577,
                        "lin_qiu",
                        "entity.current_location",
                        "云港旧街",
                        65537,
                        1,
                        2,
                        1.0,
                        1,
                        1.0,
                    ]
                ],
            }
        ],
        existing_payload=None,
    )
    assert isinstance(base_result, RustStateProtoAssembleResult)
    assert base_result.chapter_count == 1

    appended_request = build_rust_state_proto_request(
        chapters=[
            ChapterText(chapter_id=1, text="林秋在云港旧街盘货。"),
            ChapterText(chapter_id=2, text="夜里林秋来到北栈码头。"),
        ],
        target_specs=[TargetSpec(id="lin_qiu", canonical_name="林秋")],
        novel_language="zh",
    )
    plan = plan_rust_state_proto_update(
        existing_payload=base_payload,
        request=appended_request,
    )
    assert isinstance(plan, RustStateProtoUpdatePlan)
    assert plan.mode == "incremental"
    assert plan.dirty_chapter_ids == (2,)

    payload, result = assemble_rust_state_proto_payload(
        request=appended_request,
        chapter_shards=[
            {
                "chapter_id": 2,
                "chapter_number": 2,
                "signature": None,
                "segments": [[131073, 2, 2, 0, 11, 0, None, None]],
                "mentions": [["lin_qiu", 131073, 1.0, 0.1, 0]],
                "claims": [
                    [
                        2097153,
                        "lin_qiu",
                        "entity.current_location",
                        "北栈码头",
                        131073,
                        2,
                        2,
                        1.0,
                        1,
                        1.0,
                    ]
                ],
            }
        ],
        existing_payload=base_payload,
    )

    assert payload
    assert result.incremental_applied is True
    assert result.rebuilt_chapter_count == 1
    assert result.reused_chapter_count == 1
    assert result.chapter_count == 2


def test_update_plan_marks_no_changes_for_identical_payload():
    if not rust_state_proto_is_available():
        return

    request = build_rust_state_proto_request(
        chapters=[ChapterText(chapter_id=1, text="林秋在云港旧街盘货。")],
        target_specs=[TargetSpec(id="lin_qiu", canonical_name="林秋")],
        novel_language="zh",
    )
    payload, _ = build_rust_state_proto_full(request=request)

    plan = plan_rust_state_proto_update(existing_payload=payload, request=request)

    assert plan.mode == "reuse_existing"
    assert plan.no_changes is True
    assert plan.dirty_chapter_ids == ()


def test_build_full_and_incremental_rust_paths_load_into_python_runtime():
    if not rust_state_proto_is_available():
        return

    base_request = build_rust_state_proto_request(
        chapters=[
            ChapterText(chapter_id=1, text="林秋在云港旧街盘货。"),
            ChapterText(chapter_id=2, text="夜里林秋来到北栈码头等船。"),
        ],
        target_specs=[TargetSpec(id="lin_qiu", canonical_name="林秋")],
        novel_language="zh",
    )
    base_payload, base_result = build_rust_state_proto_full(request=base_request)

    assert base_result.plan_mode == "full"
    base_index = StateProtoIndex.from_msgpack(base_payload)
    assert (
        base_index.find_state("lin_qiu", SLOT_ENTITY_CURRENT_LOCATION)[
            0
        ].candidate_value_signature
        == "北栈码头"
    )

    updated_request = build_rust_state_proto_request(
        chapters=[
            ChapterText(chapter_id=1, text="林秋在云港旧街盘货。"),
            ChapterText(chapter_id=2, text="夜里林秋来到河湾书院等人。"),
            ChapterText(chapter_id=3, text="后来林秋仍在河湾书院。"),
        ],
        target_specs=[TargetSpec(id="lin_qiu", canonical_name="林秋")],
        novel_language="zh",
    )
    incremental_payload, incremental_result = update_rust_state_proto_incremental(
        existing_payload=base_payload,
        request=updated_request,
    )

    assert incremental_result.plan_mode == "incremental"
    assert incremental_result.incremental_applied is True
    assert incremental_result.rebuilt_chapter_count == 2

    incremental_index = StateProtoIndex.from_msgpack(incremental_payload)
    assert (
        incremental_index.find_state("lin_qiu", SLOT_ENTITY_CURRENT_LOCATION)[
            0
        ].candidate_value_signature
        == "河湾书院"
    )


def test_build_rust_state_proto_full_releases_gil_for_long_running_build():
    if not rust_state_proto_is_available():
        return

    target_specs = [
        TargetSpec(id=f"person_{index}", canonical_name=f"人物{index}")
        for index in range(64)
    ]
    sentence = "".join(
        f"人物{index}如今在云港司任职，人物{index}还活着。" for index in range(64)
    )
    chapters = [ChapterText(chapter_id=index + 1, text=sentence) for index in range(32)]
    request = build_rust_state_proto_request(
        chapters=chapters,
        target_specs=target_specs,
        novel_language="zh",
    )

    started = threading.Event()
    stop = threading.Event()
    tick_count = 0
    first_tick_at = None

    def _tick() -> None:
        nonlocal first_tick_at, tick_count
        started.wait()
        while not stop.is_set():
            if first_tick_at is None:
                first_tick_at = time.perf_counter()
            tick_count += 1

    thread = threading.Thread(target=_tick, daemon=True)
    thread.start()
    started.set()
    try:
        build_rust_state_proto_full(request=request)
        build_finished_at = time.perf_counter()
    finally:
        stop.set()
        thread.join(timeout=1.0)

    assert first_tick_at is not None
    assert first_tick_at < build_finished_at
    assert tick_count > 0
