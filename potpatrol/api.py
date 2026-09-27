import hashlib
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import Response as BytesResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update

from .db import Drive, Evidence, Hazard, Job, Location, ReportDraft, session_factory
from .storage import LocalStore, S3Store

MAX_BYTES = 100 * 1024 * 1024
MAX_OFFSET = 600_000


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset_ms: int = Field(ge=0, le=MAX_OFFSET)
    recorded_at: datetime
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    horizontal_accuracy_m: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    speed_mps: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("recorded_at")
    @classmethod
    def require_utc(cls, value):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("recorded_at must be an absolute UTC time")
        return value


class Batch(BaseModel):
    samples: list[Point] = Field(max_length=2000)

class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_started_at: datetime | None = None

    @field_validator("video_started_at")
    @classmethod
    def require_utc(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
            raise ValueError("video_started_at must be an absolute UTC time")
        return value


def config_env(key, default=""):
    """PotPatrol settings take priority; old RoadWatch names remain compatible."""
    return os.environ.get(f"POTPATROL_{key}") or os.environ.get(f"ROADWATCH_{key}") or default


class Config:
    def __init__(self, db_url=None, storage_dir=None, token=None, analyzer=None, store=None):
        self.db_url = db_url or config_env("DATABASE_URL", "sqlite:///./potpatrol.db")
        self.storage_dir = Path(storage_dir or config_env("STORAGE_DIR", "./.potpatrol-storage")).resolve()
        self.token = token if token is not None else config_env("DEVICE_TOKEN")
        extra_tokens = config_env("DEVICE_TOKENS")
        additional = [item.strip() for item in extra_tokens.split(",")] if extra_tokens else []
        if any(not item for item in additional):
            raise RuntimeError("POTPATROL_DEVICE_TOKENS contains an empty credential")
        self.tokens = tuple(dict.fromkeys(([self.token] if self.token else []) + additional))
        self.analyzer = analyzer if analyzer is not None else config_env("ANALYZER")
        self.reporter = config_env("REPORTER")
        if not self.tokens:
            raise RuntimeError("Set POTPATROL_DEVICE_TOKEN or POTPATROL_DEVICE_TOKENS before starting API")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        bucket = config_env("S3_BUCKET")
        self.store = store or (S3Store(bucket, config_env("S3_PREFIX")) if bucket else LocalStore(self.storage_dir))
        self.Session = session_factory(self.db_url)


def owner_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def owned(session, model, item_id, owner):
    obj = session.get(model, str(item_id))
    if obj is None:
        raise HTTPException(404, "Not found")
    if isinstance(obj, Drive):
        drive = obj
    elif isinstance(obj, Hazard):
        drive = session.get(Drive, obj.drive_id)
    else:
        raise RuntimeError("Unsupported owned model")
    if drive.owner != owner:
        raise HTTPException(404, "Not found")
    return obj


def create_app(db_url=None, storage_dir=None, token=None, analyzer=None, store=None):
    config = Config(db_url, storage_dir, token, analyzer, store)
    app = FastAPI(title="PotPatrol API", version="1.0.0")
    app.state.config = config

    def auth(x_device_token: Annotated[str | None, Header()] = None):
        import hmac
        matched = False
        if x_device_token:
            for configured in config.tokens:
                matched |= hmac.compare_digest(x_device_token, configured)
        if not matched:
            raise HTTPException(401, "Invalid device token")
        return owner_hash(x_device_token)

    Owner = Annotated[str, Depends(auth)]

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/drives", status_code=201)
    def create_drive(owner: Owner):
        drive = Drive(id=str(uuid.uuid4()), owner=owner, status="created", created_at=utc_now())
        with config.Session.begin() as db:
            db.add(drive)
        return {"drive_id": drive.id, "status": drive.status}

    @app.post("/v1/drives/{drive_id}/upload-init")
    def upload_init(drive_id: uuid.UUID, request: Request, owner: Owner):
        with config.Session.begin() as db:
            drive = owned(db, Drive, drive_id, owner)
            expiry = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
            renewed = db.execute(update(Drive).where(
                Drive.id == drive.id, Drive.owner == owner,
                Drive.status.in_(("created", "uploading")),
            ).values(upload_expires_at=expiry, status="uploading"))
            if renewed.rowcount != 1:
                raise HTTPException(409, "Drive no longer accepts uploads")
        return {"upload_url": str(request.url_for("put_video", drive_id=str(drive_id))), "method": "PUT", "headers": {"Content-Type": "video/mp4"}, "expires_at": expiry}

    @app.put("/v1/drives/{drive_id}/video", status_code=204, name="put_video")
    async def put_video(drive_id: uuid.UUID, request: Request, owner: Owner):
        with config.Session() as db:
            drive = owned(db, Drive, drive_id, owner)
            if drive.status != "uploading" or not drive.upload_expires_at or drive.upload_expires_at < utc_now():
                raise HTTPException(409, "Request a fresh upload-init first")
        if request.headers.get("content-type", "").split(";")[0].lower() != "video/mp4":
            raise HTTPException(415, "Expected video/mp4")
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=config.storage_dir, suffix=".mp4", delete=False) as out:
                temp = Path(out.name)
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, "MP4 exceeds 100 MiB")
                    out.write(chunk)
            with temp.open("rb") as src:
                magic = src.read(12)
            if len(magic) < 12 or magic[4:8] != b"ftyp":
                raise HTTPException(422, "Invalid MP4 header")
            probe = shutil.which("ffprobe")
            if probe:
                result = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(temp)], capture_output=True, text=True, timeout=15)
                try:
                    duration = float(result.stdout.strip())
                except ValueError:
                    raise HTTPException(422, "Unreadable MP4") from None
                if result.returncode or duration <= 0 or duration > 600:
                    raise HTTPException(422, "Invalid or overlong MP4")
            with config.Session.begin() as db:
                key = f"videos/{drive_id}/{uuid.uuid4().hex}.mp4"
                published = db.execute(update(Drive).where(
                    Drive.id == str(drive_id), Drive.owner == owner, Drive.status == "uploading",
                    Drive.upload_expires_at >= utc_now(),
                ).values(video_key=key))
                if published.rowcount != 1:
                    raise HTTPException(409, "Drive no longer accepts uploads")
                # The conditional UPDATE locks the drive until this unique key is stored.
                # /complete must not freeze a partially written or replaced object.
                config.store.put_file(key, temp, "video/mp4")
            return Response(status_code=204)
        finally:
            if temp:
                temp.unlink(missing_ok=True)

    @app.post("/v1/drives/{drive_id}/locations")
    def locations(drive_id: uuid.UUID, batch: Batch, owner: Owner):
        accepted = 0
        with config.Session.begin() as db:
            drive = owned(db, Drive, drive_id, owner)
            if drive.status not in ("created", "uploading"):
                raise HTTPException(409, "Locations are closed for this drive")
            offsets = [p.offset_ms for p in batch.samples]
            if len(offsets) != len(set(offsets)):
                raise HTTPException(409, "Duplicate offset in batch")
            existing = {p.offset_ms: p for p in db.scalars(select(Location).where(Location.drive_id == drive.id, Location.offset_ms.in_(offsets)))}
            for p in batch.samples:
                payload = p.model_dump()
                payload["recorded_at"] = p.recorded_at.isoformat().replace("+00:00", "Z")
                old = existing.get(p.offset_ms)
                if old:
                    if any(getattr(old, key) != value for key, value in payload.items()):
                        raise HTTPException(409, "Conflicting sample at offset")
                else:
                    db.add(Location(id=str(uuid.uuid4()), drive_id=drive.id, **payload))
                    accepted += 1
        return {"accepted": accepted}

    @app.post("/v1/drives/{drive_id}/complete")
    def complete(drive_id: uuid.UUID, payload: CompleteRequest, owner: Owner):
        with config.Session.begin() as db:
            drive = owned(db, Drive, drive_id, owner)
            if drive.status in ("queued", "processing", "complete"):
                if payload.video_started_at is not None and drive.video_started_at != payload.video_started_at.isoformat().replace("+00:00", "Z"):
                    raise HTTPException(409, "First-frame time cannot change after completing")
                return {"drive_id": drive.id, "status": drive.status}
            if drive.status == "failed":
                raise HTTPException(409, "Use /retry for failed drives")
            if not drive.video_key or not config.store.exists(drive.video_key):
                raise HTTPException(409, "Upload MP4 before completing")
            frozen = db.execute(update(Drive).where(
                Drive.id == drive.id, Drive.owner == owner, Drive.status.in_(("created", "uploading")),
                Drive.video_key == drive.video_key,
            ).values(video_started_at=payload.video_started_at.isoformat().replace("+00:00", "Z") if payload.video_started_at else None,
                     status="queued", stage="queued"))
            if frozen.rowcount != 1:
                raise HTTPException(409, "Video changed; retry completion")
            db.add(Job(id=str(uuid.uuid4()), drive_id=drive.id, state="pending", attempts=0))
            return {"drive_id": drive.id, "status": drive.status}

    @app.post("/v1/drives/{drive_id}/retry")
    def retry(drive_id: uuid.UUID, owner: Owner):
        with config.Session.begin() as db:
            drive = owned(db, Drive, drive_id, owner)
            if drive.status != "failed":
                raise HTTPException(409, "Only failed drives can be retried")
            job = db.scalar(select(Job).where(Job.drive_id == drive.id))
            job.state = "pending"
            job.lease_until = None
            job.error = None
            drive.status = "queued"
            drive.stage = "queued"
            drive.error = None
        return {"drive_id": str(drive_id), "status": "queued"}

    @app.get("/v1/drives/{drive_id}")
    def get_drive(drive_id: uuid.UUID, owner: Owner):
        with config.Session() as db:
            drive = owned(db, Drive, drive_id, owner)
            hazards = list(db.scalars(select(Hazard).where(Hazard.drive_id == drive.id).order_by(Hazard.video_offset_ms)))
            return {"drive_id": drive.id, "status": drive.status, "stage": drive.stage, "error": drive.error,
                    "analysis_mode": drive.analysis_mode, "hazards": [
                {"hazard_id": h.id, "category": h.category, "confidence": h.confidence, "severity": h.severity, "severity_basis": h.severity_basis,
                 "evidence_url": f"/v1/hazards/{h.id}/evidence", "video_offset_ms": h.video_offset_ms,
                 "observed_at": h.observed_at, "location": h.location, "review_state": h.review_state}
                for h in hazards]}

    @app.get("/v1/hazards/{hazard_id}/evidence")
    def get_evidence(hazard_id: uuid.UUID, owner: Owner):
        with config.Session() as db:
            hazard = owned(db, Hazard, hazard_id, owner)
            evidence = db.scalar(select(Evidence).where(Evidence.hazard_id == hazard.id))
            if not evidence:
                raise HTTPException(404, "No evidence")
            if not config.store.exists(evidence.storage_key):
                raise HTTPException(404, "No evidence")
            return BytesResponse(config.store.read_bytes(evidence.storage_key), media_type="image/jpeg")

    @app.post("/v1/hazards/{hazard_id}/report-draft")
    def report_draft(hazard_id: uuid.UUID, owner: Owner):
        with config.Session.begin() as db:
            hazard = owned(db, Hazard, hazard_id, owner)
            draft = db.scalar(select(ReportDraft).where(ReportDraft.hazard_id == hazard.id))
            if not draft:
                location = hazard.location or {}
                fields = {"category": hazard.category, "description": f"{hazard.category.capitalize()} observed in drive video; review evidence and approximate phone location before reporting.", "latitude": location.get("latitude"), "longitude": location.get("longitude"), "observation_time": {"value": hazard.observed_at, "source": "device_clock" if hazard.observed_at else "unassessed"}}
                destination = {"status": "unverified", "url": None}
                if config.reporter:
                    from .worker import load_callable
                    package = load_callable(config.reporter)(dict(fields=fields, hazard_id=hazard.id,
                        event_id=f"event-{hazard.event_index + 1:03d}", category=hazard.category,
                        confidence=hazard.confidence, review_state=hazard.review_state,
                        observed_at=hazard.observed_at,
                        evidence_url=f"/v1/hazards/{hazard.id}/evidence", location=hazard.location))
                    fields = package["fields"]
                    destination = package["destination"]
                    if destination.get("status") not in ("unverified", "unknown", "verified", "needs_review", "unsupported"):
                        raise HTTPException(422, "Invalid report destination")
                draft = ReportDraft(id=str(uuid.uuid4()), hazard_id=hazard.id, fields=fields, destination=destination, submission_status="not_submitted")
                db.add(draft)
            elif all(isinstance(draft.fields.get(key), dict) and "value" in draft.fields[key]
                     for key in ("category", "description", "coordinates", "observation_time")):
                # Repair the old adapter's persisted shape on fetch, without replacing
                # the report ID, destination, submission state, or already-flat edits.
                from .integration import flatten_report_fields
                draft.fields = flatten_report_fields(draft.fields)
            return {"report_id": draft.id, "fields": draft.fields, "destination": draft.destination, "submission_status": draft.submission_status}

    return app


# uvicorn imports this; explicit secret required at startup.
class LazyApp:
    def __init__(self):
        self.app = None

    async def __call__(self, scope, receive, send):
        if self.app is None:
            self.app = create_app()
        await self.app(scope, receive, send)


app = LazyApp()
