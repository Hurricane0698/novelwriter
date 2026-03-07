"""
Regression: SQLite novel ids must not be reused after deletes.

Without `AUTOINCREMENT`, SQLite may reuse the maximum deleted rowid/id:
delete id=7 -> next insert may get id=7 again.
"""

from __future__ import annotations

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Novel


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_sqlite_novel_id_is_monotonic_after_delete(db):
    # Create 7 novels -> ids 1..7
    for i in range(7):
        db.add(
            Novel(
                title=f"T{i}",
                author="",
                file_path=f"/tmp/{i}.txt",
                total_chapters=0,
            )
        )
    db.commit()

    last = db.query(Novel).order_by(Novel.id.desc()).first()
    assert last is not None
    assert last.id == 7

    db.delete(last)
    db.commit()

    n = Novel(title="new", author="", file_path="/tmp/new.txt", total_chapters=0)
    db.add(n)
    db.commit()
    db.refresh(n)

    assert n.id == 8

