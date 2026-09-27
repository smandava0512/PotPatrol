from pathlib import Path
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from potpatrol.api import create_app
from potpatrol.db import Drive, Evidence, Hazard, Job, Location, ReportDraft
from potpatrol.fixture_worker import analyze as fixture_analyze
from potpatrol.storage import LocalStore, S3Store
from potpatrol import worker
from potpatrol.worker import process_once

VIDEO = (Path(__file__).parent.parent / "fixtures" / "sample-drive.mp4").read_bytes()
ONE = {"X-Device-Token": "phone-one"}


def test_delete_owned_drive_purges_all_rows_and_immutable_media(tmp_path):
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}", storage_dir=tmp_path / "media",
                     token="phone-one", analyzer="potpatrol.fixture_worker:analyze")
    client = TestClient(app)
    drive_id = client.post("/v1/drives", headers=ONE).json()["drive_id"]
    url = client.post(f"/v1/drives/{drive_id}/upload-init", headers=ONE).json()["upload_url"]
    for _ in range(2):
        assert client.put(url, headers={**ONE, "Content-Type": "video/mp4"}, content=VIDEO).status_code == 204
    assert len(list((tmp_path / "media" / "videos" / drive_id).iterdir())) == 2
    assert client.post(f"/v1/drives/{drive_id}/locations", headers=ONE, json={"samples": [
        {"offset_ms": 0, "recorded_at": "2026-09-26T12:00:00Z", "latitude": 25.7, "longitude": -80.2}
    ]}).status_code == 200
    assert client.post(f"/v1/drives/{drive_id}/complete", headers=ONE, json={}).status_code == 200
    assert process_once(app.state.config) is True
    hazard_id = client.get(f"/v1/drives/{drive_id}", headers=ONE).json()["hazards"][0]["hazard_id"]
    assert client.post(f"/v1/hazards/{hazard_id}/report-draft", headers=ONE).status_code == 200

    assert client.delete(f"/v1/drives/{drive_id}", headers=ONE).status_code == 204
    assert not (tmp_path / "media" / "videos" / drive_id).exists()
    assert not (tmp_path / "media" / "evidence" / drive_id).exists()
    with app.state.config.Session() as db:
        for model in (Drive, Job, Location, Hazard, Evidence, ReportDraft):
            assert db.scalars(select(model)).all() == []
    assert client.get(f"/v1/drives/{drive_id}", headers=ONE).status_code == 404
    assert client.get(f"/v1/hazards/{hazard_id}/evidence", headers=ONE).status_code == 404
    assert client.post(f"/v1/hazards/{hazard_id}/report-draft", headers=ONE).status_code == 404


def test_foreign_unauthenticated_missing_and_repeated_delete_do_not_touch_other_drive(tmp_path, monkeypatch):
    monkeypatch.setenv("POTPATROL_DEVICE_TOKENS", "phone-one,phone-two")
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}", storage_dir=tmp_path / "media")
    client = TestClient(app)
    first = client.post("/v1/drives", headers=ONE).json()["drive_id"]
    two = {"X-Device-Token": "phone-two"}
    other = client.post("/v1/drives", headers=two).json()["drive_id"]
    url = client.post(f"/v1/drives/{first}/upload-init", headers=ONE).json()["upload_url"]
    assert client.put(url, headers={**ONE, "Content-Type": "video/mp4"}, content=VIDEO).status_code == 204
    assert client.delete(f"/v1/drives/{first}").status_code == 401
    assert client.delete(f"/v1/drives/{first}", headers=two).status_code == 404
    assert client.delete(f"/v1/drives/{other}", headers=ONE).status_code == 404
    assert (tmp_path / "media" / "videos" / first).exists()
    assert client.delete(f"/v1/drives/{first}", headers=ONE).status_code == 204
    assert client.delete(f"/v1/drives/{first}", headers=ONE).status_code == 404
    assert client.delete(f"/v1/drives/00000000-0000-0000-0000-000000000000", headers=ONE).status_code == 404
    assert client.get(f"/v1/drives/{other}", headers=two).status_code == 200


