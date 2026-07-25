from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.config import reload_settings
from app.core.events import ensure_project_start_event, record_event
from app.core.seed_demo import is_seeded_demo_novel
from app.database import get_db
from app.main import app

DEFAULT_PASSWORD = 'password123!'


@pytest.fixture()
def hosted_analytics_client(tmp_path):
    db_path = tmp_path / 'analytics.db'

    orig_env = {}
    env_overrides = {
        'DEPLOY_MODE': 'hosted',
        'ENABLE_EVENT_TRACKING': 'true',
        'HOSTED_INVITE_CODES': (
            '[{"code":"TEST-CODE-123","channel":"longkong","invite_batch":"batch-a"},'
            '{"code":"TEST-CODE-456","channel":"wechat","invite_batch":"batch-b"}]'
        ),
        'JWT_SECRET_KEY': 'test-secret-key-for-hosted-mode-32b',
        'INITIAL_QUOTA': '5',
        'FEEDBACK_BONUS_QUOTA': '20',
    }
    for key, val in env_overrides.items():
        orig_env[key] = os.environ.get(key)
        os.environ[key] = val
    reload_settings()

    saved_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.clear()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base

    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)
    yield client

    for key, orig_val in orig_env.items():
        if orig_val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig_val

    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved_overrides)
    reload_settings()


def _db_session():
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    return db


def test_public_analytics_endpoint_records_anonymous_pre_signup_event(hosted_analytics_client):
    response = hosted_analytics_client.post(
        '/api/auth/events',
        json={
            'event': 'invite_gate_view',
            'anonymous_id': 'anon-pre-signup',
            'meta': {
                'channel': 'longkong',
                'invite_batch': 'batch-a',
                'entry_path': '/',
            },
        },
    )
    assert response.status_code == 202
    assert response.json() == {'ok': True}

    from app.models import UserEvent

    db = _db_session()
    try:
        rows = db.query(UserEvent).all()
        assert len(rows) == 1
        assert rows[0].user_id is None
        assert rows[0].event == 'invite_gate_view'
        assert rows[0].meta['anonymous_id'] == 'anon-pre-signup'
        assert rows[0].meta['channel'] == 'longkong'
        assert rows[0].meta['invite_batch'] == 'batch-a'
    finally:
        db.close()


def test_public_project_event_requires_novel_id_for_authenticated_user(hosted_analytics_client):
    invite_response = hosted_analytics_client.post(
        '/api/auth/invite',
        json={
            'invite_code': 'TEST-CODE-123',
            'nickname': '缺少项目用户',
            'password': DEFAULT_PASSWORD,
        },
    )
    assert invite_response.status_code == 201

    response = hosted_analytics_client.post(
        '/api/auth/events',
        json={
            'event': 'world_model_view',
            'meta': {'surface': 'atlas', 'tab': 'systems'},
        },
    )
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'analytics_novel_id_required'


def test_invite_signup_uses_personal_code_metadata_for_signup_attribution(hosted_analytics_client):
    invite_response = hosted_analytics_client.post(
        '/api/auth/invite',
        json={
            'invite_code': 'TEST-CODE-456',
            'nickname': '码元数据用户',
            'password': DEFAULT_PASSWORD,
        },
    )
    assert invite_response.status_code == 201

    from app.models import User, UserEvent

    db = _db_session()
    try:
        user = db.query(User).filter(User.nickname == '码元数据用户').one()
        signup_event = (
            db.query(UserEvent)
            .filter(UserEvent.user_id == user.id, UserEvent.event == 'signup')
            .order_by(UserEvent.id.asc())
            .first()
        )
        assert signup_event is not None
        assert signup_event.meta['channel'] == 'wechat'
        assert signup_event.meta['invite_batch'] == 'batch-b'
    finally:
        db.close()


def test_public_pre_signup_event_forbids_novel_id(hosted_analytics_client):
    response = hosted_analytics_client.post(
        '/api/auth/events',
        json={
            'event': 'invite_gate_view',
            'anonymous_id': 'anon-pre-signup',
            'novel_id': 123,
            'meta': {'channel': 'longkong'},
        },
    )
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'analytics_novel_id_forbidden'


