# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Tests for text-form tool-call recovery and markup stripping (issue #5).

Some OpenAI-compatible gateways return a tool call inside the assistant content
string instead of the structured tool_calls field. These tests pin the dialects
we salvage and the degradation that keeps raw markup out of user-facing answers.
"""

import json

from app.core.copilot.tool_call_recovery import (
    contains_tool_call_markup,
    recover_tool_calls_from_text,
    strip_tool_call_markup,
)

VALID = {"load_scope_snapshot", "find", "open", "open_many", "read"}


def _args(call):
    return json.loads(call.arguments)


class TestRecover:
    def test_hermes_qwen_tool_call(self):
        text = '<tool_call>\n{"name": "find", "arguments": {"query": "孙悟空"}}\n</tool_call>'
        calls = recover_tool_calls_from_text(text, VALID)
        assert len(calls) == 1
        assert calls[0].name == "find"
        assert _args(calls[0]) == {"query": "孙悟空"}

    def test_multiple_tool_calls(self):
        text = (
            '<tool_call>{"name": "find", "arguments": {"query": "张三"}}</tool_call>\n'
            '<tool_call>{"name": "read", "arguments": {"target_refs": [{"type": "entity", "id": 1}]}}</tool_call>'
        )
        calls = recover_tool_calls_from_text(text, VALID)
        assert [c.name for c in calls] == ["find", "read"]
        assert calls[0].id != calls[1].id

    def test_nested_braces_in_arguments(self):
        text = '<tool_call>{"name": "read", "arguments": {"target_refs": [{"type": "entity", "id": 7}]}}</tool_call>'
        calls = recover_tool_calls_from_text(text, VALID)
        assert len(calls) == 1
        assert _args(calls[0])["target_refs"][0]["id"] == 7

    def test_function_named_tag(self):
        text = '<function=open>{"pack_id": "p1", "expand_chars": 2000}</function>'
        calls = recover_tool_calls_from_text(text, VALID)
        assert len(calls) == 1
        assert calls[0].name == "open"
        assert _args(calls[0])["pack_id"] == "p1"

    def test_mistral_tool_calls_array(self):
        text = '[TOOL_CALLS] [{"name": "find", "arguments": {"query": "悟空"}}]'
        calls = recover_tool_calls_from_text(text, VALID)
        assert len(calls) == 1
        assert calls[0].name == "find"

    def test_deepseek_special_tokens(self):
        text = (
            "<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>function<｜tool▁sep｜>find\n"
            '```json\n{"query": "悟空"}\n```<｜tool▁call▁end｜><｜tool▁calls▁end｜>'
        )
        calls = recover_tool_calls_from_text(text, VALID)
        assert len(calls) == 1
        assert calls[0].name == "find"
        assert _args(calls[0]) == {"query": "悟空"}

    def test_bare_function_shaped_json(self):
        text = '{"name": "find", "arguments": {"query": "主角"}}'
        calls = recover_tool_calls_from_text(text, VALID)
        assert len(calls) == 1
        assert calls[0].name == "find"

    def test_prose_then_tool_call(self):
        text = '我先检索一下相关章节。\n<tool_call>{"name": "find", "arguments": {"query": "金箍棒"}}</tool_call>'
        calls = recover_tool_calls_from_text(text, VALID)
        assert len(calls) == 1
        assert calls[0].name == "find"

    def test_arguments_as_json_string(self):
        text = '<tool_call>{"name": "find", "arguments": "{\\"query\\": \\"x\\"}"}</tool_call>'
        calls = recover_tool_calls_from_text(text, VALID)
        assert len(calls) == 1
        assert _args(calls[0]) == {"query": "x"}

    def test_unknown_tool_name_not_recovered(self):
        text = '<tool_call>{"name": "delete_everything", "arguments": {}}</tool_call>'
        assert recover_tool_calls_from_text(text, VALID) == []

    def test_legit_answer_json_not_recovered(self):
        text = '{"answer": "孙悟空是主角", "suggestions": [{"kind": "update_entity"}]}'
        assert recover_tool_calls_from_text(text, VALID) == []

    def test_plain_prose_not_recovered(self):
        assert recover_tool_calls_from_text("孙悟空是齐天大圣。", VALID) == []

    def test_empty_content(self):
        assert recover_tool_calls_from_text("", VALID) == []
        assert recover_tool_calls_from_text(None, VALID) == []


class TestStripAndDetect:
    def test_detect_wrapper_markup(self):
        assert contains_tool_call_markup('<tool_call>{"name": "find"}</tool_call>')
        assert contains_tool_call_markup('<function=read>{}</function>')
        assert not contains_tool_call_markup('{"answer": "ok", "suggestions": []}')
        assert not contains_tool_call_markup("普通的分析文本。")

    def test_strip_keeps_surrounding_prose(self):
        text = '分析完成。\n<tool_call>{"name": "find", "arguments": {"query": "x"}}</tool_call>\n以上。'
        cleaned = strip_tool_call_markup(text)
        assert "tool_call" not in cleaned
        assert "find" not in cleaned
        assert "分析完成。" in cleaned
        assert "以上。" in cleaned

    def test_strip_pure_markup_yields_empty(self):
        text = '<tool_call>{"name": "find", "arguments": {"query": "x"}}</tool_call>'
        assert strip_tool_call_markup(text) == ""

    def test_strip_leaves_clean_answer_untouched(self):
        text = "孙悟空是主角，需要补完法宝设定。"
        assert strip_tool_call_markup(text) == text

    def test_strip_deepseek_tokens(self):
        text = (
            "结论如下。<｜tool▁call▁begin｜>function<｜tool▁sep｜>find\n"
            '```json\n{"query": "x"}\n```<｜tool▁call▁end｜>'
        )
        cleaned = strip_tool_call_markup(text)
        assert "结论如下。" in cleaned
        assert "tool▁call" not in cleaned
