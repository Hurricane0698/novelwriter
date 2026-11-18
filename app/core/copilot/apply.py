# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Copilot apply application service.

This module owns the approval boundary: suggestion execution, transactional
world-model writes, dependency resolution, and suggestion status persistence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.copilot.messages import CopilotTextKey, get_copilot_text
from app.core.world.crud import WorldCrudError
from app.models import CopilotRun, WorldEntity, WorldRelationship, WorldSystem
from app.schemas import (
    WorldAttributeCreate,
    WorldAttributeUpdate,
    WorldEntityCreate,
    WorldEntityUpdate,
    WorldRelationshipCreate,
    WorldRelationshipUpdate,
    WorldSystemCreate,
    WorldSystemUpdate,
)

logger = logging.getLogger(__name__)


def _apply_text(
    interaction_locale: str,
    text_key: CopilotTextKey,
    **params: object,
) -> str:
    return get_copilot_text(text_key, locale=interaction_locale, **params)


@dataclass
class ApplyResult:
    suggestion_id: str
    success: bool
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class _ApplyDomainError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


@dataclass
class _StagedApplySuccess:
    suggestion_id: str
    action_result: dict[str, Any] | None = None


@dataclass
class _ApplyTransactionState:
    in_progress: set[str] = field(default_factory=set)
    staged_successes: list[_StagedApplySuccess] = field(default_factory=list)


class _ApplyAbort(RuntimeError):
    def __init__(self, result: ApplyResult) -> None:
        super().__init__(result.error_message or result.error_code or "apply_aborted")
        self.result = result


def _build_apply_error_message(
    code: str,
    suggestion: dict[str, Any] | None = None,
    interaction_locale: str = "zh",
) -> str:
    if code == "suggestion_not_found":
        return _apply_text(interaction_locale, CopilotTextKey.APPLY_ERROR_SUGGESTION_NOT_FOUND)
    if code == "already_applied":
        return _apply_text(interaction_locale, CopilotTextKey.APPLY_ERROR_ALREADY_APPLIED)
    if code == "not_actionable":
        reason = ((suggestion or {}).get("preview") or {}).get("non_actionable_reason")
        return (
            str(reason)
            if isinstance(reason, str) and reason.strip()
            else _apply_text(interaction_locale, CopilotTextKey.SUGGESTION_REASON_NOT_DIRECTLY_APPLICABLE)
        )
    if code == "copilot_target_stale":
        return _apply_text(interaction_locale, CopilotTextKey.APPLY_ERROR_STALE)
    if code == "dependency_apply_failed":
        return _apply_text(interaction_locale, CopilotTextKey.APPLY_ERROR_DEPENDENCY_FAILED)
    return _apply_text(interaction_locale, CopilotTextKey.APPLY_ERROR_GENERIC)


def _collect_dependency_suggestion_ids(action: dict[str, Any]) -> list[str]:
    endpoint_dependencies = action.get("endpoint_dependencies")
    if not isinstance(endpoint_dependencies, dict):
        return []

    dependency_ids: list[str] = []
    for value in endpoint_dependencies.values():
        if not isinstance(value, dict):
            continue
        suggestion_id = value.get("suggestion_id")
        if isinstance(suggestion_id, str) and suggestion_id not in dependency_ids:
            dependency_ids.append(suggestion_id)
    return dependency_ids


def _extract_applied_entity_id(
    db: Session,
    novel_id: int,
    suggestion: dict[str, Any],
) -> int | None:
    applied_resource_id = suggestion.get("applied_resource_id")
    if isinstance(applied_resource_id, int):
        return applied_resource_id

    apply_action = suggestion.get("apply") or {}
    if apply_action.get("type") != "create_entity":
        return None

    data = apply_action.get("data") or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return None

    entity = (
        db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel_id, WorldEntity.name == name)
        .order_by(WorldEntity.id.desc())
        .first()
    )
    return entity.id if entity else None


