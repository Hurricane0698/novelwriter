import msgpack
import pytest
from unittest.mock import patch

from app.core.indexing.window_index import NovelIndex, WindowRef


def test_window_index_msgpack_round_trip():
    original = NovelIndex(
        entity_windows={
            "云澈": [
                WindowRef(window_id=1, chapter_id=1, start_pos=0, end_pos=120, entity_count=5),
                WindowRef(window_id=2, chapter_id=1, start_pos=80, end_pos=200, entity_count=3),
            ],
            "楚月仙": [
                WindowRef(window_id=1, chapter_id=1, start_pos=0, end_pos=120, entity_count=5),
            ],
        },
        window_entities={
            1: {"云澈", "楚月仙"},
            2: {"云澈"},
        },
    )

    packed = original.to_msgpack()
    restored = NovelIndex.from_msgpack(packed)

    assert isinstance(packed, bytes)
    assert restored == original


def test_window_index_msgpack_omits_window_entities_from_compact_payload():
    original = NovelIndex(
        entity_windows={
            "云澈": [
                WindowRef(window_id=1, chapter_id=1, start_pos=0, end_pos=120, entity_count=5),
            ],
            "楚月仙": [
                WindowRef(window_id=1, chapter_id=1, start_pos=0, end_pos=120, entity_count=5),
            ],
        },
        window_entities={
            1: {"云澈", "楚月仙"},
        },
    )

    payload = msgpack.unpackb(original.to_msgpack(), raw=False)

    assert payload["v"] == 2
    assert "w" not in payload
    assert payload["e"]["云澈"][0] == [1, 1, 0, 120, 5]


def test_window_index_from_msgpack_keeps_legacy_payload_compatibility():
    legacy_payload = msgpack.packb(
        {
            "entity_windows": {
                "云澈": [
                    {
                        "window_id": 1,
                        "chapter_id": 1,
                        "start_pos": 0,
                        "end_pos": 120,
                        "entity_count": 5,
                    }
                ],
                "楚月仙": [
                    {
                        "window_id": 1,
                        "chapter_id": 1,
                        "start_pos": 0,
                        "end_pos": 120,
                        "entity_count": 5,
                    }
                ],
            }
        },
        use_bin_type=True,
    )

    restored = NovelIndex.from_msgpack(legacy_payload)

    assert set(restored.window_entities[1]) == {"云澈", "楚月仙"}


@pytest.mark.parametrize("encoding", ["msgpack", "json"])
def test_state_proto_compatibility_decodes_payload_once(monkeypatch, encoding):
    import json
    from app.core.indexing import state_proto_runtime, window_index
    from app.core.indexing.state_proto_model import CoverageRepresentative, Segment, TargetSpec

    original = state_proto_runtime.StateProtoIndex(
        language="zh",
        targets={"hero": TargetSpec(id="hero", canonical_name="云澈", aliases=("小澈",))},
        segments=[Segment(1, 10, 1, 0, 120, 0)],
        coverage_reps=[CoverageRepresentative("hero", 0, 1, 3.0)],
    )
    if encoding == "json":
        monkeypatch.setattr(state_proto_runtime, "msgpack", None)
        monkeypatch.setattr(window_index, "msgpack", None)
        codec, method = json, "loads"
    else:
        codec, method = msgpack, "unpackb"
    payload = original.to_msgpack()

    with patch.object(codec, method, wraps=getattr(codec, method)) as decode:
        restored = NovelIndex.from_msgpack(payload)

    assert restored == original.to_window_index_compat()
    assert restored.window_entities[1] == {"云澈", "小澈"}
    assert decode.call_count == 1


def test_find_entity_passages_sorted_by_entity_count():
    index = NovelIndex(
        entity_windows={
            "云澈": [
                WindowRef(window_id=3, chapter_id=1, start_pos=200, end_pos=300, entity_count=2),
                WindowRef(window_id=1, chapter_id=1, start_pos=0, end_pos=100, entity_count=5),
                WindowRef(window_id=2, chapter_id=1, start_pos=100, end_pos=200, entity_count=5),
            ]
        },
        window_entities={},
    )

    top = index.find_entity_passages("云澈", limit=2)
    assert [ref.window_id for ref in top] == [1, 2]


def test_find_cooccurrence_intersection():
    index = NovelIndex(
        entity_windows={
            "云澈": [
                WindowRef(window_id=1, chapter_id=1, start_pos=0, end_pos=120, entity_count=5),
                WindowRef(window_id=2, chapter_id=1, start_pos=120, end_pos=240, entity_count=3),
                WindowRef(window_id=3, chapter_id=1, start_pos=240, end_pos=360, entity_count=2),
            ],
            "楚月仙": [
                WindowRef(window_id=1, chapter_id=1, start_pos=0, end_pos=120, entity_count=5),
                WindowRef(window_id=3, chapter_id=1, start_pos=240, end_pos=360, entity_count=2),
            ],
        },
        window_entities={},
    )

    co = index.find_cooccurrence("云澈", "楚月仙", limit=10)
    assert [ref.window_id for ref in co] == [1, 3]
