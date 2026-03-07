from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import _mount_spa_static_files


def _build_static_dir(tmp_path):
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>spa-entry</body></html>", encoding="utf-8")
    (static_dir / "favicon.ico").write_bytes(b"ico-bytes")
    (assets_dir / "app.js").write_text("console.log('spa');", encoding="utf-8")
    return static_dir


def test_spa_fallback_serves_index_for_client_routes(tmp_path):
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    _mount_spa_static_files(app, static_dir=_build_static_dir(tmp_path))

    with TestClient(app) as client:
        root_response = client.get("/")
        nested_response = client.get("/novels/42/chapters")
        api_response = client.get("/api/health")

    assert root_response.status_code == 200
    assert nested_response.status_code == 200
    assert root_response.text == nested_response.text
    assert "spa-entry" in root_response.text
    assert api_response.status_code == 200
    assert api_response.json() == {"status": "ok"}


def test_spa_fallback_serves_existing_static_files(tmp_path):
    app = FastAPI()
    _mount_spa_static_files(app, static_dir=_build_static_dir(tmp_path))

    with TestClient(app) as client:
        favicon_response = client.get("/favicon.ico")
        asset_response = client.get("/assets/app.js")

    assert favicon_response.status_code == 200
    assert favicon_response.content == b"ico-bytes"
    assert asset_response.status_code == 200
    assert asset_response.text == "console.log('spa');"


def test_spa_fallback_rejects_path_traversal(tmp_path):
    static_dir = _build_static_dir(tmp_path)
    (tmp_path / "secret.txt").write_text("outside-static-root", encoding="utf-8")

    app = FastAPI()
    _mount_spa_static_files(app, static_dir=static_dir)

    with TestClient(app) as client:
        response = client.get("/%2E%2E/secret.txt")

    assert response.status_code == 200
    assert "spa-entry" in response.text
    assert "outside-static-root" not in response.text
