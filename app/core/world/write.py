# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Shared write-side policies for world-model CRUD flows."""

from __future__ import annotations

from typing import Any, Protocol, cast

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import WorldRelationship
from app.schemas import SystemDisplayType, normalize_and_validate_system_data
from app.world_relationships import canonicalize_relationship_label

AI_DRAFT_ORIGINS = frozenset({"bootstrap", "worldgen"})
MANUAL_ORIGIN = "manual"
WORLDPACK_ORIGIN = "worldpack"
RelationshipSignature = tuple[int, int, str]


class RelationshipConflictError(RuntimeError):
    """Raised when a relationship write collides with an existing canonical signature."""


class InvalidSystemDisplayTypeError(ValueError):
    """Raised when a stored system row uses an unsupported display type."""


class _HasOrigin(Protocol):
    origin: str


class _HasOriginAndStatus(_HasOrigin, Protocol):
    status: str


class _HasOriginAndWorldpackPackId(_HasOrigin, Protocol):
    worldpack_pack_id: str | None


class _HasRelationshipSignatureFields(Protocol):
    source_id: int
    target_id: int
    label: str
    label_canonical: str | None


def is_worldpack_origin(row: _HasOrigin) -> bool:
    return row.origin == WORLDPACK_ORIGIN


def is_worldpack_controlled_by_pack(row: _HasOriginAndWorldpackPackId, *, pack_id: str) -> bool:
    return is_worldpack_origin(row) and row.worldpack_pack_id == pack_id


def promote_worldpack_origin_to_manual(row: _HasOrigin) -> bool:
    if not is_worldpack_origin(row):
        return False
    row.origin = MANUAL_ORIGIN
    return True


def promote_ai_draft_origin_to_manual(row: _HasOriginAndStatus) -> bool:
    if row.status != "draft" or row.origin not in AI_DRAFT_ORIGINS:
        return False
    row.origin = MANUAL_ORIGIN
    return True


def ensure_relationship_is_unique(
    db: Session,
    *,
    novel_id: int,
    source_id: int,
    target_id: int,
    label: str,
    exclude_relationship_id: int | None = None,
) -> None:
    _, _, label_canonical = build_relationship_signature(
        source_id=source_id,
        target_id=target_id,
        label=label,
    )
    query = db.query(WorldRelationship.id).filter(
        WorldRelationship.novel_id == novel_id,
        WorldRelationship.source_id == source_id,
        WorldRelationship.target_id == target_id,
        WorldRelationship.label_canonical == label_canonical,
    )
    if exclude_relationship_id is not None:
        query = query.filter(WorldRelationship.id != exclude_relationship_id)
    if query.first() is not None:
        raise RelationshipConflictError("Relationship conflict")


def build_relationship_signature(
    *,
    source_id: int,
    target_id: int,
    label: str | None = None,
    label_canonical: str | None = None,
) -> RelationshipSignature:
    canonical = str(label_canonical or "").strip()
    if not canonical:
        canonical = canonicalize_relationship_label(label or "")
    return (int(source_id), int(target_id), canonical)


def relationship_signature_from_row(row: _HasRelationshipSignatureFields) -> RelationshipSignature:
    return build_relationship_signature(
        source_id=row.source_id,
        target_id=row.target_id,
        label=row.label,
        label_canonical=row.label_canonical,
    )


def normalize_system_data_for_write(display_type: str, data: Any) -> dict:
    try:
        return normalize_and_validate_system_data(cast(SystemDisplayType, display_type), data)
    except ValidationError:
        raise
    except ValueError as exc:
        raise InvalidSystemDisplayTypeError(str(exc)) from exc
