import types


def test_postcheck_flags_unknown_terms_and_address_tokens():
    from app.core.continuation_postcheck import postcheck_continuation

    writer_ctx = {
        "entities": [
            {"name": "夏倾月", "aliases": ["神无忆"]},
            {"name": "神无厌夜", "aliases": []},
        ],
        "systems": [],
    }
    recent_text = "神无忆缓步走入殿中。"

    cont = types.SimpleNamespace(
        content="神无厌夜冷笑道：“忆儿！把‘永夜渊’给本尊！”"
    )

    warnings = postcheck_continuation(
        writer_ctx=writer_ctx,
        recent_text=recent_text,
        user_prompt=None,
        continuations=[cont],
    )

    assert any(w.code == "unknown_address_token" and w.term == "忆儿" for w in warnings)
    assert any(w.code == "unknown_term_quoted" and w.term == "永夜渊" for w in warnings)
    assert all(w.version == 1 for w in warnings)

