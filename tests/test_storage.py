from pathlib import Path

from fastapi.testclient import TestClient

from roadwatch.api import create_app
from roadwatch.worker import process_once
from roadwatch.storage import LocalStore, S3Store


def test_local_private_object_store_roundtrip(tmp_path):
    store = LocalStore(tmp_path / "bucket")
    source = tmp_path / "source.bin"
    source.write_bytes(b"data")
    store.put_file("videos/a.mp4", source, "video/mp4")
    assert store.exists("videos/a.mp4")
    target = tmp_path / "download.bin"
    store.download_file("videos/a.mp4", target)
    assert target.read_bytes() == b"data"
    assert store.read_bytes("videos/a.mp4") == b"data"


class FakeS3:
    def __init__(self):
        self.objects = {}

    def upload_file(self, filename, bucket, key, ExtraArgs):
        assert ExtraArgs["ContentType"] in ("image/jpeg", "video/mp4")
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise FileNotFoundError(Key)

    def download_file(self, bucket, key, filename):
        Path(filename).write_bytes(self.objects[(bucket, key)])

    def get_object(self, Bucket, Key):
        data = self.objects[(Bucket, Key)]
        class Body:
            def read(self):
                return data
        return {"Body": Body()}


def test_s3_store_private_prefix(tmp_path):
    s3 = FakeS3()
    store = S3Store("private-bucket", "roadwatch", s3)
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"photo")
    store.put_file("evidence/a.jpg", source, "image/jpeg")
    assert ("private-bucket", "roadwatch/evidence/a.jpg") in s3.objects
    assert store.exists("evidence/a.jpg")
    out = tmp_path / "out.jpg"
    store.download_file("evidence/a.jpg", out)
    assert out.read_bytes() == store.read_bytes("evidence/a.jpg") == b"photo"


def test_s3_upload_and_worker_flow(tmp_path):
    s3 = FakeS3()
    store = S3Store("private-bucket", "roadwatch", s3)
    app = create_app(db_url=f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}", storage_dir=tmp_path / "temp", token="secret", analyzer="roadwatch.fixture_worker:analyze", store=store)
    client = TestClient(app)
    headers = {"X-Device-Token": "secret"}
    drive = client.post("/v1/drives", headers=headers, json={}).json()["drive_id"]
    upload = client.post(f"/v1/drives/{drive}/upload-init", headers=headers, json={}).json()
    video = (Path(__file__).parent.parent / "fixtures" / "sample-drive.mp4").read_bytes()
    assert client.put(upload["upload_url"], headers={**headers, "Content-Type": "video/mp4"}, content=video).status_code == 204
    assert ("private-bucket", f"roadwatch/videos/{drive}.mp4") in s3.objects
    client.post(f"/v1/drives/{drive}/complete", headers=headers, json={})
    assert process_once(app.state.config)
    result = client.get(f"/v1/drives/{drive}", headers=headers).json()
    assert result["status"] == "complete"
    evidence = client.get(result["hazards"][0]["evidence_url"], headers=headers)
    assert evidence.status_code == 200 and evidence.content[:3] == b"\xff\xd8\xff"
