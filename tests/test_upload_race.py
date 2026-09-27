from pathlib import Path
from threading import Event, Thread

from fastapi.testclient import TestClient
from sqlalchemy import event

from potpatrol.api import create_app
from potpatrol.db import Drive
from potpatrol.storage import LocalStore

VIDEO = (Path(__file__).parent.parent / "fixtures" / "sample-drive.mp4").read_bytes()
AUTH = {"X-Device-Token": "phone-one"}


def setup_upload(tmp_path, store=None):
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'drive.db').as_posix()}",
                     storage_dir=tmp_path / "media", token="phone-one", store=store)
    client = TestClient(app)
    drive_id = client.post("/v1/drives", headers=AUTH).json()["drive_id"]
    url = client.post(f"/v1/drives/{drive_id}/upload-init", headers=AUTH).json()["upload_url"]
    return app, client, drive_id, url


def upload(client, url):
    return client.put(url, headers={**AUTH, "Content-Type": "video/mp4"}, content=VIDEO)


def test_replacement_upload_retains_immutable_prior_video(tmp_path):
    app, client, drive_id, url = setup_upload(tmp_path)
    assert upload(client, url).status_code == 204
    with app.state.config.Session() as session:
        original_key = session.get(Drive, drive_id).video_key
    assert upload(client, url).status_code == 204
    with app.state.config.Session() as session:
        replacement_key = session.get(Drive, drive_id).video_key
    assert replacement_key != original_key
    assert app.state.config.store.read_bytes(original_key) == VIDEO
    assert app.state.config.store.read_bytes(replacement_key) == VIDEO
    assert client.post(f"/v1/drives/{drive_id}/complete", headers=AUTH, json={}).status_code == 200
    assert upload(client, url).status_code == 409
    with app.state.config.Session() as session:
        assert session.get(Drive, drive_id).video_key == replacement_key


class PausingStore(LocalStore):
    def __init__(self, root):
        super().__init__(root)
        self.pause_next = False
        self.entered = Event()
        self.release = Event()

    def put_file(self, key, source, content_type):
        if self.pause_next:
            self.pause_next = False
            self.entered.set()
            assert self.release.wait(timeout=5), "Replacement upload stayed blocked"
        return super().put_file(key, source, content_type)


def test_complete_cannot_finish_during_replacement_publish(tmp_path):
    store = PausingStore(tmp_path / "bucket")
    app, client, drive_id, url = setup_upload(tmp_path, store)
    assert upload(client, url).status_code == 204
    with app.state.config.Session() as session:
        original_key = session.get(Drive, drive_id).video_key
    store.pause_next = True
    responses = {}
    finished = Event()

    def put_replacement():
        responses["put"] = upload(client, url)

    def finish_drive():
        responses["complete"] = client.post(f"/v1/drives/{drive_id}/complete", headers=AUTH, json={})
        finished.set()

    putting = Thread(target=put_replacement)
    completing = Thread(target=finish_drive)
    putting.start()
    try:
        assert store.entered.wait(timeout=5), "Replacement did not reach storage"
        completing.start()
        assert not finished.wait(timeout=0.2), "Completion committed before upload finished"
    finally:
        store.release.set()
        putting.join(timeout=10)
        if completing.ident:
            completing.join(timeout=10)
    assert not putting.is_alive() and not completing.is_alive()
    assert responses["put"].status_code == 204
    if responses["complete"].status_code == 409:
        responses["complete"] = client.post(f"/v1/drives/{drive_id}/complete", headers=AUTH, json={})
    assert responses["complete"].status_code == 200
    with app.state.config.Session() as session:
        selected = session.get(Drive, drive_id).video_key
    assert selected != original_key
    assert store.read_bytes(selected) == VIDEO
    assert store.read_bytes(original_key) == VIDEO


def test_upload_init_cannot_reopen_completed_drive(tmp_path):
    app, client, drive_id, url = setup_upload(tmp_path)
    assert upload(client, url).status_code == 204
    entered, release = Event(), Event()
    responses = {}
    initiating = Thread(target=lambda: responses.setdefault(
        "init", client.post(f"/v1/drives/{drive_id}/upload-init", headers=AUTH)))

    def pause_before_update(connection, cursor, statement, parameters, context, executemany):
        if "UPDATE drives SET" in statement and "upload_expires_at" in statement:
            entered.set()
            assert release.wait(timeout=5), "Upload-init update remained blocked"

    engine = app.state.config.Session.kw["bind"]
    event.listen(engine, "before_cursor_execute", pause_before_update)
    try:
        initiating.start()
        assert entered.wait(timeout=5), "Upload-init did not reach update"
        assert client.post(f"/v1/drives/{drive_id}/complete", headers=AUTH, json={}).status_code == 200
    finally:
        release.set()
        initiating.join(timeout=10)
        event.remove(engine, "before_cursor_execute", pause_before_update)
    assert not initiating.is_alive()
    assert responses["init"].status_code == 409
    assert client.get(f"/v1/drives/{drive_id}", headers=AUTH).json()["status"] == "queued"
