# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Recover tool calls that a gateway emitted as plain text.

Some OpenAI-compatible gateways/models return a tool call inside the
assistant ``content`` string instead of the structured ``tool_calls`` field
(Hermes/Qwen ``<tool_call>``, Mistral ``[TOOL_CALLS]``, DeepSeek special
tokens, ``<function=...>`` tags, or a bare function-shaped JSON object). When
that happens the copilot tool loop sees ``response.tool_calls == []`` and the
raw markup leaks into the user-facing answer with no retrieval executed and no
suggestion cards compiled.

This module is the single place that understands those text dialects. It is
used two ways:

* ``recover_tool_calls_from_text`` — salvage recognized calls back into
  structured :class:`ToolCall` objects so the tool loop can keep going.
* ``strip_tool_call_markup`` — degradation safety net that removes the markup
  from any final answer text so the user never sees raw tool-call code.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable

from app.core.ai_client import ToolCall

logger = logging.getLogger(__name__)

# Wrapper markup that unambiguously denotes a text-form tool call. These are
# stripped from final answers regardless of whether the inner name resolves to
# a known tool, because users should never see this transport-level scaffolding.
_STRIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<tool_call>\s*\{.*?\}\s*</tool_call>", re.DOTALL),
    re.compile(r"<tool_call>\s*\{.*\}\s*$", re.DOTALL),  # unclosed, trailing
    re.compile(r"<function_call>\s*\{.*?\}\s*</function_call>", re.DOTALL),
    re.compile(r"<function=[^>]*>.*?</function>", re.DOTALL),
    re.compile(r"\[TOOL_CALLS\]\s*(?:\[.*\]|\{.*\})\s*$", re.DOTALL),
    re.compile(r"<｜tool▁calls▁begin｜>.*?<｜tool▁calls▁end｜>", re.DOTALL),
    re.compile(r"<｜tool▁call▁begin｜>.*?<｜tool▁call▁end｜>", re.DOTALL),
)

# Locators used to find where a text-form call starts, so the JSON payload can
# be extracted with a brace-balanced scan (regex cannot count nested braces).
_TOOL_CALL_TAG = re.compile(r"<tool_call>", re.IGNORECASE)
_FUNCTION_CALL_TAG = re.compile(r"<function_call>", re.IGNORECASE)
_FUNCTION_NAMED_TAG = re.compile(r"<function=([A-Za-z0-9_.-]+)>", re.IGNORECASE)
_MISTRAL_TAG = re.compile(r"\[TOOL_CALLS\]")
_DEEPSEEK_CALL = re.compile(
    r"<｜tool▁call▁begin｜>.*?<｜tool▁sep｜>\s*([A-Za-z0-9_.-]+)",
    re.DOTALL,
)


def _scan_balanced(text: str, start: int, open_ch: str, close_ch: str) -> str | None:
    """Return the first brace/bracket-balanced span at/after ``start``.

    Respects string literals so braces inside JSON strings do not unbalance the
    scan. Returns ``None`` if no balanced span is found.
    """
    begin = text.find(open_ch, start)
    if begin == -1:
        return None
    depth = 0
    in_str = False
    escaped = False
    quote = ""
    for idx in range(begin, len(text)):
        ch = text[idx]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[begin : idx + 1]
    return None


