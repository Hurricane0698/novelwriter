# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Explicit prompt-assembly contract objects for copilot runtime prompts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PromptSectionKind = Literal["static", "dynamic", "mixed"]


@dataclass(frozen=True, slots=True)
class PromptSection:
    section_id: str
    heading: str | None
    body: str
    content_kind: PromptSectionKind
    depends_on: tuple[str, ...] = ()

    def render(self) -> str:
        body = (self.body or "").strip()
        heading = (self.heading or "").strip()
        if heading and body:
            return f"{heading}\n{body}"
        return heading or body

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "id": self.section_id,
            "heading": self.heading,
            "content_kind": self.content_kind,
            "depends_on": list(self.depends_on),
            "character_count": len(self.body or ""),
        }


@dataclass(frozen=True, slots=True)
class PromptBuild:
    prompt_id: str
    locale: str
    sections: tuple[PromptSection, ...]
    prompt_text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def section_ids(self) -> list[str]:
        return [section.section_id for section in self.sections]

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "locale": self.locale,
            "section_ids": self.section_ids,
            "section_count": len(self.sections),
            "character_count": len(self.prompt_text),
            "sections": [section.to_debug_dict() for section in self.sections],
            **self.metadata,
        }


def assemble_prompt_build(
    *,
    prompt_id: str,
    locale: str,
    sections: list[PromptSection],
    metadata: dict[str, Any] | None = None,
) -> PromptBuild:
    prompt_text = "\n\n".join(
        rendered for rendered in (section.render() for section in sections) if rendered
    ).strip()
    return PromptBuild(
        prompt_id=prompt_id,
        locale=locale,
        sections=tuple(sections),
        prompt_text=prompt_text,
        metadata=dict(metadata or {}),
    )
