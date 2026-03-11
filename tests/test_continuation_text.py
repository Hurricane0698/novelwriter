from types import SimpleNamespace

from app.core.continuation_text import (
    append_user_instruction_for_relevance,
    format_recent_chapters_for_prompt,
    format_world_context_for_prompt,
)


def test_format_recent_chapters_for_prompt_preserves_existing_shape():
    chapters = [
        SimpleNamespace(chapter_number=1, title="第一章", content="云澈看向远方。"),
        SimpleNamespace(chapter_number=2, title="第二章", content="楚月仙静坐不语。"),
    ]

    result = format_recent_chapters_for_prompt(chapters)

    assert "【Chapter 1: 第一章】" in result
    assert "云澈看向远方。" in result
    assert "【Chapter 2: 第二章】" in result
    assert "楚月仙静坐不语。" in result


def test_append_user_instruction_for_relevance_uses_dedicated_heading():
    result = append_user_instruction_for_relevance("recent text", "请继续写云澈的内心戏")

    assert result.endswith("【用户续写指令】\n请继续写云澈的内心戏")


def test_format_world_context_for_prompt_renders_sections_without_constraints_inline():
    writer_ctx = {
        "systems": [
            {
                "name": "修炼体系",
                "display_type": "list",
                "description": "玄气等级划分",
                "data": {"items": [{"label": "真玄境", "description": "基础境界"}]},
                "constraints": ["每章最多一次时间跳转"],
            }
        ],
        "entities": [
            {
                "id": 1,
                "name": "云澈",
                "entity_type": "Character",
                "description": "主角",
                "aliases": ["小澈"],
                "attributes": [{"key": "身份", "surface": "苍风弟子"}],
            },
            {
                "id": 2,
                "name": "楚月仙",
                "entity_type": "Character",
                "description": "师父",
                "aliases": [],
                "attributes": [],
            },
        ],
        "relationships": [
            {
                "source_id": 1,
                "target_id": 2,
                "label": "师徒",
                "description": "云澈拜楚月仙为师",
            }
        ],
    }

    result = format_world_context_for_prompt(writer_ctx)

    assert "〈世界体系〉" in result
    assert "〈角色与事物〉" in result
    assert "〈人物关系〉" in result
    assert "修炼体系" in result
    assert "真玄境：基础境界" in result
    assert "别名：小澈" in result
    assert "身份：苍风弟子" in result
    assert "云澈 —师徒→ 楚月仙：云澈拜楚月仙为师" in result
    assert "每章最多一次时间跳转" not in result
