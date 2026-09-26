from fastapi.testclient import TestClient

from potpatrol.api import create_app


def test_potpatrol_environment_and_api_brand(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'potpatrol.db').as_posix()}"
    monkeypatch.setenv("POTPATROL_DATABASE_URL", url)
    monkeypatch.setenv("POTPATROL_DEVICE_TOKEN", "new-token")
    monkeypatch.delenv("ROADWATCH_DATABASE_URL", raising=False)
    monkeypatch.delenv("ROADWATCH_DEVICE_TOKEN", raising=False)
    app = create_app(storage_dir=tmp_path / "objects")
    assert app.title == "PotPatrol API"
    assert app.state.config.db_url == url
    assert TestClient(app).post("/v1/drives", json={}, headers={"X-Device-Token": "new-token"}).status_code == 201


def test_legacy_environment_remains_accepted(tmp_path, monkeypatch):
    monkeypatch.delenv("POTPATROL_DATABASE_URL", raising=False)
    monkeypatch.delenv("POTPATROL_DEVICE_TOKEN", raising=False)
    monkeypatch.setenv("ROADWATCH_DEVICE_TOKEN", "legacy-token")
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'old.db').as_posix()}", storage_dir=tmp_path / "objects")
    assert TestClient(app).post("/v1/drives", json={}, headers={"X-Device-Token": "legacy-token"}).status_code == 201
