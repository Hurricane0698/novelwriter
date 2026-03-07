"""Tests for the demo novel seed function."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import hash_password
from app.core.seed_demo import seed_demo_novel, DEMO_TITLE
from app.database import Base
from app.models import Novel, Chapter, WorldEntity, WorldRelationship, WorldSystem, User

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def _make_user(db, username="test_seed_user"):
    user = User(username=username, hashed_password=hash_password("x"), is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_seed_creates_novel_and_worldpack():
    db = _fresh_db()
    user = _make_user(db)
    novel_id = seed_demo_novel(db, user)

    assert novel_id is not None
    novel = db.query(Novel).filter(Novel.id == novel_id).one()
    assert novel.title == DEMO_TITLE
    assert novel.owner_id == user.id

    chapters = db.query(Chapter).filter(Chapter.novel_id == novel_id).all()
    assert len(chapters) == 27

    entities = db.query(WorldEntity).filter(WorldEntity.novel_id == novel_id).all()
    assert len(entities) >= 20

    rels = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel_id).all()
    assert len(rels) >= 15

    systems = db.query(WorldSystem).filter(WorldSystem.novel_id == novel_id).all()
    assert len(systems) == 5
    db.close()


def test_seed_is_idempotent():
    db = _fresh_db()
    user = _make_user(db)
    first_id = seed_demo_novel(db, user)
    second_id = seed_demo_novel(db, user)

    assert first_id is not None
    assert second_id is None

    count = db.query(Novel).filter(
        Novel.owner_id == user.id, Novel.title == DEMO_TITLE
    ).count()
    assert count == 1
    db.close()


def test_seed_does_not_affect_other_users():
    db = _fresh_db()
    user_a = _make_user(db, "seed_a")
    user_b = _make_user(db, "seed_b")

    id_a = seed_demo_novel(db, user_a)
    id_b = seed_demo_novel(db, user_b)

    assert id_a is not None
    assert id_b is not None
    assert id_a != id_b
    db.close()
