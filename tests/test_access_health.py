from fastapi.testclient import TestClient


def _build_static_dir(tmp_path):
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>spa-entry</body></html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('spa');", encoding="utf-8")
    return static_dir


def test_access_health_report_marks_missing_critical_checks_as_degraded(tmp_path, monkeypatch):
    import app.config as config_mod
    import app.main as main_mod
    from app.api import novel_support as novels_api
    from app.config import Settings

    static_dir = _build_static_dir(tmp_path)
    upload_dir = tmp_path / "uploads-missing"

    config_mod._settings_instance = Settings(
        deploy_mode="hosted",
        hosted_invite_codes=[],
        hosted_llm_base_url="http://localhost:4000/v1",
        hosted_llm_api_key="test-key",
        hosted_llm_model="test-model",
        _env_file=None,
    )
    monkeypatch.setattr(main_mod, "_probe_database_connection", lambda: True)
    monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

    report = main_mod._build_access_health_report(static_dir=static_dir)

    assert report["status"] == "degraded"
    assert set(report["critical_failures"]) == {"auth", "upload"}
    assert report["checks"]["static_delivery"]["ready"] is True
    assert report["checks"]["generation"]["ready"] is True


def test_access_health_endpoint_reports_hosted_access_contract(tmp_path, monkeypatch):
    import app.config as config_mod
    import app.main as main_mod
    from app.api import novel_support as novels_api
    from app.config import reload_settings
    from app.main import app
    from app.version import APP_VERSION

    static_dir = _build_static_dir(tmp_path)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    monkeypatch.setenv("DEPLOY_MODE", "hosted")
    monkeypatch.setenv("HOSTED_INVITE_CODES", '[{"code":"invite-123","channel":"longkong","invite_batch":"batch-a"}]')
    monkeypatch.setenv("HOSTED_LLM_BASE_URL", "http://localhost:4000/v1")
    monkeypatch.setenv("HOSTED_LLM_API_KEY", "test-key")
    monkeypatch.setenv("HOSTED_LLM_MODEL", "test-model")
    monkeypatch.setenv("HOSTED_GITHUB_LOGIN_ENABLED", "false")
    monkeypatch.setenv("ENABLE_EVENT_TRACKING", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-access-health-32b")
    config_mod._settings_instance = None
    reload_settings()
    monkeypatch.setattr(main_mod, "_probe_database_connection", lambda: True)
    monkeypatch.setattr(main_mod, "_static_dir", static_dir)
    monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

    with TestClient(app) as client:
        response = client.get("/api/health/access")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["version"] == APP_VERSION
    assert payload["checks"]["auth"]["invite_configured"] is True
    assert payload["checks"]["auth"]["invite_code_count"] == 1
    assert payload["checks"]["auth"]["github_login_enabled"] is False
    assert payload["checks"]["generation"]["stream_headers"]["X-Accel-Buffering"] == "no"
    assert payload["checks"]["monitoring"]["ready"] is False


def test_health_endpoints_report_current_app_version(monkeypatch):
    import app.main as main_mod
    from app.main import app
    from app.version import APP_VERSION

    monkeypatch.setattr(main_mod, "_probe_database_connection", lambda: True)

    with TestClient(app) as client:
        api_response = client.get("/api")
        health_response = client.get("/api/health")

    assert api_response.status_code == 200
    assert api_response.json()["version"] == APP_VERSION
    assert health_response.status_code == 200
    assert health_response.json()["version"] == APP_VERSION
