from pathlib import Path
from threading import Event, Thread

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select

from potpatrol.api import create_app
from potpatrol.db import Drive, Job, Hazard, ReportDraft, Location
from potpatrol.storage import LocalStore, S3Store
from potpatrol.worker import process_once

ONE = {"X-Device-Token": "phone-one"}
VIDEO = (Path(__file__).parent.parent / "fixtures" / "sample-drive.mp4").read_bytes()


def app_client(tmp_path, store=None):
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}", storage_dir=tmp_path / "media",
                     token="phone-one", analyzer="potpatrol.fixture_worker:analyze", store=store)
    return app, TestClient(app)


def test_storage_failure_leaves_durable_intent_and_blocks_mutators(tmp_path):
    class FailingStore(LocalStore):
        fail = True

        def delete_prefix(self, prefix):
            if self.fail:
                raise OSError("offline")
            super().delete_prefix(prefix)

    store = FailingStore(tmp_path / "media")
    app, client = app_client(tmp_path, store)
    drive = client.post('/v1/drives', headers=ONE).json()['drive_id']
    assert client.delete(f'/v1/drives/{drive}', headers=ONE).status_code == 503
    with app.state.config.Session() as db:
        assert db.get(Drive, drive).status == 'deleting'
    assert client.get(f'/v1/drives/{drive}', headers=ONE).json()['status'] == 'deleting'
    assert client.post(f'/v1/drives/{drive}/upload-init', headers=ONE).status_code == 409
    assert client.post(f'/v1/drives/{drive}/locations', headers=ONE, json={'samples': []}).status_code == 409
    store.fail = False
    assert client.delete(f'/v1/drives/{drive}', headers=ONE).status_code == 204


def test_final_commit_failure_keeps_deleting_and_retry_finishes(tmp_path):
    app, client = app_client(tmp_path)
    drive = client.post('/v1/drives', headers=ONE).json()['drive_id']
    commits = 0

    def fail_second_commit(session):
        nonlocal commits
        commits += 1
        if commits == 2:
            raise OSError('final commit failed')

    event.listen(app.state.config.Session, 'before_commit', fail_second_commit)
    try:
        with pytest.raises(OSError, match='final commit failed'):
            client.delete(f'/v1/drives/{drive}', headers=ONE)
    finally:
        event.remove(app.state.config.Session, 'before_commit', fail_second_commit)
    assert commits == 2
    with app.state.config.Session() as db:
        assert db.get(Drive, drive).status == 'deleting'
    assert client.delete(f'/v1/drives/{drive}', headers=ONE).status_code == 204
    assert client.get(f'/v1/drives/{drive}', headers=ONE).status_code == 404


def test_receipt_survives_restart_and_is_owner_bound(tmp_path, monkeypatch):
    monkeypatch.setenv('POTPATROL_DEVICE_TOKENS', 'phone-one,phone-two')
    app, client = app_client(tmp_path)
    drive = client.post('/v1/drives', headers=ONE).json()['drive_id']
    assert client.delete(f'/v1/drives/{drive}', headers=ONE).status_code == 204
    restarted = TestClient(create_app(db_url=app.state.config.db_url, storage_dir=tmp_path / 'media'))
    assert restarted.delete(f'/v1/drives/{drive}', headers=ONE).status_code == 204
    assert restarted.delete(f'/v1/drives/{drive}', headers={'X-Device-Token': 'phone-two'}).status_code == 404
    assert restarted.delete('/v1/drives/00000000-0000-0000-0000-000000000000', headers=ONE).status_code == 404


def test_worker_does_not_claim_job_for_deleting_drive(tmp_path):
    app, client = app_client(tmp_path)
    drive = client.post('/v1/drives', headers=ONE).json()['drive_id']
    with app.state.config.Session.begin() as db:
        db.add(Job(id='job', drive_id=drive, state='pending', attempts=0))
        db.get(Drive, drive).status = 'deleting'
    assert process_once(app.state.config) is False
    with app.state.config.Session() as db:
        assert db.get(Drive, drive).status == 'deleting'


