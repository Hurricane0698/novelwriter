from fastapi.testclient import TestClient


def _build_static_dir(tmp_path):
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>spa-entry</body></html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('spa');", encoding="utf-8")
    return static_dir


def test_access_health_report_marks_missing_critical_checks_as_degraded(tmp_path, monkeypatch):
    import app.main as main_mod
    from app.api import novel_support as novels_api

    static_dir = _build_static_dir(tmp_path)
    upload_dir = tmp_path / "uploads-missing"

    monkeypatch.setattr(main_mod, "_probe_database_connection", lambda: True)
    monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

    report = main_mod._build_access_health_report(static_dir=static_dir)

    assert report["status"] == "degraded"
    assert set(report["critical_failures"]) == {"upload"}
    assert report["checks"]["static_delivery"]["ready"] is True


def test_access_health_endpoint_reports_ready_storage(tmp_path, monkeypatch):
    import app.main as main_mod
    from app.api import novel_support as novels_api
    from app.main import app
    from app.version import APP_VERSION

    static_dir = _build_static_dir(tmp_path)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    monkeypatch.setattr(main_mod, "_probe_database_connection", lambda: True)
    monkeypatch.setattr(main_mod, "_static_dir", static_dir)
    monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

    with TestClient(app) as client:
        response = client.get("/api/health/access")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["version"] == APP_VERSION
    assert payload["checks"]["upload"]["ready"] is True


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