def _coerce_arguments(raw: Any) -> str:
    """Normalize a parsed arguments value to a raw JSON string."""
    if raw is None:
        return "{}"
    if isinstance(raw, str):
        candidate = raw.strip()
        if not candidate:
            return "{}"
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            # Argument string was not JSON; wrap so downstream json.loads is safe.
            return json.dumps({"value": raw}, ensure_ascii=False)
    try:
        return json.dumps(raw, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"


def _call_from_object(obj: Any, valid_tool_names: Iterable[str]) -> tuple[str, str] | None:
    """Build (name, arguments_json) from a function-shaped JSON object."""
    if not isinstance(obj, dict):
        return None
    name = obj.get("name") or obj.get("tool") or obj.get("function")
    if isinstance(name, dict):  # e.g. {"function": {"name": ..., "arguments": ...}}
        inner = name
        name = inner.get("name")
        args_source: Any = inner.get("arguments", inner.get("parameters"))
    else:
        args_source = obj.get("arguments", obj.get("parameters", obj.get("args")))
    if not isinstance(name, str) or name not in set(valid_tool_names):
        return None
    return name, _coerce_arguments(args_source)


def _iter_json_objects(text: str) -> Iterable[str]:
    """Yield each top-level balanced JSON object substring in ``text``."""
    cursor = 0
    while True:
        nxt = text.find("{", cursor)
        if nxt == -1:
            return
        span = _scan_balanced(text, nxt, "{", "}")
        if span is None:
            return
        yield span
        cursor = nxt + len(span)


def recover_tool_calls_from_text(
    content: str | None,
    valid_tool_names: Iterable[str],
) -> list[ToolCall]:
    """Salvage text-form tool calls from assistant ``content``.

    Only calls whose name resolves to ``valid_tool_names`` are returned, so
    ordinary prose or a legitimate final-answer JSON object (which has no
    ``name`` key) is never misread as a tool call.
    """
    if not content:
        return []
    valid = set(valid_tool_names)
    recovered: list[tuple[str, str]] = []

    # 1. Hermes/Qwen <tool_call>{...}</tool_call> and <function_call>{...}.
    for tag in (_TOOL_CALL_TAG, _FUNCTION_CALL_TAG):
        for match in tag.finditer(content):
            span = _scan_balanced(content, match.end(), "{", "}")
            if not span:
                continue
            try:
                parsed = json.loads(span)
            except json.JSONDecodeError:
                continue
            call = _call_from_object(parsed, valid)
            if call:
                recovered.append(call)

    # 2. <function=NAME>{...args...}</function>.
    for match in _FUNCTION_NAMED_TAG.finditer(content):
        name = match.group(1)
        if name not in valid:
            continue
        span = _scan_balanced(content, match.end(), "{", "}")
        recovered.append((name, _coerce_arguments(span)))

    # 3. Mistral [TOOL_CALLS] [ {...}, ... ].
    for match in _MISTRAL_TAG.finditer(content):
        array_span = _scan_balanced(content, match.end(), "[", "]")
        payloads: list[Any] = []
        if array_span:
            try:
                payloads = json.loads(array_span)
            except json.JSONDecodeError:
                payloads = []
        else:
            obj_span = _scan_balanced(content, match.end(), "{", "}")
            if obj_span:
                try:
                    payloads = [json.loads(obj_span)]
                except json.JSONDecodeError:
                    payloads = []
        for obj in payloads if isinstance(payloads, list) else []:
            call = _call_from_object(obj, valid)
            if call:
                recovered.append(call)

    # 4. DeepSeek <｜tool▁call▁begin｜>...<｜tool▁sep｜>NAME ... ```json {...} ```.
    for match in _DEEPSEEK_CALL.finditer(content):
        name = match.group(1)
        if name not in valid:
            continue
        span = _scan_balanced(content, match.end(), "{", "}")
        recovered.append((name, _coerce_arguments(span)))

    # 5. Fallback: bare function-shaped JSON object(s) with no wrapper. Guarded
    #    by valid_tool_names membership so the real answer JSON is left alone.
    if not recovered:
        for obj_span in _iter_json_objects(content):
            try:
                parsed = json.loads(obj_span)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                continue
            call = _call_from_object(parsed, valid)
            if call:
                recovered.append(call)

    if not recovered:
        return []

    logger.warning(
        "Recovered %d text-form tool call(s) from assistant content: %s",
        len(recovered),
        ", ".join(name for name, _ in recovered),
    )
    return [
        ToolCall(id=f"recovered_{idx + 1}", name=name, arguments=arguments)
        for idx, (name, arguments) in enumerate(recovered)
    ]


def contains_tool_call_markup(content: str | None) -> bool:
    """True when ``content`` still carries recognizable tool-call wrapper markup."""
    if not content:
        return False
    return any(pattern.search(content) for pattern in _STRIP_PATTERNS)


def strip_tool_call_markup(content: str | None) -> str:
    """Remove tool-call wrapper markup so a final answer never shows raw code."""
    if not content:
        return ""
    cleaned = content
    for pattern in _STRIP_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    # Collapse blank lines left behind by removed blocks.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