def test_public_project_event_rejects_other_users_novel(hosted_analytics_client):
    first_invite = hosted_analytics_client.post(
        '/api/auth/invite',
        json={
            'invite_code': 'TEST-CODE-123',
            'nickname': '项目主人',
            'password': DEFAULT_PASSWORD,
        },
    )
    assert first_invite.status_code == 201

    from app.models import Novel, User, UserEvent

    db = _db_session()
    try:
        first_user = db.query(User).filter(User.nickname == '项目主人').one()
        first_demo_novel = next(
            novel for novel in db.query(Novel).filter(Novel.owner_id == first_user.id).all() if is_seeded_demo_novel(novel)
        )
        first_demo_novel_id = first_demo_novel.id
    finally:
        db.close()

    second_invite = hosted_analytics_client.post(
        '/api/auth/invite',
        json={
            'invite_code': 'TEST-CODE-456',
            'nickname': '外部用户',
            'password': DEFAULT_PASSWORD,
        },
    )
    assert second_invite.status_code == 201

    response = hosted_analytics_client.post(
        '/api/auth/events',
        json={
            'event': 'copilot_open',
            'novel_id': first_demo_novel_id,
            'meta': {'surface': 'studio', 'mode': 'whole_book', 'scope': 'whole_book'},
        },
    )
    assert response.status_code == 404
    assert response.json()['detail']['code'] == 'analytics_novel_not_found'

    db = _db_session()
    try:
        assert (
            db.query(UserEvent)
            .filter(UserEvent.event == 'copilot_open', UserEvent.novel_id == first_demo_novel_id)
            .count()
        ) == 0
    finally:
        db.close()


def test_admin_funnel_ignores_untrusted_public_project_events(hosted_analytics_client):
    invite_response = hosted_analytics_client.post(
        '/api/auth/invite',
        json={
            'invite_code': 'TEST-CODE-123',
            'nickname': '报表管理员',
            'password': DEFAULT_PASSWORD,
        },
    )
    assert invite_response.status_code == 201

    from app.models import User

    db = _db_session()
    try:
        user = db.query(User).filter(User.nickname == '报表管理员').one()
        user.role = 'admin'
        db.commit()

        record_event(db, user.id, 'world_model_view', novel_id=999999, meta={'surface': 'atlas', 'tab': 'systems'})
        record_event(
            db,
            user.id,
            'copilot_open',
            novel_id=999999,
            meta={'surface': 'studio', 'mode': 'whole_book', 'scope': 'whole_book'},
        )
    finally:
        db.close()

    report_response = hosted_analytics_client.get('/api/auth/admin/funnel')
    assert report_response.status_code == 200
    report = report_response.json()

    assert report['funnel_summary'].get('world_model_view', {}).get('total', 0) == 0
    assert report['funnel_summary'].get('copilot_open', {}).get('total', 0) == 0
    assert report['derived_metrics']['copilot_discovered']['projects'] == 0
    assert report['project_funnel_rows'] == []
    assert all(item['novel_id'] != 999999 for item in report['recent_events'])


