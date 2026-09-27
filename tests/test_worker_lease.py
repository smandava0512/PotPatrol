from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Thread

from fastapi.testclient import TestClient
from sqlalchemy import select

from potpatrol.api import create_app
from potpatrol.db import Drive, Hazard, Job
from potpatrol.fixture_worker import analyze as fixture_analyze
from potpatrol import worker

VIDEO = (Path(__file__).parent.parent / "fixtures" / "sample-drive.mp4").read_bytes()
AUTH = {"X-Device-Token": "phone-one"}


def test_expired_attempt_cannot_fail_newer_completed_attempt(tmp_path, monkeypatch):
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}",
                     storage_dir=tmp_path / "media", token="phone-one",
                     analyzer="potpatrol.fixture_worker:analyze")
    client = TestClient(app)
    drive_id = client.post("/v1/drives", headers=AUTH).json()["drive_id"]
    upload = client.post(f"/v1/drives/{drive_id}/upload-init", headers=AUTH).json()["upload_url"]
    assert client.put(upload, headers={**AUTH, "Content-Type": "video/mp4"}, content=VIDEO).status_code == 204
    assert client.post(f"/v1/drives/{drive_id}/complete", headers=AUTH, json={}).status_code == 200

    first_started = Event()
    release_first = Event()
    calls = []

    def analyze(video, output):
        calls.append(1)
        if len(calls) == 1:
            first_started.set()
            assert release_first.wait(timeout=10)
        return fixture_analyze(video, output)

    monkeypatch.setattr(worker, "load_callable", lambda spec: analyze)
    first = Thread(target=worker.process_once, args=(app.state.config,))
    first.start()
    try:
        assert first_started.wait(timeout=5)
        with app.state.config.Session.begin() as db:
            job = db.scalar(select(Job).where(Job.drive_id == drive_id))
            job.lease_until = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        assert worker.process_once(app.state.config) is True
    finally:
        release_first.set()
        first.join(timeout=10)
    assert not first.is_alive()
    with app.state.config.Session() as db:
        job = db.scalar(select(Job).where(Job.drive_id == drive_id))
        drive = db.get(Drive, drive_id)
        assert job.state == "done" and job.attempts == 2
        assert drive.status == "complete"
    assert client.get(f"/v1/drives/{drive_id}", headers=AUTH).json()["status"] == "complete"


def test_only_active_claim_can_renew_lease(tmp_path):
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'renew.db').as_posix()}",
                     storage_dir=tmp_path / "media", token="phone-one")
    client = TestClient(app)
    drive_id = client.post("/v1/drives", headers=AUTH).json()["drive_id"]
    with app.state.config.Session.begin() as db:
        job = Job(id="job-renew", drive_id=drive_id, state="processing", attempts=1,
                  claim_token="current", lease_until=(datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"))
        db.add(job)
    assert worker.renew_claim(app.state.config, "job-renew", "stale") is False
    assert worker.renew_claim(app.state.config, "job-renew", "current") is True
    with app.state.config.Session() as db:
        assert db.get(Job, "job-renew").lease_until > (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat().replace("+00:00", "Z")


def test_reclaimed_attempt_cannot_publish_while_current_attempt_runs(tmp_path, monkeypatch):
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'overlap.db').as_posix()}",
                     storage_dir=tmp_path / "media", token="phone-one",
                     analyzer="potpatrol.fixture_worker:analyze")
    client = TestClient(app)
    drive_id = client.post("/v1/drives", headers=AUTH).json()["drive_id"]
    url = client.post(f"/v1/drives/{drive_id}/upload-init", headers=AUTH).json()["upload_url"]
    assert client.put(url, headers={**AUTH, "Content-Type": "video/mp4"}, content=VIDEO).status_code == 204
    assert client.post(f"/v1/drives/{drive_id}/complete", headers=AUTH, json={}).status_code == 200
    first_started, second_started = Event(), Event()
    release_first, release_second = Event(), Event()
    outcomes = {}
    calls = []

    def analyze(video, output):
        calls.append(1)
        if len(calls) == 1:
            first_started.set()
            assert release_first.wait(timeout=10)
        else:
            second_started.set()
            assert release_second.wait(timeout=10)
        return fixture_analyze(video, output)

    monkeypatch.setattr(worker, "load_callable", lambda spec: analyze)
    first = Thread(target=lambda: outcomes.setdefault("first", worker.process_once(app.state.config)))
    second = Thread(target=lambda: outcomes.setdefault("second", worker.process_once(app.state.config)))
    first.start()
    try:
        assert first_started.wait(timeout=5)
        with app.state.config.Session.begin() as db:
            db.scalar(select(Job).where(Job.drive_id == drive_id)).lease_until = (
                datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        second.start()
        assert second_started.wait(timeout=5)
        release_first.set()
        first.join(timeout=10)
        assert not first.is_alive()
        assert outcomes["first"] is False
        with app.state.config.Session() as db:
            assert db.get(Drive, drive_id).status == "processing"
            assert db.scalar(select(Hazard).where(Hazard.drive_id == drive_id)) is None
    finally:
        release_first.set()
        release_second.set()
        first.join(timeout=10)
        if second.ident:
            second.join(timeout=10)
    assert not second.is_alive() and outcomes["second"] is True
    assert client.get(f"/v1/drives/{drive_id}", headers=AUTH).json()["status"] == "complete"