def _resolve_relationship_endpoint_entity_id(
    db: Session,
    novel_id: int,
    endpoint_ref: dict[str, Any],
    suggestions_by_id: dict[str, dict[str, Any]],
) -> int:
    kind = endpoint_ref.get("kind")
    if kind == "existing" and isinstance(endpoint_ref.get("entity_id"), int):
        return int(endpoint_ref["entity_id"])
    if kind == "suggestion":
        suggestion_id = endpoint_ref.get("suggestion_id")
        if not isinstance(suggestion_id, str):
            raise _ApplyDomainError(code="dependency_apply_failed", message="Dependency suggestion missing", status_code=409)
        suggestion = suggestions_by_id.get(suggestion_id)
        if suggestion is None:
            raise _ApplyDomainError(code="dependency_apply_failed", message="Dependency suggestion missing", status_code=409)
        entity_id = _extract_applied_entity_id(db, novel_id, suggestion)
        if entity_id is None:
            raise _ApplyDomainError(code="dependency_apply_failed", message="Dependency entity missing", status_code=409)
        return entity_id
    raise _ApplyDomainError(code="dependency_apply_failed", message="Relationship endpoint unresolved", status_code=409)


def apply_suggestions(
    db: Session,
    run: CopilotRun,
    suggestion_ids: list[str],
    interaction_locale: str = "zh",
) -> list[ApplyResult]:
    """Apply selected suggestions transactionally.

    Each top-level suggestion is isolated from the others, but any same-run
    dependencies it requires are applied in the same transaction.
    """
    if (run.context_json or {}).get("text_review"):
        from app.core.copilot.text_review_apply import lock_review_run
        lock_review_run(db, run)
    initial_suggestions = list(run.suggestions_json or [])
    suggestion_order = [s["suggestion_id"] for s in initial_suggestions if isinstance(s, dict) and "suggestion_id" in s]
    suggestions_by_id = {s["suggestion_id"]: s for s in initial_suggestions if isinstance(s, dict) and "suggestion_id" in s}
    results_by_id: dict[str, ApplyResult] = {}
    result_order: list[str] = []

    def _record_result(result: ApplyResult) -> ApplyResult:
        if result.suggestion_id not in results_by_id:
            result_order.append(result.suggestion_id)
        results_by_id[result.suggestion_id] = result
        return result

    def _ordered_results() -> list[ApplyResult]:
        ordered_ids = [sid for sid in suggestion_order if sid in results_by_id]
        ordered_ids.extend(sid for sid in result_order if sid not in ordered_ids)
        return [results_by_id[sid] for sid in ordered_ids]

    def _persist_suggestions_json() -> None:
        run.suggestions_json = [suggestions_by_id[sid] for sid in suggestion_order if sid in suggestions_by_id]
        flag_modified(run, "suggestions_json")

    def _mark_staged_successes_applied(tx_state: _ApplyTransactionState) -> None:
        for staged in tx_state.staged_successes:
            suggestion = suggestions_by_id.get(staged.suggestion_id)
            if suggestion is None:
                continue
            suggestion["status"] = "applied"
            action_result = staged.action_result or {}
            applied_resource_id = (
                action_result.get("entity_id")
                or action_result.get("relationship_id")
                or action_result.get("system_id")
            )
            if isinstance(applied_resource_id, int):
                suggestion["applied_resource_id"] = applied_resource_id
            _record_result(ApplyResult(staged.suggestion_id, True))
        _persist_suggestions_json()

    def _abort_result(
        suggestion_id: str,
        code: str,
        suggestion: dict[str, Any] | None = None,
    ) -> _ApplyAbort:
        return _ApplyAbort(ApplyResult(
            suggestion_id,
            False,
            code,
            _build_apply_error_message(code, suggestion, interaction_locale),
        ))

    def _apply_one_inner(
        suggestion_id: str,
        *,
        auto_dependency: bool,
        tx_state: _ApplyTransactionState,
    ) -> None:
        suggestion = suggestions_by_id.get(suggestion_id)
        if suggestion is None:
            raise _abort_result(suggestion_id, "suggestion_not_found")

        if suggestion.get("status") == "applied":
            if auto_dependency:
                return
            raise _abort_result(suggestion_id, "already_applied")

        if not suggestion.get("apply") or not suggestion.get("preview", {}).get("actionable", False):
            raise _abort_result(suggestion_id, "not_actionable", suggestion)

        if suggestion_id in tx_state.in_progress:
            raise _abort_result(suggestion_id, "dependency_apply_failed")

        tx_state.in_progress.add(suggestion_id)
        try:
            for dependency_id in _collect_dependency_suggestion_ids(suggestion["apply"]):
                try:
                    _apply_one_inner(
                        dependency_id,
                        auto_dependency=True,
                        tx_state=tx_state,
                    )
                except _ApplyAbort:
                    raise _abort_result(suggestion_id, "dependency_apply_failed") from None

            if suggestion["apply"].get("review_guards"):
                from app.core.copilot.text_review_apply import validate_guards
                from fastapi import HTTPException
                try:
                    validate_guards(db, run.novel_id, suggestion["apply"]["review_guards"])
                except HTTPException:
                    raise _abort_result(suggestion_id, "copilot_target_stale") from None
            action_result = _execute_apply_action(
                db,
                run.novel_id,
                suggestion["apply"],
                suggestions_by_id=suggestions_by_id,
            )
            if suggestion["apply"].get("source_refs"):
                from app.core.copilot.text_review_apply import attach_action_sources
                attach_action_sources(db, suggestion["apply"], action_result)
            tx_state.staged_successes.append(
                _StagedApplySuccess(
                    suggestion_id=suggestion_id,
                    action_result=action_result if isinstance(action_result, dict) else None,
                )
            )
        finally:
            tx_state.in_progress.discard(suggestion_id)

    def _apply_one(suggestion_id: str) -> ApplyResult:
        existing_result = results_by_id.get(suggestion_id)
        if existing_result is not None and existing_result.success:
            return existing_result

        tx_state = _ApplyTransactionState()
        suggestion = suggestions_by_id.get(suggestion_id)

        try:
            with db.begin_nested():
                _apply_one_inner(
                    suggestion_id,
                    auto_dependency=False,
                    tx_state=tx_state,
                )
                _mark_staged_successes_applied(tx_state)
            db.commit()
            return results_by_id.get(suggestion_id) or _record_result(ApplyResult(suggestion_id, True))
        except _ApplyAbort as exc:
            db.rollback()
            db.expire_all()
            return _record_result(exc.result)
        except (_ApplyDomainError, WorldCrudError) as exc:
            db.rollback()
            db.expire_all()
            error_code = getattr(exc, "code", "apply_error")
            return _record_result(ApplyResult(
                suggestion_id,
                False,
                error_code,
                _build_apply_error_message(error_code, suggestion, interaction_locale),
            ))
        except Exception:
            db.rollback()
            db.expire_all()
            logger.warning("Apply suggestion %s failed", suggestion_id, exc_info=True)
            return _record_result(ApplyResult(
                suggestion_id,
                False,
                "apply_error",
                _build_apply_error_message("apply_error", suggestion, interaction_locale),
            ))

    for sid in suggestion_ids:
        _apply_one(sid)

    return _ordered_results()


