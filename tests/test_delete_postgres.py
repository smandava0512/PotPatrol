"""Optional real-PostgreSQL regression for deletion/worker locking.

Run only against an ephemeral local PostgreSQL database via POTPATROL_DELETE_QA_URL.
The fixture creates and drops its own randomly named schema; never set this to production.
"""
import os
import time
import uuid
from pathlib import Path
from threading import Event, Thread

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url

from potpatrol.api import create_app
from potpatrol.db import Drive, Evidence, Hazard, Job, Location, ReportDraft
from potpatrol.storage import LocalStore
from potpatrol.worker import process_once

VIDEO = (Path(__file__).parent.parent / "fixtures" / "sample-drive.mp4").read_bytes()
AUTH = {"X-Device-Token": "ephemeral-qa-phone"}


@pytest.fixture
def postgres_url():
    configured = os.environ.get("POTPATROL_DELETE_QA_URL")
    if not configured:
        pytest.skip("set POTPATROL_DELETE_QA_URL for an isolated PostgreSQL QA container")
    base = make_url(configured)
    if base.get_backend_name() != "postgresql" or base.host not in ("127.0.0.1", "localhost"):
        pytest.fail("QA URL must point to localhost PostgreSQL, never a production host")
    base = base.set(query={**base.query, "connect_timeout": "5"})
    schema = "qa_delete_" + uuid.uuid4().hex
    engine = create_engine(base)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield str(base.set(query={**base.query, "options": f"-csearch_path={schema} -c lock_timeout=5s"}))
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_postgres_worker_and_delete_are_serialized_without_republishing(postgres_url, tmp_path):
    publishing, release = Event(), Event()

    class PauseEvidence(LocalStore):
        def put_file(self, key, source, content_type):
            if key.startswith("evidence/"):
                publishing.set()
                assert release.wait(timeout=8)
            super().put_file(key, source, content_type)

    app = create_app(db_url=postgres_url, storage_dir=tmp_path / "media", token=AUTH["X-Device-Token"],
                     analyzer="potpatrol.fixture_worker:analyze", store=PauseEvidence(tmp_path / "media"))
    client = TestClient(app)
    drive = client.post("/v1/drives", headers=AUTH).json()["drive_id"]
    url = client.post(f"/v1/drives/{drive}/upload-init", headers=AUTH).json()["upload_url"]
    assert client.put(url, headers={**AUTH, "Content-Type": "video/mp4"}, content=VIDEO).status_code == 204
    assert client.post(f"/v1/drives/{drive}/complete", headers=AUTH, json={}).status_code == 200
    results, errors = [], []

    def run(label, call):
        try:
            results.append((label, call()))
        except Exception as exc:
            errors.append((label, exc))

    worker = Thread(target=lambda: run("worker", lambda: process_once(app.state.config)))
    worker.start()
    assert publishing.wait(timeout=5)
    deletion = Thread(target=lambda: run("delete", lambda: client.delete(f"/v1/drives/{drive}", headers=AUTH).status_code))
    deletion.start()
    try:
        # Exercise DELETE while worker owns both PostgreSQL row locks.
        time.sleep(0.15)
        assert deletion.is_alive()
    finally:
        release.set()
        worker.join(timeout=8)
        deletion.join(timeout=8)
    assert not worker.is_alive() and not deletion.is_alive(), errors
    assert errors == []
    assert sorted(results) == [("delete", 204), ("worker", True)]
    assert client.delete(f"/v1/drives/{drive}", headers=AUTH).status_code == 204
    with app.state.config.Session() as db:
        for model in (Drive, Job, Hazard, Evidence, Location, ReportDraft):
            assert db.scalars(select(model)).all() == []
    assert not (tmp_path / "media" / "evidence" / drive).exists()
    assert not (tmp_path / "media" / "videos" / drive).exists()


def test_postgres_migration_adds_durable_receipts(postgres_url, monkeypatch):
    monkeypatch.setenv("POTPATROL_DATABASE_URL", postgres_url)
    config = AlembicConfig(str(Path(__file__).parent.parent / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(postgres_url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "fc86b25c81a7"
        assert [column["name"] for column in inspect(connection).get_columns("deletion_receipts")] == ["digest"]
    engine.dispose()
