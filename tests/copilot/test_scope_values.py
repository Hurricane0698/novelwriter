"""Scope values must survive commits and closure of their loading session."""

from dataclasses import FrozenInstanceError

import pytest
from sqlalchemy import inspect


def test_scope_is_independent_of_orm_expiration(
    db,
    novel,
    entities,
    attributes,
    relationships,
    systems,
):
    from app.core.copilot.prompting import build_auto_preload
    from app.core.copilot.scope import load_scope_snapshot

    snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
    before = build_auto_preload(snapshot, "zh")
    # Commit expires all attached rows, including JSON fields. The value snapshot
    # must not issue lazy reads, or need a live session, after this boundary.
    db.commit()
    db.close()
    assert build_auto_preload(snapshot, "zh") == before
    rows = [
        snapshot.novel,
        *snapshot.entities,
        *snapshot.relationships,
        *snapshot.systems,
    ]
    rows.extend(
        attr for attrs in snapshot.attributes_by_entity.values() for attr in attrs
    )
    assert all(inspect(row, raiseerr=False) is None for row in rows)
    with pytest.raises(FrozenInstanceError):
        snapshot.entities[0].name = "changed"


def test_scope_json_values_do_not_alias_live_rows(db, novel, entities, systems):
    from app.core.copilot.scope import load_scope_snapshot

    snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
    before_aliases = list(snapshot.entities_by_id[entities[0].id].aliases)
    before_constraints = list(snapshot.systems[0].constraints)
    entities[0].aliases.append("后来添加")
    systems[0].constraints.append("后来限制")
    assert list(snapshot.entities_by_id[entities[0].id].aliases) == before_aliases
    assert list(snapshot.systems[0].constraints) == before_constraints
