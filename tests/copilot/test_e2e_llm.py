# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Real-LLM copilot smoke tests using the Journey to the West demo.

These tests hit the actual LLM provider configured in .env.
Run with: RUN_E2E_LLM=1 scripts/uv_run.sh pytest tests/copilot/test_e2e_llm.py -v -s
Skip by leaving RUN_E2E_LLM unset or via: pytest -m "not e2e_llm"

Purpose: validate the full copilot pipeline with a real provider, while
keeping the live suite intentionally small and operator-invoked only.
"""

from functools import lru_cache
import json
import os
import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import reload_settings
from app.core.llm_config import (
    LLM_CONFIG_INCOMPLETE_CODE,
    LLM_CONFIG_MISSING_CODE,
    LlmConfigError,
    resolve_llm_config,
)
from app.database import Base
from app.models import (
    Chapter,
    CopilotRun,
    Novel,
    WorldEntity,
    WorldEntityAttribute,
    WorldRelationship,
    WorldSystem,
)

pytestmark = [pytest.mark.e2e_llm, pytest.mark.asyncio]
_RUN_E2E_LLM = (os.getenv("RUN_E2E_LLM") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_E2E_TOOL_ROUNDS = 2

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _has_llm_config() -> bool:
    try:
        resolve_llm_config(settings=reload_settings())
    except LlmConfigError as exc:
        if exc.code in {LLM_CONFIG_MISSING_CODE, LLM_CONFIG_INCOMPLETE_CODE}:
            return False
        raise
    return True


if not _RUN_E2E_LLM:
    pytest.skip(
        "Set RUN_E2E_LLM=1 to run real-provider copilot E2E tests",
        allow_module_level=True,
    )

if not _has_llm_config():
    pytest.skip("No LLM config — skipping E2E LLM tests", allow_module_level=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=_engine)
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@lru_cache(maxsize=1)
def _load_demo_chapters() -> tuple[str, ...]:
    import re

    with open("data/demo/西游记_前27回.txt", encoding="utf-8") as f:
        text = f.read()
    parts = re.split(r"(第[一二三四五六七八九十百千]+回\s)", text)
    chapters: list[str] = []
    for i in range(1, len(parts) - 1, 2):
        chapters.append(parts[i] + parts[i + 1])
    return tuple(chapters)


@lru_cache(maxsize=1)
def _load_worldpack_payload() -> dict:
    with open("data/worldpacks/journey-to-the-west.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def _fast_e2e_settings(monkeypatch):
    import app.config as config_module

    base_settings = config_module.reload_settings()
    tuned_settings = config_module.Settings.model_validate(
        {
            **base_settings.model_dump(),
            "copilot_max_tool_rounds": _E2E_TOOL_ROUNDS,
        }
    )

    monkeypatch.setattr(config_module, "_settings_instance", tuned_settings, raising=False)
    monkeypatch.setattr(config_module, "get_settings", lambda: tuned_settings)
    monkeypatch.setattr(config_module, "reload_settings", lambda: tuned_settings)
    yield


def _load_chapter_text(chapter_num: int) -> str:
    """Load a chapter from the demo text by splitting on "第X回" markers."""
    chapters = _load_demo_chapters()
    if chapter_num <= 0 or chapter_num > len(chapters):
        return chapters[0][:5000] if chapters else ""
    return chapters[chapter_num - 1][:8000]  # Cap for test speed


@pytest.fixture
def jtw_world(db):
    """Create a Journey to the West world from the demo data + worldpack."""
    novel = Novel(
        title="西游记（前二十七回）", author="吴承恩",
        file_path="/tmp/jtw.txt", total_chapters=3, language="zh",
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)

    # Load 3 chapters (chapter 1, 14 (收悟空), 27 (三打白骨精))
    for num, real_ch in [(1, 1), (2, 14), (3, 27)]:
        ch = Chapter(
            novel_id=novel.id, chapter_number=num,
            title=f"第{real_ch}回",
            content=_load_chapter_text(real_ch),
        )
        db.add(ch)
    db.commit()

    # Load worldpack
    wp = _load_worldpack_payload()

    key_to_entity: dict[str, WorldEntity] = {}

    # Seed a subset of entities (the main cast + a draft)
    keep_keys = {
        "tang-seng", "sun-wukong", "zhu-bajie", "sha-seng",
        "bai-gu-furen", "guan-yin",
        "hua-guo-shan", "jin-gu-bang",
    }
    for ent_data in wp["entities"]:
        key = ent_data["key"]
        if key not in keep_keys:
            continue
        # Make 白骨夫人 a draft (for draft_cleanup testing)
        status = "draft" if key == "bai-gu-furen" else "confirmed"
        origin = "bootstrap" if key == "bai-gu-furen" else "manual"
        # Intentionally weaken 猪八戒's description for enrichment testing
        desc = ent_data["description"]
        if key == "zhu-bajie":
            desc = ""  # empty — copilot should catch this

        e = WorldEntity(
            novel_id=novel.id, name=ent_data["name"],
            entity_type=ent_data["entity_type"],
            description=desc,
            aliases=ent_data.get("aliases", []),
            status=status, origin=origin,
        )
        db.add(e)
        db.flush()
        key_to_entity[key] = e

        # Add a few attributes
        for attr in ent_data.get("attributes", [])[:2]:
            a = WorldEntityAttribute(
                entity_id=e.id, key=attr["key"],
                surface=attr["surface"],
                visibility=attr.get("visibility", "active"),
                origin="manual",
            )
            db.add(a)
    db.commit()

    # Seed relationships (subset)
    for rel_data in wp.get("relationships", [])[:6]:
        src = key_to_entity.get(rel_data["source_key"])
        tgt = key_to_entity.get(rel_data["target_key"])
        if not src or not tgt:
            continue
        r = WorldRelationship(
            novel_id=novel.id, source_id=src.id, target_id=tgt.id,
            label=rel_data["label"],
            description=rel_data.get("description", ""),
            status="confirmed", origin="manual",
        )
        db.add(r)
    db.commit()

    # Seed one system
    sys_data = wp.get("systems", [{}])[0]
    if sys_data:
        s = WorldSystem(
            novel_id=novel.id, name=sys_data["name"],
            display_type=sys_data["display_type"],
            description=sys_data.get("description", ""),
            constraints=sys_data.get("constraints", []),
            status="confirmed", origin="manual",
        )
        db.add(s)
        db.commit()

    return {"novel": novel, "entities": key_to_entity}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _run_copilot(db, novel, mode, scope, context, prompt, locale="zh"):
    """Run a full copilot execution against the real LLM.

    The canonical resolver supplies the same typed config used by application
    requests and background workers.

    The test DB *is* the real SessionLocal for this test — we just need to
    make execute_copilot_run find its run/session/novel in our test DB.
    """
    from app.core.copilot.service import (
        create_run,
        execute_copilot_run,
        open_or_reuse_session,
    )
    import app.database as db_mod

    session, _ = open_or_reuse_session(db, novel.id, 1, mode, scope, context, locale, "")
    run = create_run(db, session, 1, prompt)

    llm_config = resolve_llm_config(settings=reload_settings())

    # Patch SessionLocal to return our test DB session (non-closeable).
    orig_sl = db_mod.SessionLocal
    _real_close = db.close

    def _test_session_factory():
        db.close = lambda: None  # prevent accidental close
        return db

    db_mod.SessionLocal = _test_session_factory
    try:
        await execute_copilot_run(run.run_id, novel.id, 1, llm_config=llm_config)
    finally:
        db.close = _real_close
        db_mod.SessionLocal = orig_sl

    db.refresh(run)
    return run


def _print_run(label: str, run: CopilotRun):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Status:      {run.status}")
    if run.error:
        print(f"  Error:       {run.error[:300]}")
    print(f"  Answer:      {(run.answer or '')[:400]}")
    print(f"  Evidence:    {len(run.evidence_json or [])} items")
    print(f"  Suggestions: {len(run.suggestions_json or [])} items")
    for i, sg in enumerate(run.suggestions_json or []):
        kind = sg.get("kind", "?")
        title = sg.get("title", "?")
        act = sg.get("preview", {}).get("actionable", False)
        target = sg.get("target", {}).get("label", "?")
        print(f"    [{i}] {kind} → {target} | {title} | actionable={act}")
        for fd in sg.get("preview", {}).get("field_deltas", []):
            before = (fd.get("before") or "∅")[:40]
            after = (fd.get("after") or "∅")[:60]
            print(f"        {fd.get('label')}: {before} → {after}")


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

async def test_current_entity_enrichment_smoke(db, jtw_world):
    """Actionable current-entity workflow against a weak field."""
    run = await _run_copilot(
        db, jtw_world["novel"],
        mode="current_entity", scope="current_entity",
        context={"entity_id": jtw_world["entities"]["zhu-bajie"].id},
        prompt="猪八戒的描述是空的，帮我补完。",
    )
    _print_run("Entity enrichment smoke: 猪八戒", run)

    assert run.status == "completed", f"Failed: {run.error}"
    assert run.answer and len(run.answer) > 20
    assert len(run.evidence_json or []) > 0

    suggestions = run.suggestions_json or []
    if suggestions:
        targets = [sg.get("target", {}).get("label", "") for sg in suggestions]
        print(f"  Suggestion targets: {targets}")


async def test_whole_book_research_smoke(db, jtw_world):
    """Inquiry-style whole-book workflow remains valid with a live provider."""
    run = await _run_copilot(
        db, jtw_world["novel"],
        mode="research", scope="whole_book",
        context=None,
        prompt="帮我盘点一下西游记世界模型的设定缺口。",
    )
    _print_run("Whole-book inquiry smoke: 西游记", run)

    assert run.status == "completed", f"Failed: {run.error}"
    assert run.answer and len(run.answer) > 30
