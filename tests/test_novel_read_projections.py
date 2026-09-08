"""Request metadata must not materialize the whole-book index."""

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Novel, User


@pytest.mark.parametrize("loader_name", ["novel_api", "api_dependency", "world_crud"])
def test_novel_access_loaders_defer_index_but_preserve_on_demand_reads(tmp_path, loader_name):
    from app.api.deps import verify_novel_access
    from app.api.novel_support import get_accessible_novel
    from app.core.world.crud import load_novel

    engine = create_engine(f"sqlite:///{tmp_path / 'projection.db'}")
    Base.metadata.create_all(engine)
    payload = b"whole-book-index" * 65536
    with Session(engine) as seed:
        novel = Novel(title="Projection", file_path="unused.txt", owner_id=1, window_index=payload)
        seed.add(novel)
        seed.commit()
        novel_id = novel.id

    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as db:
            user = User(id=1, username="owner", hashed_password="unused")
            if loader_name == "novel_api":
                novel = get_accessible_novel(db, novel_id, user)
            elif loader_name == "api_dependency":
                novel = verify_novel_access(novel_id, db, user)
            else:
                novel = load_novel(novel_id, db)

            assert novel.title == "Projection"
            assert "window_index" in inspect(novel).unloaded
            assert len(statements) == 1

            # Index consumers still receive the original bytes without changing
            # the persistence contract or clearing an incremental build base.
            assert novel.window_index == payload
            assert len(statements) == 2
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        engine.dispose()


@pytest.mark.parametrize("payload", [None, b"", b"index" * 65536], ids=["missing", "empty", "large"])
def test_metadata_reload_and_readiness_do_not_materialize_index(tmp_path, payload):
    from app.core.indexing.lifecycle import inspect_window_index_lifecycle

    engine = create_engine(f"sqlite:///{tmp_path / 'reload.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as seed:
        seed.add(Novel(id=1, title="Before", file_path="unused.txt", window_index=payload))
        seed.commit()
    with Session(engine) as db:
        novel = db.get(Novel, 1)
        assert "window_index" in inspect(novel).unloaded
        novel.title = "After"
        db.commit()
        assert novel.title == "After"
        assert "window_index" in inspect(novel).unloaded
        db.refresh(novel)
        state = inspect_window_index_lifecycle(novel, db=db)
        assert state.has_payload is bool(payload)
        assert "window_index" in inspect(novel).unloaded
        assert novel.window_index == payload
        # Pending writes also affect readiness before the next commit.
        novel.window_index = b"new payload"
        assert inspect_window_index_lifecycle(novel, db=db).has_payload is True
        novel.window_index = None
        assert inspect_window_index_lifecycle(novel, db=db).has_payload is False
    engine.dispose()
