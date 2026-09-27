"""Published optional time and Dev 3 report/analysis boundary tests."""
from pathlib import Path

from fastapi.testclient import TestClient

from potpatrol.api import create_app
from potpatrol.worker import process_once

TOKEN = {"X-Device-Token": "demo-secret"}
MP4 = (Path(__file__).parent.parent / "fixtures" / "sample-drive.mp4").read_bytes()


def drive_flow(tmp_path, monkeypatch, *, started_at=None, samples=None):
    monkeypatch.setenv("POTPATROL_ANALYSIS_MODE", "fixture")
    monkeypatch.setenv("POTPATROL_REPORTER", "potpatrol.integration:draft_report")
    db_url = f"sqlite:///{(tmp_path / 'drive.db').as_posix()}"
    app = create_app(db_url=db_url, storage_dir=tmp_path / "storage", token="demo-secret",
                     analyzer="potpatrol.integration:analyze")
    client = TestClient(app)
    drive_id = client.post("/v1/drives", json={}, headers=TOKEN).json()["drive_id"]
    upload = client.post(f"/v1/drives/{drive_id}/upload-init", json={}, headers=TOKEN).json()
    assert client.put(upload["upload_url"], content=MP4, headers={**TOKEN, **upload["headers"]}).status_code == 204
    if samples is not None:
        assert client.post(f"/v1/drives/{drive_id}/locations", json={"samples": samples}, headers=TOKEN).status_code == 200
    payload = {"video_started_at": started_at} if started_at else {}
    assert client.post(f"/v1/drives/{drive_id}/complete", json=payload, headers=TOKEN).status_code == 200
    assert process_once(app.state.config)
    result = client.get(f"/v1/drives/{drive_id}", headers=TOKEN).json()
    assert result["status"] == "complete", result
    assert result["analysis_mode"] == "fixture"
    assert len(result["hazards"]) == 2
    return client, result


def test_no_gps_or_start_time_preserves_hazards_and_report(tmp_path, monkeypatch):
    client, drive = drive_flow(tmp_path, monkeypatch)
    for hazard in drive["hazards"]:
        assert hazard["location"] is None
        assert hazard["observed_at"] is None
        assert hazard["severity"] is None
        assert client.get(hazard["evidence_url"], headers=TOKEN).status_code == 200
        draft = client.post(f"/v1/hazards/{hazard['hazard_id']}/report-draft", json={}, headers=TOKEN).json()
        assert draft["destination"]["status"] == "needs_review"
        assert draft["destination"]["url"] is None
        assert draft["destination"]["candidates"] == []
        assert draft["fields"]["observation_time"]["value"] is None
        assert draft["submission_status"] == "not_submitted"


def test_first_frame_time_maps_offset_and_miami_is_review(tmp_path, monkeypatch):
    sample = {"offset_ms": 36700, "recorded_at": "2026-09-26T18:04:49Z",
              "latitude": 25.7563, "longitude": -80.374, "horizontal_accuracy_m": 8}
    client, drive = drive_flow(tmp_path, monkeypatch, started_at="2026-09-26T18:04:12Z", samples=[sample])
    hazard = next(h for h in drive["hazards"] if h["video_offset_ms"] == 36700)
    assert hazard["observed_at"] == "2026-09-26T18:04:48.700000Z"
    draft = client.post(f"/v1/hazards/{hazard['hazard_id']}/report-draft", json={}, headers=TOKEN).json()
    assert draft["fields"]["observation_time"]["value"] == hazard["observed_at"]
    assert draft["destination"]["status"] == "needs_review"
    assert len(draft["destination"]["candidates"]) == 3
    assert draft["submission_status"] == "not_submitted"


def test_outside_supported_region_and_invalid_start_time(tmp_path, monkeypatch):
    sample = {"offset_ms": 36700, "recorded_at": "2026-09-26T18:04:49Z",
              "latitude": 40.7128, "longitude": -74.006, "horizontal_accuracy_m": 8}
    client, drive = drive_flow(tmp_path, monkeypatch, started_at="2026-09-26T18:04:12Z", samples=[sample])
    hazard = next(h for h in drive["hazards"] if h["video_offset_ms"] == 36700)
    draft = client.post(f"/v1/hazards/{hazard['hazard_id']}/report-draft", json={}, headers=TOKEN).json()
    assert draft["destination"]["status"] == "unsupported"
    assert draft["destination"]["url"] is None
    created = client.post("/v1/drives", json={}, headers=TOKEN).json()["drive_id"]
    assert client.post(f"/v1/drives/{created}/complete", json={"video_started_at": "2026-09-26T18:04:12"}, headers=TOKEN).status_code == 422
