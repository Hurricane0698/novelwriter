from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy.exc import IntegrityError

from app.core.auth import _get_or_create_default_user


def test_get_or_create_default_user_recovers_from_unique_race():
    existing_user = SimpleNamespace(username="default")

    query = Mock()
    query.filter.return_value.first.side_effect = [None, existing_user]

    db = Mock()
    db.query.return_value = query
    db.commit.side_effect = IntegrityError("stmt", "params", Exception("orig"))

    user = _get_or_create_default_user(db)

    assert user is existing_user
    db.add.assert_called_once()
    db.rollback.assert_called_once()
