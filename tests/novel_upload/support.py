from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.models import User

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def make_app(db, router) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return app


def make_novels_app(db, novels_api, user=None) -> FastAPI:
    app = make_app(db, novels_api.router)
    if user is not None:
        from app.core.auth import get_current_user_or_default

        app.dependency_overrides[get_current_user_or_default] = lambda: user
    return app


def run_ingest_and_index_jobs(*, max_rounds: int = 5) -> None:
    from app.core.ingest import (
        enqueue_next_deferred_window_index_build,
        run_next_novel_ingest_job,
    )
    from app.core.indexing import run_next_window_index_rebuild_job

    for _ in range(max_rounds):
        did_work = False
        did_work = run_next_novel_ingest_job(session_factory=TestingSessionLocal) or did_work
        if not did_work:
            did_work = enqueue_next_deferred_window_index_build(
                session_factory=TestingSessionLocal,
            ) or did_work
        did_work = run_next_window_index_rebuild_job(session_factory=TestingSessionLocal) or did_work
        if not did_work:
            return

    raise AssertionError("background ingest/index worker did not go idle in time")


def patch_upload_dir(monkeypatch, tmp_path) -> Path:
    from app.api import novel_support

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(novel_support, "UPLOAD_DIR", upload_dir)
    return upload_dir


def create_user(db, *, user_id: int = 1) -> User:
    user = User(id=user_id, username=f"u{user_id}", hashed_password="x", role="admin", is_active=True)
    db.add(user)
    db.commit()
    return user


def novel_txt_bytes() -> bytes:
    text = "\n".join(
        [
            "第一章 开端",
            "这里是第一章内容。",
            "",
            "第二章 继续",
            "这里是第二章内容。",
            "",
        ]
    )
    return text.encode("utf-8")


def english_novel_txt_bytes() -> bytes:
    text = "\n".join(
        [
            "Chapter 1 Beginning",
            "Alice walked into the city.",
            "",
            "Chapter 2 Return",
            "Bob returned home.",
            "",
        ]
    )
    return text.encode("utf-8")


def japanese_novel_txt_bytes() -> bytes:
    text = "\n".join(
        [
            "プロローグ",
            "勇者は城へ向かった。",
            "",
            "第1話 出会い",
            "アリスは町で彼を待っていた。",
            "",
        ]
    )
    return text.encode("utf-8")


def korean_novel_txt_bytes() -> bytes:
    text = "\n".join(
        [
            "프롤로그",
            "민수는 집으로 돌아갔다.",
            "",
            "제1장 만남",
            "지현은 역 앞에서 기다리고 있었다.",
            "",
        ]
    )
    return text.encode("utf-8")