def test_admin_funnel_derives_first_value_and_segments_demo_projects(hosted_analytics_client):
    invite_response = hosted_analytics_client.post(
        '/api/auth/invite',
        json={
            'invite_code': 'TEST-CODE-123',
            'nickname': '分析用户',
            'password': DEFAULT_PASSWORD,
            'anonymous_id': 'anon-joined',
            'attribution': {
                'channel': 'longkong',
                'invite_batch': 'batch-a',
                'entry_path': '/',
            },
        },
    )
    assert invite_response.status_code == 201

    from app.models import Novel, User, UserEvent

    db = _db_session()
    try:
        user = db.query(User).filter(User.nickname == '分析用户').one()
        user.role = 'admin'
        db.commit()

        demo_novel = next(novel for novel in db.query(Novel).filter(Novel.owner_id == user.id).all() if is_seeded_demo_novel(novel))
        demo_novel_id = demo_novel.id
    finally:
        db.close()

    # Opening the seeded demo should lock the project start mode to demo.
    get_novel_response = hosted_analytics_client.get(f'/api/novels/{demo_novel_id}')
    assert get_novel_response.status_code == 200

    # Authenticated depth/discovery signals through the public endpoint.
    assert hosted_analytics_client.post(
        '/api/auth/events',
        json={'event': 'world_model_view', 'novel_id': demo_novel_id, 'meta': {'surface': 'atlas', 'tab': 'systems'}},
    ).status_code == 202
    assert hosted_analytics_client.post(
        '/api/auth/events',
        json={'event': 'copilot_open', 'novel_id': demo_novel_id, 'meta': {'surface': 'studio', 'mode': 'whole_book', 'scope': 'whole_book'}},
    ).status_code == 202

    db = _db_session()
    try:
        user = db.query(User).filter(User.nickname == '分析用户').one()
        ensure_project_start_event(db, user_id=user.id, novel_id=demo_novel_id, start_mode='demo')
        record_event(db, user.id, 'generation', novel_id=demo_novel_id, meta={'variants': 1, 'delivery_mode': 'sync'})
        record_event(db, user.id, 'chapter_save', novel_id=demo_novel_id, meta={'chapter': 28})
        record_event(db, user.id, 'copilot_apply', novel_id=demo_novel_id, meta={'success_count': 1})

        signup_event = (
            db.query(UserEvent)
            .filter(UserEvent.user_id == user.id, UserEvent.event == 'signup')
            .order_by(UserEvent.id.asc())
            .first()
        )
        assert signup_event is not None
        assert signup_event.meta['channel'] == 'longkong'
        assert signup_event.meta['invite_batch'] == 'batch-a'
        assert signup_event.meta['anonymous_id'] == 'anon-joined'
    finally:
        db.close()

    report_response = hosted_analytics_client.get('/api/auth/admin/funnel')
    assert report_response.status_code == 200
    report = report_response.json()

    assert report['derived_metrics']['first_value_completed']['projects'] == 1
    assert report['derived_metrics']['copilot_discovered']['projects'] == 1
    assert report['derived_metrics']['copilot_applied']['projects'] == 1
    assert report['funnel_summary']['signup']['unique_users'] == 1

    segment = next(
        item for item in report['segment_summary']
        if item['channel'] == 'longkong' and item['invite_batch'] == 'batch-a' and item['project_start_mode'] == 'demo'
    )
    assert segment['projects'] == 1
    assert segment['generated_projects'] == 1
    assert segment['first_value_projects'] == 1
    assert segment['world_model_view_projects'] == 1
    assert segment['copilot_open_projects'] == 1
    assert segment['copilot_apply_projects'] == 1

    project_row = next(item for item in report['project_funnel_rows'] if item['novel_id'] == demo_novel_id)
    assert project_row['project_start_mode'] == 'demo'
    assert project_row['first_value_completed'] is True
    assert project_row['world_model_viewed'] is True
    assert project_row['copilot_opened'] is True
    assert project_row['copilot_applied'] is True


def test_worldpack_import_records_setting_import_project_start_and_worldpack_event(hosted_analytics_client):
    invite_response = hosted_analytics_client.post(
        '/api/auth/invite',
        json={
            'invite_code': 'TEST-CODE-123',
            'nickname': '导入包用户',
            'password': DEFAULT_PASSWORD,
        },
    )
    assert invite_response.status_code == 201

    from app.models import Novel, User, UserEvent

    db = _db_session()
    try:
        user = db.query(User).filter(User.nickname == '导入包用户').one()
        user_id = user.id
        novel = Novel(
            title='空白设定项目',
            author='Tester',
            file_path='/tmp/worldpack-import.txt',
            total_chapters=0,
            owner_id=user.id,
        )
        db.add(novel)
        db.commit()
        db.refresh(novel)
        novel_id = novel.id
    finally:
        db.close()

    payload = {
        'schema_version': 'worldpack.v1',
        'pack_id': 'pack-demo',
        'pack_name': 'Demo Pack',
        'language': 'zh',
        'license': 'CC-BY',
        'source': {'wiki_base_url': 'https://example.com/wiki'},
        'generated_at': '2026-02-22T00:00:00+00:00',
        'entities': [],
        'relationships': [],
        'systems': [],
    }
    response = hosted_analytics_client.post(f'/api/novels/{novel_id}/world/worldpack/import', json=payload)
    assert response.status_code == 200

    db = _db_session()
    try:
        rows = (
            db.query(UserEvent)
            .filter(UserEvent.novel_id == novel_id, UserEvent.user_id == user_id)
            .order_by(UserEvent.id.asc())
            .all()
        )
        project_start = next(row for row in rows if row.event == 'project_start')
        assert project_start.meta['start_mode'] == 'setting_import'
        assert project_start.meta['entry_action'] == 'worldpack_import'

        worldpack_event = next(row for row in rows if row.event == 'worldpack_import')
        assert worldpack_event.meta['pack_id'] == 'pack-demo'
        assert worldpack_event.meta['warnings_count'] == 0
        assert worldpack_event.meta['entities_created'] == 0
        assert worldpack_event.meta['relationships_created'] == 0
        assert worldpack_event.meta['systems_created'] == 0
    finally:
        db.close()


