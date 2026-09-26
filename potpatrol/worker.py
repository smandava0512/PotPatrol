import argparse
import importlib
import json
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import or_, select, update

from .db import Drive, Evidence, Hazard, Job, Location


def load_callable(spec):
    module, sep, function = spec.partition(":")
    if not sep or not module or not function:
        raise ValueError("Expected module:function")
    return getattr(importlib.import_module(module), function)


def match_location(samples, offset):
    """Approximate phone location only; never a surveyed road-hazard coordinate."""
    before = next((p for p in reversed(samples) if p.offset_ms <= offset), None)
    after = next((p for p in samples if p.offset_ms >= offset), None)
    if not before or not after:
        near = before or after
        if near and abs(near.offset_ms - offset) <= 1000 and near.horizontal_accuracy_m is not None and near.horizontal_accuracy_m <= 50:
            return {"latitude": near.latitude, "longitude": near.longitude, "horizontal_accuracy_m": near.horizontal_accuracy_m, "source": "phone_sample"}
        return None
    if before.horizontal_accuracy_m is None or after.horizontal_accuracy_m is None or max(before.horizontal_accuracy_m, after.horizontal_accuracy_m) > 50 or after.offset_ms - before.offset_ms > 5000:
        return None
    fraction = (offset - before.offset_ms) / (after.offset_ms - before.offset_ms) if before.offset_ms != after.offset_ms else 0
    return {"latitude": before.latitude + fraction * (after.latitude - before.latitude), "longitude": before.longitude + fraction * (after.longitude - before.longitude), "horizontal_accuracy_m": max(before.horizontal_accuracy_m, after.horizontal_accuracy_m), "source": "phone_sample" if before.offset_ms == after.offset_ms else "phone_interpolated"}


def validate_manifest(manifest, output_dir):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or not isinstance(manifest.get("events"), list) or len(manifest["events"]) > 100:
        raise ValueError("Invalid worker schema/version or too many events")
    checked = []
    for event in manifest["events"]:
        if not isinstance(event, dict) or not isinstance(event.get("video_offset_ms"), int) or isinstance(event["video_offset_ms"], bool) or not 0 <= event["video_offset_ms"] <= 600000:
            raise ValueError("Invalid event offset")
        if not isinstance(event.get("category"), str) or not 1 <= len(event["category"]) <= 80:
            raise ValueError("Invalid event category")
        confidence = event.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise ValueError("Invalid event confidence")
        name = event.get("evidence_path")
        if not isinstance(name, str) or Path(name).is_absolute() or ":" in name or ".." in Path(name).parts:
            raise ValueError("Unsafe evidence path")
        path = (Path(output_dir) / name).resolve()
        if not path.is_relative_to(Path(output_dir).resolve()) or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024 or path.read_bytes()[:3] != b"\xff\xd8\xff":
            raise ValueError("Missing/invalid JPEG evidence")
        first, last = event.get("first_seen_ms"), event.get("last_seen_ms")
        if (first is not None and (not isinstance(first, int) or first < 0 or first > event["video_offset_ms"])) or (last is not None and (not isinstance(last, int) or last < event["video_offset_ms"] or last > 600000)):
            raise ValueError("Invalid event interval")
        checked.append((event, path))
    return checked


def process_once(config):
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lease = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    with config.Session.begin() as db:
        candidate = db.scalar(select(Job).where(or_(Job.state == "pending", (Job.state == "processing") & (Job.lease_until < now))).order_by(Job.id).limit(1))
        if candidate is None:
            return False
        claimed = db.execute(update(Job).where(Job.id == candidate.id, Job.state == candidate.state, Job.lease_until == candidate.lease_until).values(state="processing", lease_until=lease, started_at=now, attempts=Job.attempts + 1))
        if not claimed.rowcount:
            return False
        drive_id = candidate.drive_id
        drive = db.get(Drive, drive_id)
        drive.status = "processing"
        drive.stage = "analyzing"
        drive.error = None
    try:
        with config.Session() as db:
            drive = db.get(Drive, drive_id)
            if not drive.video_key or not config.store.exists(drive.video_key):
                raise ValueError("Missing stored video")
            video_key = drive.video_key
            samples = list(db.scalars(select(Location).where(Location.drive_id == drive_id).order_by(Location.offset_ms)))
        with tempfile.TemporaryDirectory(prefix="potpatrol-", dir=config.storage_dir) as workspace:
            video = Path(workspace) / "drive.mp4"
            config.store.download_file(video_key, video)
            result = load_callable(config.analyzer)(str(video), str(workspace))
            manifest_path = Path(result).resolve()
            if manifest_path != (Path(workspace) / "analysis.json").resolve():
                raise ValueError("Worker must return output_dir/analysis.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            events = validate_manifest(manifest, workspace)
            evidence_dir = config.storage_dir / "evidence" / drive_id
            evidence_dir.mkdir(parents=True, exist_ok=True)
            with config.Session.begin() as db:
                drive = db.get(Drive, drive_id)
                if drive.status != "processing":
                    raise ValueError("Job no longer owned by worker")
                for index, (event, jpeg) in enumerate(events):
                    hazard = db.scalar(select(Hazard).where(Hazard.drive_id == drive_id, Hazard.event_index == index))
                    if not hazard:
                        hazard = Hazard(id=str(uuid.uuid4()), drive_id=drive_id, event_index=index)
                        db.add(hazard)
                    hazard.category = event["category"]
                    hazard.confidence = event["confidence"]
                    hazard.video_offset_ms = event["video_offset_ms"]
                    hazard.severity = None
                    hazard.severity_basis = None
                    hazard.location = match_location(samples, event["video_offset_ms"])
                    hazard.review_state = "needs_review"
                    key = f"evidence/{drive_id}/{index}.jpg"
                    config.store.put_file(key, jpeg, "image/jpeg")
                    evidence = db.scalar(select(Evidence).where(Evidence.hazard_id == hazard.id))
                    if not evidence:
                        db.add(Evidence(id=str(uuid.uuid4()), hazard_id=hazard.id, storage_key=key, content_type="image/jpeg"))
                # No stale hazards after a retry with fewer events.
                for old in db.scalars(select(Hazard).where(Hazard.drive_id == drive_id, Hazard.event_index >= len(events))):
                    raise ValueError("Worker changed event count on retry; manual review required")
                drive.status = "complete"
                drive.stage = "complete"
                job = db.scalar(select(Job).where(Job.drive_id == drive_id))
                job.state = "done"
                job.lease_until = None
                job.finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return True
    except Exception as exc:
        with config.Session.begin() as db:
            drive = db.get(Drive, drive_id)
            job = db.scalar(select(Job).where(Job.drive_id == drive_id))
            drive.status = "failed"
            drive.stage = "failed"
            drive.error = str(exc)[:500]
            job.state = "failed"
            job.error = str(exc)[:500]
            job.lease_until = None
            job.finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return True


def main():
    from .api import Config
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    if not (args.once or args.loop):
        parser.error("Select --once or --loop")
    config = Config()
    if args.once:
        print("Processed one job" if process_once(config) else "No pending jobs")
    else:
        while True:
            if not process_once(config):
                time.sleep(2)


if __name__ == "__main__":
    main()
