# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot LLM response parsing tests."""

class TestParseLLMResponse:
    """Verify _parse_llm_response handles real LLM output patterns."""

    def test_pure_json(self):
        from app.core.copilot.run_state import parse_llm_response as _parse_llm_response
        result = _parse_llm_response('{"answer": "hello", "suggestions": []}')
        assert result["answer"] == "hello"
        assert result["suggestions"] == []

    def test_json_in_code_block(self):
        from app.core.copilot.run_state import parse_llm_response as _parse_llm_response
        text = 'Here is my analysis:\n```json\n{"answer": "hello", "suggestions": [{"kind": "update_entity"}]}\n```\nDone.'
        result = _parse_llm_response(text)
        assert result["answer"] == "hello"
        assert len(result["suggestions"]) == 1

    def test_json_in_bare_code_block(self):
        from app.core.copilot.run_state import parse_llm_response as _parse_llm_response
        text = '```\n{"answer": "bare block", "suggestions": []}\n```'
        result = _parse_llm_response(text)
        assert result["answer"] == "bare block"

    def test_json_embedded_in_text(self):
        """LLM sometimes wraps JSON in natural language without code blocks."""
        from app.core.copilot.run_state import parse_llm_response as _parse_llm_response
        text = '根据分析结果：\n{"answer": "嵌入在文本中", "suggestions": [{"kind": "update_entity", "title": "test"}]}\n以上是建议。'
        result = _parse_llm_response(text)
        assert result["answer"] == "嵌入在文本中"
        assert len(result["suggestions"]) == 1

    def test_pure_text_fallback(self):
        """When no JSON is found, entire text becomes the answer."""
        from app.core.copilot.run_state import parse_llm_response as _parse_llm_response
        result = _parse_llm_response("Just some natural language response with no JSON.")
        assert "natural language" in result["answer"]
        assert result["suggestions"] == []

    def test_malformed_json_fallback(self):
        from app.core.copilot.run_state import parse_llm_response as _parse_llm_response
        result = _parse_llm_response('{"answer": "incomplete json')
        assert "incomplete json" in result["answer"]

    def test_mixed_markdown_with_json_block(self):
        """Real LLM pattern: markdown analysis followed by JSON block."""
        from app.core.copilot.run_state import parse_llm_response as _parse_llm_response
        text = """## 分析

孙悟空的设定需要补完。

### 建议

```json
{
  "answer": "孙悟空需要补完法宝和约束设定。",
  "cited_evidence_indices": [0, 1],
  "suggestions": [
    {
      "kind": "update_entity",
      "title": "补完法宝",
      "summary": "增加如意金箍棒属性",
      "target_resource": "entity",
      "target_id": 1,
      "delta": {"attributes": [{"key": "法宝", "surface": "如意金箍棒"}]}
    }
  ]
}
```

以上为补完建议。"""
        result = _parse_llm_response(text)
        assert "法宝" in result["answer"]
        assert len(result["suggestions"]) == 1
        assert result["suggestions"][0]["kind"] == "update_entity"

    def test_leaked_tool_call_markup_stripped_from_answer(self):
        """A final answer that still carries text-form tool-call markup must not
        surface the raw scaffolding to the user (issue #5 degradation)."""
        from app.core.copilot.run_state import parse_llm_response as _parse_llm_response
        text = '分析完成。\n<tool_call>{"name": "find", "arguments": {"query": "x"}}</tool_call>'
        result = _parse_llm_response(text)
        assert "tool_call" not in result["answer"]
        assert "find" not in result["answer"]
        assert "分析完成" in result["answer"]
        assert result["suggestions"] == []

    def test_clean_json_answer_untouched_by_markup_strip(self):
        from app.core.copilot.run_state import parse_llm_response as _parse_llm_response
        result = _parse_llm_response('{"answer": "孙悟空是主角", "suggestions": []}')
        assert result["answer"] == "孙悟空是主角"
        assert result["suggestions"] == []
