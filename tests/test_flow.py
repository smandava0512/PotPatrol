from pathlib import Path

from sqlalchemy import create_engine, inspect
from fastapi.testclient import TestClient

from potpatrol.api import create_app
from potpatrol.worker import process_once


MP4 = (Path(__file__).parent.parent / "fixtures" / "sample-drive.mp4").read_bytes()
TOKEN = {"X-Device-Token": "demo-secret"}


def test_fixture_drive_end_to_end(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'data.db').as_posix()}"
    storage = tmp_path / "storage"
    app = create_app(db_url=db_url, storage_dir=storage, token="demo-secret", analyzer="potpatrol.fixture_worker:analyze")
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/v1/drives", json={}).status_code == 401
    created = client.post("/v1/drives", headers=TOKEN, json={}).json()
    drive = created["drive_id"]
    assert created["status"] == "created"
    upload = client.post(f"/v1/drives/{drive}/upload-init", headers=TOKEN, json={}).json()
    assert upload["method"] == "PUT"
    assert client.put(upload["upload_url"], headers={**TOKEN, **upload["headers"]}, content=MP4).status_code == 204
    samples = {"samples": [
        {"offset_ms": 0, "recorded_at": "2026-09-26T12:00:00Z", "latitude": 25.7617, "longitude": -80.1918, "horizontal_accuracy_m": 5, "speed_mps": 4},
        {"offset_ms": 2000, "recorded_at": "2026-09-26T12:00:02Z", "latitude": 25.7619, "longitude": -80.1916, "horizontal_accuracy_m": 6, "speed_mps": 4},
    ]}
    assert client.post(f"/v1/drives/{drive}/locations", headers=TOKEN, json=samples).json() == {"accepted": 2}
    assert client.post(f"/v1/drives/{drive}/locations", headers=TOKEN, json=samples).json() == {"accepted": 0}
    assert client.post(f"/v1/drives/{drive}/complete", headers=TOKEN, json={}).json()["status"] == "queued"
    assert client.post(f"/v1/drives/{drive}/complete", headers=TOKEN, json={}).json()["status"] == "queued"
    assert process_once(app.state.config) is True
    assert process_once(app.state.config) is False
    result = client.get(f"/v1/drives/{drive}", headers=TOKEN).json()
    assert result["status"] == "complete" and len(result["hazards"]) == 1
    hazard = result["hazards"][0]
    assert hazard["location"]["source"] == "phone_interpolated"
    assert round(hazard["location"]["latitude"], 4) == 25.7618
    assert client.get(hazard["evidence_url"], headers=TOKEN).headers["content-type"] == "image/jpeg"
    draft = client.post(f"/v1/hazards/{hazard['hazard_id']}/report-draft", headers=TOKEN, json={}).json()
    assert draft["submission_status"] == "not_submitted"
    assert draft["destination"]["status"] == "unverified"
    assert client.post(f"/v1/hazards/{hazard['hazard_id']}/report-draft", headers=TOKEN, json={}).json() == draft
