"""Synthetic manifest boundary tests; no fixture is represented as real analysis."""
import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from potpatrol.api import create_app, owner_hash
from potpatrol.db import Drive, Job
from potpatrol.worker import process_once

TOKEN = {"X-Device-Token": "provenance-test-token"}
JPEG = b"\xff\xd8\xff\xd9"


def run_manifest(tmp_path, monkeypatch, manifest, *, required=True):
    monkeypatch.setenv("POTPATROL_REPORTER", "potpatrol.integration:draft_report")
    if required:
        monkeypatch.setenv("POTPATROL_VISION_MODE", "gemini_required")
    else:
        monkeypatch.delenv("POTPATROL_VISION_MODE", raising=False)
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'drive.db').as_posix()}",
                     storage_dir=tmp_path / "storage", token=TOKEN["X-Device-Token"], analyzer="synthetic:analyze")
    drive_id = str(uuid.uuid4())
    app.state.config.store.put_file(f"videos/{drive_id}/sample.mp4", Path(__file__), "video/mp4")
    with app.state.config.Session.begin() as db:
        db.add(Drive(id=drive_id, owner=owner_hash(TOKEN["X-Device-Token"]), status="queued",
                     video_key=f"videos/{drive_id}/sample.mp4", created_at="2026-09-27T00:00:00Z"))
        db.add(Job(id=str(uuid.uuid4()), drive_id=drive_id, state="pending", attempts=0))

    def analyze(video, output):
        for event in manifest["events"]:
            path = Path(output, event["evidence_path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(JPEG)
        result = Path(output, "analysis.json")
        result.write_text(json.dumps(manifest), encoding="utf-8")
        return str(result)

    from potpatrol.integration import draft_report
    monkeypatch.setattr("potpatrol.worker.load_callable", lambda spec: analyze if spec == "synthetic:analyze" else draft_report)
    assert process_once(app.state.config)
    return TestClient(app), drive_id


def manifest(source="gemini_scan"):
    return {"schema_version": 1, "mode": "model", "vision_mode": "gemini_required",
            "gemini_frames_scanned": 4, "validator": {"provider": "gemini", "model": "gemini-test-model"},
            "events": [{"category": "pothole", "confidence": 0.8, "video_offset_ms": 1000,
                        "evidence_path": "evidence/a.jpg", "source": source,
                        **({"validation": {"provider": "gemini", "model": "gemini-test-model",
                                            "is_hazard": True, "confidence": 0.91}}
                           if source == "yolo_gemini_validated" else {})}]}


def test_required_manifest_persists_and_reports_scanned_provenance(tmp_path, monkeypatch):
    client, drive_id = run_manifest(tmp_path, monkeypatch, manifest())
    result = client.get(f"/v1/drives/{drive_id}", headers=TOKEN).json()
    assert result["status"] == "complete"
    assert result["vision_mode"] == "gemini_required"
    assert result["validator_model"] == "gemini-test-model"
    assert result["gemini_frames_scanned"] == 4
    hazard = result["hazards"][0]
    assert hazard["source"] == "gemini_scan" and hazard["validation"] is None
    assert hazard["location"] is None and hazard["review_state"] == "needs_review"
    assert client.get(f"/v1/drives/{drive_id}", headers={"X-Device-Token": "wrong"}).status_code == 401
    draft = client.post(f"/v1/hazards/{hazard['hazard_id']}/report-draft", headers=TOKEN).json()
    assert draft["fields"]["provenance"]["category"]["source"] == "validator"
    assert draft["fields"]["provenance"]["detector"]["source"] == "validator"
    assert draft["fields"]["provenance"]["source"]["value"] == "gemini_scan"
    assert draft["fields"]["provenance"]["validator_model"]["value"] == "gemini-test-model"
    assert draft["fields"]["provenance"]["gemini_frames_scanned"]["value"] == 4
    assert draft["fields"]["latitude"] is None


def test_required_manifest_persists_yolo_validation(tmp_path, monkeypatch):
    client, drive_id = run_manifest(tmp_path, monkeypatch, manifest("yolo_gemini_validated"))
    hazard = client.get(f"/v1/drives/{drive_id}", headers=TOKEN).json()["hazards"][0]
    assert hazard["validation"]["confidence"] == 0.91
    draft = client.post(f"/v1/hazards/{hazard['hazard_id']}/report-draft", headers=TOKEN).json()
    provenance = draft["fields"]["provenance"]
    assert provenance["category"]["source"] == "detector"
    assert provenance["ai_check"]["value"] == hazard["validation"]
    assert provenance["source"]["value"] == "yolo_gemini_validated"


def test_required_rejects_fixture_or_unverified_manifest(tmp_path, monkeypatch):
    for idx, change in enumerate(({"mode": "fixture"}, {"vision_mode": None},
                                  {"gemini_frames_scanned": 0}, {"validator": {}},
                                  {"events": [{**manifest()["events"][0], "source": "yolo_gemini_validated"}]})):
        candidate = {**manifest(), **change}
        client, drive_id = run_manifest(tmp_path / str(idx), monkeypatch, candidate)
        result = client.get(f"/v1/drives/{drive_id}", headers=TOKEN).json()
        assert result["status"] == "failed", (change, result)
        assert result["hazards"] == []


def test_local_fixture_mode_remains_explicitly_available(tmp_path, monkeypatch):
    client, drive_id = run_manifest(tmp_path, monkeypatch, {"schema_version": 1, "mode": "fixture", "events": []}, required=False)
    result = client.get(f"/v1/drives/{drive_id}", headers=TOKEN).json()
    assert result["status"] == "complete" and result["analysis_mode"] == "fixture"
    assert result["vision_mode"] is None


def test_required_clean_result_retains_scan_provenance(tmp_path, monkeypatch):
    candidate = {**manifest(), "events": []}
    client, drive_id = run_manifest(tmp_path, monkeypatch, candidate)
    result = client.get(f"/v1/drives/{drive_id}", headers=TOKEN).json()
    assert result["status"] == "complete" and result["hazards"] == []
    assert result["gemini_frames_scanned"] == 4


def test_required_rejects_spoofed_validation_and_unbounded_metadata(tmp_path, monkeypatch):
    for index, changes in enumerate((
        {"validator": {"provider": "fixture", "model": "gemini-test-model"}},
        {"gemini_frames_scanned": 25},
        {"events": [{**manifest()["events"][0], "source": "detector"}]},
        {"events": [{**manifest("yolo_gemini_validated")["events"][0],
                     "validation": {"provider": "gemini", "model": "other", "is_hazard": True, "confidence": 0.9}}]},
    )):
        client, drive_id = run_manifest(tmp_path / str(index), monkeypatch, {**manifest(), **changes})
        result = client.get(f"/v1/drives/{drive_id}", headers=TOKEN).json()
        assert result["status"] == "failed" and result["hazards"] == []


def test_report_without_adapter_still_discloses_source(tmp_path, monkeypatch):
    client, drive_id = run_manifest(tmp_path, monkeypatch, manifest())
    client.app.state.config.reporter = ""
    hazard = client.get(f"/v1/drives/{drive_id}", headers=TOKEN).json()["hazards"][0]
    draft = client.post(f"/v1/hazards/{hazard['hazard_id']}/report-draft", headers=TOKEN).json()
    assert draft["fields"]["provenance"]["source"] == "gemini_scan"
    assert draft["fields"]["provenance"]["validator_model"] == "gemini-test-model"
