import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.novel_support import delete_legacy_novel_rows


def test_partial_legacy_schema_ignores_unrelated_rows():
    engine = sa.create_engine("sqlite://")
    with Session(engine) as db:
        db.execute(sa.text("CREATE TABLE narrative_facts (id INTEGER PRIMARY KEY)"))
        db.execute(sa.text("INSERT INTO narrative_facts VALUES (9)"))
        db.execute(sa.text("CREATE TABLE character_arcs (id INTEGER PRIMARY KEY, novel_id INTEGER)"))
        db.execute(sa.text("INSERT INTO character_arcs VALUES (1, 1), (2, 2)"))
        delete_legacy_novel_rows(db, 1)
        assert db.scalars(sa.text("SELECT id FROM narrative_facts")).all() == [9]
        assert db.scalars(sa.text("SELECT id FROM character_arcs")).all() == [2]