def test_failed_storage_cleanup_is_not_success_and_can_be_retried(tmp_path):
    class FailingStore(LocalStore):
        fail = True

        def delete_prefix(self, prefix):
            if self.fail and prefix.startswith("evidence/"):
                raise OSError("device unavailable")
            return super().delete_prefix(prefix)

    store = FailingStore(tmp_path / "media")
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}", storage_dir=tmp_path / "media", token="phone-one", store=store)
    client = TestClient(app)
    drive = client.post("/v1/drives", headers=ONE).json()["drive_id"]
    url = client.post(f"/v1/drives/{drive}/upload-init", headers=ONE).json()["upload_url"]
    assert client.put(url, headers={**ONE, "Content-Type": "video/mp4"}, content=VIDEO).status_code == 204
    assert client.delete(f"/v1/drives/{drive}", headers=ONE).status_code == 503
    assert client.get(f"/v1/drives/{drive}", headers=ONE).status_code == 200
    store.fail = False
    assert client.delete(f"/v1/drives/{drive}", headers=ONE).status_code == 204
    assert client.get(f"/v1/drives/{drive}", headers=ONE).status_code == 404


def test_s3_prefix_cleanup_paginates_and_never_deletes_siblings(tmp_path):
    class ListingS3:
        def __init__(self):
            self.objects = {}

        def upload_file(self, filename, bucket, key, ExtraArgs):
            self.objects[(bucket, key)] = Path(filename).read_bytes()

        def list_objects_v2(self, Bucket, Prefix):
            keys = sorted(k for bucket, k in self.objects if bucket == Bucket and k.startswith(Prefix))
            return {"Contents": [{"Key": k} for k in keys[:2]]} if keys else {}

        def delete_objects(self, Bucket, Delete):
            for item in Delete["Objects"]:
                self.objects.pop((Bucket, item["Key"]))
            return {}

    remote = ListingS3()
    store = S3Store("bucket", "scope", remote)
    source = tmp_path / "source"
    source.write_bytes(b"private")
    for key in ["videos/abc/a.mp4", "videos/abc/b.mp4", "videos/abc/c.mp4", "videos/abcd/keep.mp4"]:
        store.put_file(key, source, "video/mp4")
    store.delete_prefix("videos/abc")
    assert sorted(key for _, key in remote.objects) == ["scope/videos/abcd/keep.mp4"]


def test_s3_refuses_false_delete_success_and_recovers_on_retry():
    class StuckS3:
        def __init__(self):
            self.objects = {"scope/videos/abc/a.mp4"}
            self.stuck = True

        def list_objects_v2(self, Bucket, Prefix):
            return {"Contents": [{"Key": key} for key in self.objects if key.startswith(Prefix)]}

        def delete_objects(self, Bucket, Delete):
            if not self.stuck:
                self.objects.clear()
            return {}

    client = StuckS3()
    store = S3Store("bucket", "scope", client)
    with pytest.raises(OSError):
        store.delete_prefix("videos/abc")
    client.stuck = False
    store.delete_prefix("videos/abc")
    assert client.objects == set()


def test_delete_while_worker_analyzes_cannot_republish(tmp_path, monkeypatch):
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}", storage_dir=tmp_path / "media",
                     token="phone-one", analyzer="potpatrol.fixture_worker:analyze")
    client = TestClient(app)
    drive = client.post("/v1/drives", headers=ONE).json()["drive_id"]
    url = client.post(f"/v1/drives/{drive}/upload-init", headers=ONE).json()["upload_url"]
    assert client.put(url, headers={**ONE, "Content-Type": "video/mp4"}, content=VIDEO).status_code == 204
    assert client.post(f"/v1/drives/{drive}/complete", headers=ONE, json={}).status_code == 200
    started, release = Event(), Event()
    outcomes = []

    def paused_analyzer(video, output):
        started.set()
        assert release.wait(timeout=10)
        return fixture_analyze(video, output)

    monkeypatch.setattr(worker, "load_callable", lambda spec: paused_analyzer)
    thread = Thread(target=lambda: outcomes.append(process_once(app.state.config)))
    thread.start()
    try:
        assert started.wait(timeout=5)
        assert client.delete(f"/v1/drives/{drive}", headers=ONE).status_code == 204
    finally:
        release.set()
        thread.join(timeout=10)
    assert not thread.is_alive() and outcomes == [False]
    assert not (tmp_path / "media" / "evidence" / drive).exists()
    assert not (tmp_path / "media" / "videos" / drive).exists()
    with app.state.config.Session() as db:
        assert db.scalars(select(Hazard)).all() == []
        assert db.scalars(select(Job)).all() == []