def test_intent_is_visible_and_fences_concurrent_upload_and_locations(tmp_path):
    entered, release = Event(), Event()

    class PausedStore(LocalStore):
        def delete_prefix(self, prefix):
            entered.set()
            assert release.wait(10)
            super().delete_prefix(prefix)

    app, client = app_client(tmp_path, PausedStore(tmp_path / 'media'))
    drive = client.post('/v1/drives', headers=ONE).json()['drive_id']
    url = client.post(f'/v1/drives/{drive}/upload-init', headers=ONE).json()['upload_url']
    outcomes = []
    thread = Thread(target=lambda: outcomes.append(client.delete(f'/v1/drives/{drive}', headers=ONE).status_code))
    thread.start()
    try:
        assert entered.wait(5)
        assert client.get(f'/v1/drives/{drive}', headers=ONE).json()['status'] == 'deleting'
        assert client.put(url, headers={**ONE, 'Content-Type': 'video/mp4'}, content=VIDEO).status_code == 409
        assert client.post(f'/v1/drives/{drive}/locations', headers=ONE, json={'samples': [
            {'offset_ms': 0, 'recorded_at': '2026-09-26T12:00:00Z', 'latitude': 25, 'longitude': -80}
        ]}).status_code == 409
    finally:
        release.set()
        thread.join(10)
    assert outcomes == [204] and not thread.is_alive()
    with app.state.config.Session() as db:
        assert db.scalars(select(Location)).all() == []


def test_partial_deletion_fences_worker_and_report_draft(tmp_path):
    class FailingStore(LocalStore):
        fail = False
        def delete_prefix(self, prefix):
            if self.fail:
                raise OSError('offline')
            super().delete_prefix(prefix)

    store = FailingStore(tmp_path / 'media')
    app, client = app_client(tmp_path, store)
    drive = client.post('/v1/drives', headers=ONE).json()['drive_id']
    url = client.post(f'/v1/drives/{drive}/upload-init', headers=ONE).json()['upload_url']
    assert client.put(url, headers={**ONE, 'Content-Type': 'video/mp4'}, content=VIDEO).status_code == 204
    assert client.post(f'/v1/drives/{drive}/complete', headers=ONE, json={}).status_code == 200
    assert process_once(app.state.config) is True
    hazard = client.get(f'/v1/drives/{drive}', headers=ONE).json()['hazards'][0]['hazard_id']
    store.fail = True
    assert client.delete(f'/v1/drives/{drive}', headers=ONE).status_code == 503
    assert client.post(f'/v1/hazards/{hazard}/report-draft', headers=ONE).status_code == 409
    with app.state.config.Session() as db:
        assert db.scalars(select(ReportDraft)).all() == []
    store.fail = False
    assert client.delete(f'/v1/drives/{drive}', headers=ONE).status_code == 204


def test_s3_refuses_to_claim_cleanup_without_version_listing():
    class NoVersionListing:
        def list_object_versions(self, Bucket, Prefix):
            raise PermissionError('cannot inspect historical versions')
    with pytest.raises(PermissionError, match='historical versions'):
        S3Store('bucket', 'scope', NoVersionListing()).delete_prefix('videos/abc')


def test_s3_deletes_all_versions_including_delete_markers():
    class Versioned:
        def __init__(self):
            self.objects = [('scope/videos/abc/a.mp4', 'v1'), ('scope/videos/abc/a.mp4', 'v2'),
                            ('scope/videos/abc/a.mp4', 'marker'), ('scope/videos/abcd/keep.mp4', 'v3')]
        def list_object_versions(self, Bucket, Prefix):
            found = [(key, version) for key, version in self.objects if key.startswith(Prefix)]
            return {'Versions': [{'Key': k, 'VersionId': v} for k, v in found if v != 'marker'],
                    'DeleteMarkers': [{'Key': k, 'VersionId': v} for k, v in found if v == 'marker']}
        def delete_objects(self, Bucket, Delete):
            for item in Delete['Objects']:
                self.objects.remove((item['Key'], item['VersionId']))
            return {}
    remote = Versioned()
    S3Store('bucket', 'scope', remote).delete_prefix('videos/abc')
    assert remote.objects == [('scope/videos/abcd/keep.mp4', 'v3')]
