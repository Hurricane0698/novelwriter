# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Explicit runtime metadata for copilot research tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AutoFollowUpHint = Literal["none", "open_first_chapter_pack"]
ToolExecutionPath = Literal["dispatch", "runtime"]
ToolSnapshotPolicy = Literal[
    "refresh_scope",
    "snapshot_bound",
    "live_read",
    "workspace_memory",
]


@dataclass(frozen=True, slots=True)
class ToolRuntimeMetadata:
    read_only: bool = True
    execution_path: ToolExecutionPath = "dispatch"
    snapshot_policy: ToolSnapshotPolicy = "snapshot_bound"
    fresh_snapshot_sensitive: bool = False
    auto_follow_up_hint: AutoFollowUpHint = "none"

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "read_only": self.read_only,
            "execution_path": self.execution_path,
            "snapshot_policy": self.snapshot_policy,
            "fresh_snapshot_sensitive": self.fresh_snapshot_sensitive,
            "auto_follow_up_hint": self.auto_follow_up_hint,
        }


@dataclass(frozen=True, slots=True)
class ResearchToolSpec:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    runtime: ToolRuntimeMetadata

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


@dataclass(frozen=True, slots=True)
class ResearchToolCatalog:
    specs: tuple[ResearchToolSpec, ...]

    def get(self, tool_name: str) -> ResearchToolSpec | None:
        return next((spec for spec in self.specs if spec.name == tool_name), None)

    @property
    def tool_schemas(self) -> list[dict[str, Any]]:
        return [spec.to_openai_schema() for spec in self.specs]
