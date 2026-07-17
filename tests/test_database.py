from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool

from app.database import (
    _SQLITE_BUSY_TIMEOUT_MILLISECONDS,
    _set_sqlite_connection_pragmas,
    ensure_sqlite_wal_mode,
)


class _RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.closed = False

    def execute(self, statement: str) -> None:
        self.statements.append(statement)

    def close(self) -> None:
        self.closed = True


class _RecordingConnection:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _RecordingCursor:
        return self._cursor


def test_sqlite_connection_hook_only_sets_connection_scoped_pragmas():
    cursor = _RecordingCursor()

    _set_sqlite_connection_pragmas(_RecordingConnection(cursor), None)

    assert cursor.statements == [
        f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MILLISECONDS}",
        "PRAGMA synchronous=NORMAL",
    ]
    assert cursor.closed is True


def test_ensure_sqlite_wal_mode_rejects_database_that_cannot_enable_wal():
    db_engine = create_engine("sqlite:///:memory:")
    try:
        with pytest.raises(RuntimeError, match="refused required WAL"):
            ensure_sqlite_wal_mode(db_engine)
    finally:
        db_engine.dispose()


def test_sqlite_new_connection_does_not_reassert_wal_during_active_write(
    tmp_path: Path,
):
    database_path = tmp_path / "concurrent.db"
    db_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    event.listen(db_engine, "connect", _set_sqlite_connection_pragmas)

    try:
        ensure_sqlite_wal_mode(db_engine)
        with db_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )

        writer = db_engine.connect()
        try:
            writer.exec_driver_sql("BEGIN IMMEDIATE")
            writer.exec_driver_sql("INSERT INTO records (value) VALUES ('pending')")

            with db_engine.connect() as reader:
                assert (
                    reader.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
                )
                assert (
                    reader.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
                    == _SQLITE_BUSY_TIMEOUT_MILLISECONDS
                )
        finally:
            writer.rollback()
            writer.close()
    finally:
        db_engine.dispose()
