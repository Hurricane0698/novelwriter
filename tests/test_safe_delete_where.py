from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.novels import _safe_delete_where


def _make_db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine)

    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER NOT NULL)"))

    return SessionLocal()


def test_safe_delete_where_rejects_unsafe_table_name() -> None:
    db = _make_db()
    try:
        with pytest.raises(ValueError):
            _safe_delete_where(
                db,
                table="t; DROP TABLE t;--",
                where_sql="v = :v",
                params={"v": 1},
            )
    finally:
        db.close()


def test_safe_delete_where_missing_table_does_not_poison_transaction() -> None:
    db = _make_db()
    try:
        db.execute(sa.text("INSERT INTO t (v) VALUES (1)"))

        # narrative_events does not exist in this in-memory DB; this should be ignored.
        _safe_delete_where(
            db,
            table="narrative_events",
            where_sql="novel_id = :novel_id",
            params={"novel_id": 1},
            allow_missing_column=True,
        )

        db.commit()
        count = db.execute(sa.text("SELECT COUNT(*) FROM t")).scalar_one()
        assert count == 1
    finally:
        db.close()


def test_safe_delete_where_missing_column_is_ignored_when_allowed() -> None:
    db = _make_db()
    try:
        # Create a table without the expected column.
        db.execute(sa.text("CREATE TABLE narrative_facts (id INTEGER PRIMARY KEY)"))

        _safe_delete_where(
            db,
            table="narrative_facts",
            where_sql="novel_id = :novel_id",
            params={"novel_id": 1},
            allow_missing_column=True,
        )
        db.commit()
    finally:
        db.close()