def test_admin_funnel_reports_world_build_attempts_demo_completion_and_upload_after_demo(hosted_analytics_client):
    invite_response = hosted_analytics_client.post(
        '/api/auth/invite',
        json={
            'invite_code': 'TEST-CODE-123',
            'nickname': '漏斗补环用户',
            'password': DEFAULT_PASSWORD,
            'anonymous_id': 'anon-funnel-closure',
            'attribution': {
                'channel': 'longkong',
                'invite_batch': 'batch-a',
                'entry_path': '/',
            },
        },
    )
    assert invite_response.status_code == 201

    from app.models import Novel, User, UserEvent

    db = _db_session()
    try:
        user = db.query(User).filter(User.nickname == '漏斗补环用户').one()
        user.role = 'admin'
        db.commit()

        demo_novel = next(novel for novel in db.query(Novel).filter(Novel.owner_id == user.id).all() if is_seeded_demo_novel(novel))
        demo_novel_id = demo_novel.id
    finally:
        db.close()

    assert hosted_analytics_client.get(f'/api/novels/{demo_novel_id}').status_code == 200

    project_events = [
        ('world_onboarding_view', {'surface': 'studio'}),
        ('world_generate_open', {'source_surface': 'world_onboarding'}),
        ('world_generate_submit', {'source_surface': 'world_onboarding', 'text_length': 128}),
        ('world_generate_failed', {'source_surface': 'world_onboarding', 'status': 503, 'error_code': 'world_generate_llm_unavailable'}),
        ('bootstrap_trigger', {'source_surface': 'world_onboarding', 'mode': 'initial'}),
        ('bootstrap_failed', {'source_surface': 'world_onboarding', 'status': 400, 'error_code': 'bootstrap_no_text'}),
        ('demo_guide_view', {'source': 'auto', 'status': 'in_progress', 'progress_count': 1}),
        ('demo_guide_step_complete', {'step': 'chapter', 'progress_count': 1}),
        ('demo_guide_step_complete', {'step': 'atlas', 'progress_count': 2}),
        ('demo_guide_step_complete', {'step': 'write', 'progress_count': 3}),
        ('demo_guide_step_complete', {'step': 'copilot', 'progress_count': 4}),
        ('demo_guide_completed', {'progress_count': 4}),
    ]
    for event_name, meta in project_events:
        response = hosted_analytics_client.post(
            '/api/auth/events',
            json={'event': event_name, 'novel_id': demo_novel_id, 'meta': meta},
        )
        assert response.status_code == 202, event_name

    upload_click_response = hosted_analytics_client.post(
        '/api/auth/events',
        json={'event': 'upload_cta_click', 'meta': {'source_surface': 'library_demo_card'}},
    )
    assert upload_click_response.status_code == 202

    db = _db_session()
    try:
        user = db.query(User).filter(User.nickname == '漏斗补环用户').one()
        uploaded_novel = Novel(
            title='我的正文项目',
            author='Tester',
            file_path='/tmp/uploaded-after-demo.txt',
            total_chapters=12,
            owner_id=user.id,
        )
        db.add(uploaded_novel)
        db.commit()
        db.refresh(uploaded_novel)

        record_event(
            db,
            user.id,
            'world_generate',
            novel_id=demo_novel_id,
            meta={
                'entities_created': 2,
                'relationships_created': 1,
                'systems_created': 1,
                'warnings_count': 0,
            },
        )
        record_event(
            db,
            user.id,
            'worldpack_import',
            novel_id=demo_novel_id,
            meta={
                'pack_id': 'pack-demo',
                'warnings_count': 0,
                'entities_created': 0,
                'relationships_created': 0,
                'systems_created': 0,
            },
        )
        ensure_project_start_event(
            db,
            user_id=user.id,
            novel_id=uploaded_novel.id,
            start_mode='chapter_import',
            meta={
                'entry_action': 'novel_upload',
                'source_surface': 'library_demo_card',
            },
        )
        record_event(
            db,
            user.id,
            'novel_upload',
            novel_id=uploaded_novel.id,
            meta={
                'chapters': 12,
                'bytes_uploaded': 4096,
                'language': 'zh',
                'source_surface': 'library_demo_card',
                'upload_duration_ms': 321.5,
            },
        )

        completion_event = (
            db.query(UserEvent)
            .filter(UserEvent.user_id == user.id, UserEvent.novel_id == demo_novel_id, UserEvent.event == 'demo_guide_completed')
            .order_by(UserEvent.id.asc())
            .first()
        )
        upload_start_event = (
            db.query(UserEvent)
            .filter(UserEvent.user_id == user.id, UserEvent.novel_id == uploaded_novel.id, UserEvent.event == 'project_start')
            .order_by(UserEvent.id.asc())
            .first()
        )
        assert completion_event is not None
        assert upload_start_event is not None
        upload_start_event.created_at = completion_event.created_at
        db.commit()
        uploaded_novel_id = uploaded_novel.id
    finally:
        db.close()

    report_response = hosted_analytics_client.get('/api/auth/admin/funnel')
    assert report_response.status_code == 200
    report = report_response.json()

    assert report['funnel_summary']['world_onboarding_view']['unique_projects'] == 1
    assert report['funnel_summary']['world_generate_submit']['total'] == 1
    assert report['funnel_summary']['world_generate_failed']['total'] == 1
    assert report['funnel_summary']['bootstrap_trigger']['total'] == 1
    assert report['funnel_summary']['bootstrap_failed']['total'] == 1
    assert report['funnel_summary']['demo_guide_completed']['total'] == 1
    assert report['funnel_summary']['upload_cta_click']['unique_users'] == 1

    assert report['derived_metrics']['world_onboarding_engaged']['projects'] == 1
    assert report['derived_metrics']['demo_guide_completed']['projects'] == 1
    assert report['derived_metrics']['uploaded_own_novel_after_demo_guide']['projects'] == 1

    assert report['cross_project_user_metrics']['demo_guide_to_upload_click']['users'] == 1
    assert report['cross_project_user_metrics']['demo_guide_to_upload_click']['events'] == 1
    assert report['cross_project_user_metrics']['demo_guide_to_chapter_import']['users'] == 1
    assert report['cross_project_user_metrics']['demo_guide_to_chapter_import']['projects'] == 1

    demo_project_row = next(item for item in report['project_funnel_rows'] if item['novel_id'] == demo_novel_id)
    assert demo_project_row['world_onboarding_viewed'] is True
    assert demo_project_row['world_onboarding_engaged'] is True
    assert demo_project_row['world_generate_submit_count'] == 1
    assert demo_project_row['world_generate_failed_count'] == 1
    assert demo_project_row['bootstrap_trigger_count'] == 1
    assert demo_project_row['bootstrap_failed_count'] == 1
    assert demo_project_row['demo_guide_completed'] is True
    assert demo_project_row['demo_guide_step_chapter_count'] == 1
    assert demo_project_row['demo_guide_step_atlas_count'] == 1
    assert demo_project_row['demo_guide_step_write_count'] == 1
    assert demo_project_row['demo_guide_step_copilot_count'] == 1
    assert demo_project_row['worldpack_import_count'] == 1

    uploaded_project_row = next(item for item in report['project_funnel_rows'] if item['novel_id'] == uploaded_novel_id)
    assert uploaded_project_row['project_start_mode'] == 'chapter_import'
    assert uploaded_project_row['project_start_entry_action'] == 'novel_upload'
    assert uploaded_project_row['project_start_source_surface'] == 'library_demo_card'
    assert uploaded_project_row['upload_source_surface'] == 'library_demo_card'