def _execute_apply_action(
    db: Session,
    novel_id: int,
    action: dict[str, Any],
    *,
    suggestions_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Execute a single apply action inside the caller's transaction."""
    from app.core.world import crud as world_crud

    action_type = action.get("type")
    data = action.get("data", {})

    if action_type == "create_entity":
        validated = WorldEntityCreate.model_validate(data)
        entity = world_crud.stage_create_entity(
            novel_id,
            {
                **validated.model_dump(),
                "origin": "manual",
                "status": "confirmed",
            },
            db,
        )
        for attr_action in action.get("deferred_attribute_actions", []):
            attr_data = attr_action.get("data", {})
            attr_validated = WorldAttributeCreate.model_validate(attr_data)
            world_crud.stage_create_attribute(novel_id, entity.id, attr_validated.model_dump(), db)
        return {"entity_id": entity.id}

    if action_type == "update_entity":
        entity_id = action.get("entity_id")
        if not entity_id:
            raise _ApplyDomainError(code="missing_entity_id", message="Missing entity_id", status_code=400)
        entity = db.query(WorldEntity).filter(WorldEntity.id == entity_id, WorldEntity.novel_id == novel_id).first()
        if not entity:
            raise _ApplyDomainError(code="copilot_target_stale", message="Entity no longer exists", status_code=409)
        if data:
            validated = WorldEntityUpdate.model_validate(data)
            world_crud.stage_update_entity(novel_id, entity_id, validated.model_dump(exclude_unset=True), db)
        for attr_action in action.get("attribute_actions", []):
            _execute_attribute_action(db, novel_id, attr_action)
        return {"entity_id": entity_id}

    if action_type == "create_relationship":
        relationship_data = dict(data)
        endpoint_dependencies = action.get("endpoint_dependencies")
        if isinstance(endpoint_dependencies, dict) and isinstance(suggestions_by_id, dict):
            if "source_id" not in relationship_data:
                source_ref = endpoint_dependencies.get("source")
                if isinstance(source_ref, dict):
                    relationship_data["source_id"] = _resolve_relationship_endpoint_entity_id(
                        db,
                        novel_id,
                        source_ref,
                        suggestions_by_id,
                    )
            if "target_id" not in relationship_data:
                target_ref = endpoint_dependencies.get("target")
                if isinstance(target_ref, dict):
                    relationship_data["target_id"] = _resolve_relationship_endpoint_entity_id(
                        db,
                        novel_id,
                        target_ref,
                        suggestions_by_id,
                    )

        validated = WorldRelationshipCreate.model_validate(relationship_data)
        rel = world_crud.stage_create_relationship(
            novel_id,
            {
                **validated.model_dump(),
                "origin": "manual",
                "status": "confirmed",
            },
            db,
        )
        return {"relationship_id": rel.id}

    if action_type == "update_relationship":
        rel_id = action.get("relationship_id")
        if not rel_id:
            raise _ApplyDomainError(code="missing_relationship_id", message="Missing relationship_id", status_code=400)
        rel = db.query(WorldRelationship).filter(WorldRelationship.id == rel_id, WorldRelationship.novel_id == novel_id).first()
        if not rel:
            raise _ApplyDomainError(code="copilot_target_stale", message="Relationship no longer exists", status_code=409)
        validated = WorldRelationshipUpdate.model_validate(data)
        world_crud.stage_update_relationship(novel_id, rel_id, validated.model_dump(exclude_unset=True), db)
        return {"relationship_id": rel_id}

    if action_type == "create_system":
        validated = WorldSystemCreate.model_validate(data)
        sys_row = world_crud.stage_create_system(
            novel_id,
            {
                **validated.model_dump(),
                "origin": "manual",
                "status": "confirmed",
            },
            db,
        )
        return {"system_id": sys_row.id}

    if action_type == "update_system":
        sys_id = action.get("system_id")
        if not sys_id:
            raise _ApplyDomainError(code="missing_system_id", message="Missing system_id", status_code=400)
        system = db.query(WorldSystem).filter(WorldSystem.id == sys_id, WorldSystem.novel_id == novel_id).first()
        if not system:
            raise _ApplyDomainError(code="copilot_target_stale", message="System no longer exists", status_code=409)
        validated = WorldSystemUpdate.model_validate(data)
        world_crud.stage_update_system(novel_id, sys_id, validated.model_dump(exclude_unset=True), db)
        return {"system_id": sys_id}

    raise _ApplyDomainError(code="unknown_apply_type", message=f"Unknown apply type: {action_type}", status_code=400)


def _execute_attribute_action(db: Session, novel_id: int, attr_action: dict[str, Any]) -> None:
    """Execute a single attribute create/update sub-action."""
    from app.core.world import crud as world_crud

    action_type = attr_action.get("type")
    entity_id = attr_action.get("entity_id")
    data = attr_action.get("data", {})

    if action_type == "create_attribute" and entity_id:
        validated = WorldAttributeCreate.model_validate(data)
        world_crud.stage_create_attribute(novel_id, entity_id, validated.model_dump(), db)
    elif action_type == "update_attribute" and entity_id:
        attr_id = attr_action.get("attribute_id")
        if attr_id:
            validated = WorldAttributeUpdate.model_validate(data)
            world_crud.stage_update_attribute(
                novel_id,
                entity_id,
                attr_id,
                validated.model_dump(exclude_unset=True),
                db,
            )
