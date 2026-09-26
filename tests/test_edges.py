from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from potpatrol.api import create_app
from potpatrol.db import Drive, Job
from potpatrol.worker import process_once, validate_manifest

VIDEO = (Path(__file__).parent.parent / "fixtures" / "sample-drive.mp4").read_bytes()
TOKEN = {"X-Device-Token": "secret"}


def setup_drive(tmp_path, analyzer="potpatrol.fixture_worker:analyze", with_locations=False):
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}", storage_dir=tmp_path / "objects", token="secret", analyzer=analyzer)
    client = TestClient(app)
    drive = client.post("/v1/drives", json={}, headers=TOKEN).json()["drive_id"]
    url = client.post(f"/v1/drives/{drive}/upload-init", json={}, headers=TOKEN).json()["upload_url"]
    if with_locations:
        client.post(f"/v1/drives/{drive}/locations", headers=TOKEN, json={"samples": [{"offset_ms": 0, "recorded_at": "2026-09-26T12:00:00Z", "latitude": 25, "longitude": -80, "horizontal_accuracy_m": 100, "speed_mps": None}]})
    return app, client, drive, url


def test_no_hazard_worker_and_missing_gps(tmp_path):
    app, client, drive, url = setup_drive(tmp_path, analyzer="potpatrol.empty_worker:analyze")
    assert client.put(url, headers={**TOKEN, "Content-Type": "video/mp4"}, content=VIDEO).status_code == 204
    assert client.post(f"/v1/drives/{drive}/complete", headers=TOKEN, json={}).status_code == 200
    assert process_once(app.state.config)
    result = client.get(f"/v1/drives/{drive}", headers=TOKEN).json()
    assert result["status"] == "complete" and result["hazards"] == []


def test_bad_upload_rejected_and_no_duplicate_job(tmp_path):
    app, client, drive, url = setup_drive(tmp_path)
    assert client.put(url, headers={**TOKEN, "Content-Type": "text/plain"}, content=VIDEO).status_code == 415
    assert client.put(url, headers={**TOKEN, "Content-Type": "video/mp4"}, content=b"bad").status_code == 422
    assert client.post(f"/v1/drives/{drive}/complete", headers=TOKEN, json={}).status_code == 409
    assert client.put(url, headers={**TOKEN, "Content-Type": "video/mp4"}, content=VIDEO).status_code == 204
    samples = {"samples": [{"offset_ms": 0, "recorded_at": "2026-09-26T12:00:00Z", "latitude": 25, "longitude": -80, "horizontal_accuracy_m": 100, "speed_mps": None}]}
    assert client.post(f"/v1/drives/{drive}/locations", headers=TOKEN, json=samples).status_code == 200
    samples["samples"][0]["latitude"] = 26
    assert client.post(f"/v1/drives/{drive}/locations", headers=TOKEN, json=samples).status_code == 409
    assert client.post(f"/v1/drives/{drive}/complete", headers=TOKEN, json={}).status_code == 200
    assert client.post(f"/v1/drives/{drive}/complete", headers=TOKEN, json={}).status_code == 200
    with app.state.config.Session() as db:
        assert len(list(db.scalars(select(Job)))) == 1
    process_once(app.state.config)
    result = client.get(f"/v1/drives/{drive}", headers=TOKEN).json()
    assert result["hazards"][0]["location"] is None
    assert client.get(result["hazards"][0]["evidence_url"]).status_code == 401


def test_worker_failure_retry_and_reclaims_expired_lease(tmp_path):
    app, client, drive, url = setup_drive(tmp_path, analyzer="nonexistent:analyze")
    client.put(url, headers={**TOKEN, "Content-Type": "video/mp4"}, content=VIDEO)
    client.post(f"/v1/drives/{drive}/complete", headers=TOKEN, json={})
    assert process_once(app.state.config)
    assert client.get(f"/v1/drives/{drive}", headers=TOKEN).json()["status"] == "failed"
    app.state.config.analyzer = "potpatrol.fixture_worker:analyze"
    assert client.post(f"/v1/drives/{drive}/retry", headers=TOKEN, json={}).json()["status"] == "queued"
    with app.state.config.Session.begin() as db:
        job = db.scalar(select(Job).where(Job.drive_id == drive))
        job.state = "processing"
        job.lease_until = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        db.get(Drive, drive).status = "processing"
    assert process_once(app.state.config)
    assert client.get(f"/v1/drives/{drive}", headers=TOKEN).json()["status"] == "complete"
    with app.state.config.Session() as db:
        assert db.scalar(select(Job).where(Job.drive_id == drive)).attempts == 2


def test_manifest_rejects_path_traversal(tmp_path):
    (tmp_path / "analysis.jpg").write_bytes(b"\xff\xd8\xff")
    event = {"video_offset_ms": 100, "category": "pothole", "confidence": 0.9, "evidence_path": "../analysis.jpg"}
    try:
        validate_manifest({"schema_version": 1, "events": [event]}, tmp_path / "subdir")
    except ValueError as exc:
        assert "Unsafe evidence" in str(exc)
    else:
        raise AssertionError("Unsafe path was accepted")
