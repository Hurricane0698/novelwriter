# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only


"""Structured extraction contracts for world generation."""

from __future__ import annotations

from typing import Literal, cast
from pydantic import BaseModel, ConfigDict, Field, field_validator

WORLDGEN_ORIGIN = "worldgen"
WorldGenSystemDisplayType = Literal["list", "hierarchy", "timeline"]


def _normalize_worldgen_system_display_type(
    display_type: str | None,
) -> WorldGenSystemDisplayType:
    normalized = str(display_type or "").strip().lower()
    if normalized in {"list", "hierarchy", "timeline"}:
        return cast(WorldGenSystemDisplayType, normalized)
    return "list"


class WorldGenEntity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=255)
    entity_type: str = Field(min_length=1, max_length=50)
    description: str = ""
    aliases: list[str] = Field(default_factory=list)


class WorldGenRelationship(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str = Field(min_length=1, max_length=255)
    target: str = Field(min_length=1, max_length=255)
    label: str = Field(min_length=1, max_length=100)
    description: str = ""


class WorldGenSystemItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str = Field(min_length=1, max_length=255)
    description: str | None = None
    time: str | None = None
    children: list["WorldGenSystemItem"] = Field(default_factory=list)


WorldGenSystemItem.model_rebuild()


class WorldGenSystem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    display_type: WorldGenSystemDisplayType = "list"
    items: list[WorldGenSystemItem] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)

    @field_validator("display_type", mode="before")
    @classmethod
    def _normalize_display_type(cls, value: object) -> object:
        return _normalize_worldgen_system_display_type(cast(str | None, value))


class WorldGenLLMOutput(BaseModel):
    """Intermediate schema: LLM extracts content only; server fills metadata/defaults."""

    model_config = ConfigDict(extra="ignore")

    entities: list[WorldGenEntity] = Field(default_factory=list)
    relationships: list[WorldGenRelationship] = Field(default_factory=list)
    systems: list[WorldGenSystem] = Field(default_factory=list)
