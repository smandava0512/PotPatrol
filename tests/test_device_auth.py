from pathlib import Path

from fastapi.testclient import TestClient

from potpatrol.api import create_app
from potpatrol.worker import process_once

VIDEO = (Path(__file__).parent.parent / "fixtures" / "sample-drive.mp4").read_bytes()


def test_distinct_device_tokens_isolate_drives(tmp_path, monkeypatch):
    monkeypatch.setenv("POTPATROL_DEVICE_TOKENS", "phone-one,phone-two")
    monkeypatch.delenv("POTPATROL_DEVICE_TOKEN", raising=False)
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'devices.db').as_posix()}", storage_dir=tmp_path / "media")
    client = TestClient(app)
    one = {"X-Device-Token": "phone-one"}
    two = {"X-Device-Token": "phone-two"}
    first = client.post("/v1/drives", headers=one).json()["drive_id"]
    second = client.post("/v1/drives", headers=two).json()["drive_id"]
    assert client.get(f"/v1/drives/{first}", headers=two).status_code == 404
    assert client.post(f"/v1/drives/{first}/upload-init", headers=two).status_code == 404
    assert client.get(f"/v1/drives/{second}", headers=one).status_code == 404
    assert client.get(f"/v1/drives/{first}", headers=one).status_code == 200


def test_revoked_device_token_cannot_access_previous_drives(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'devices.db').as_posix()}"
    storage = tmp_path / "media"
    monkeypatch.setenv("POTPATROL_DEVICE_TOKENS", "phone-one,phone-two")
    monkeypatch.delenv("POTPATROL_DEVICE_TOKEN", raising=False)
    first_app = create_app(db_url=url, storage_dir=storage)
    first = TestClient(first_app).post("/v1/drives", headers={"X-Device-Token": "phone-one"}).json()["drive_id"]
    second = TestClient(first_app).post("/v1/drives", headers={"X-Device-Token": "phone-two"}).json()["drive_id"]
    monkeypatch.setenv("POTPATROL_DEVICE_TOKENS", "phone-two")
    restarted = TestClient(create_app(db_url=url, storage_dir=storage))
    assert restarted.get(f"/v1/drives/{first}", headers={"X-Device-Token": "phone-one"}).status_code == 401
    assert restarted.get(f"/v1/drives/{second}", headers={"X-Device-Token": "phone-two"}).status_code == 200
    assert restarted.get(f"/v1/drives/{first}", headers={"X-Device-Token": "phone-two"}).status_code == 404


def test_other_device_cannot_fetch_evidence_or_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("POTPATROL_DEVICE_TOKENS", "phone-one,phone-two")
    monkeypatch.delenv("POTPATROL_DEVICE_TOKEN", raising=False)
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'evidence.db').as_posix()}",
                     storage_dir=tmp_path / "media", analyzer="potpatrol.fixture_worker:analyze")
    client = TestClient(app)
    one, two = {"X-Device-Token": "phone-one"}, {"X-Device-Token": "phone-two"}
    drive = client.post("/v1/drives", headers=one).json()["drive_id"]
    url = client.post(f"/v1/drives/{drive}/upload-init", headers=one).json()["upload_url"]
    assert client.put(url, headers={**one, "Content-Type": "video/mp4"}, content=VIDEO).status_code == 204
    assert client.post(f"/v1/drives/{drive}/complete", headers=one, json={}).status_code == 200
    assert process_once(app.state.config) is True
    hazard = client.get(f"/v1/drives/{drive}", headers=one).json()["hazards"][0]
    assert client.get(hazard["evidence_url"], headers=two).status_code == 404
    assert client.post(f"/v1/hazards/{hazard['hazard_id']}/report-draft", headers=two, json={}).status_code == 404
    assert client.get(hazard["evidence_url"], headers=one).status_code == 200
