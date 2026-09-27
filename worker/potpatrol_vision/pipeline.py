"""analyze(video_path, output_dir) -> manifest dict (and output_dir/analysis.json).

CLI: python -m potpatrol_vision VIDEO OUTPUT_DIR [--fixture] [--sample-fps N] [--conf X] [--device D]
Contract: docs/contracts/analysis.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict

import numpy as np

from .events import MergeParams, EventMerger, Track
from .frames import VideoInfo, sample_frames
from .schema import SCHEMA_VERSION, AnalysisError, InvalidVideoError, env, validate_manifest
from .validators import get_validator, get_required_validator, max_validations

DEFAULT_SAMPLE_FPS = 4.0
DEFAULT_CONF = 0.35
BATCH = 8
_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "analysis.fixture.json")


def _region(box) -> str:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    h = "left" if cx < 0.4 else "right" if cx > 0.6 else "center"
    v = "lower" if cy > 0.66 else "middle"
    return f"{v}-{h}" if h != "center" else f"{v}-center"


def _write_evidence(output_dir: str, event_id: str, image: np.ndarray, box, label: str) -> tuple[str, str]:
    import cv2

    ev_dir = os.path.join(output_dir, "evidence")
    os.makedirs(ev_dir, exist_ok=True)
    raw_rel = f"evidence/{event_id}-raw.jpg"
    ann_rel = f"evidence/{event_id}.jpg"
    h, w = image.shape[:2]
    if not cv2.imwrite(os.path.join(output_dir, raw_rel), image, [cv2.IMWRITE_JPEG_QUALITY, 90]):
        raise AnalysisError(f"failed to write {raw_rel}")
    ann = image.copy()
    p1 = (int(box[0] * w), int(box[1] * h))
    p2 = (int(box[2] * w), int(box[3] * h))
    thick = max(2, w // 400)
    cv2.rectangle(ann, p1, p2, (0, 0, 255), thick)
    scale = max(0.6, w / 1600)
    ty = max(p1[1] - 8, int(24 * scale))
    cv2.putText(ann, label, (p1[0], ty), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(ann, label, (p1[0], ty), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thick, cv2.LINE_AA)
    if not cv2.imwrite(os.path.join(output_dir, ann_rel), ann, [cv2.IMWRITE_JPEG_QUALITY, 90]):
        raise AnalysisError(f"failed to write {ann_rel}")
    return ann_rel, raw_rel


def _event_dict(idx: int, tr: Track, output_dir: str, min_hits: int) -> dict:
    event_id = f"event-{idx:03d}"
    status = "confirmed" if tr.hits >= min_hits else "needs_review"
    ann, raw = _write_evidence(output_dir, event_id, tr.best_image, tr.best_box,
                               f"{tr.category} {tr.best_conf:.2f}")
    span_s = (tr.last_ms - tr.first_ms) / 1000.0
    notes = (f"Detected in {tr.hits} sampled frame{'s' if tr.hits != 1 else ''}"
             + (f" over {span_s:.1f} s" if tr.hits > 1 else "")
             + f"; box in {_region(tr.best_box)} of frame")
    return {
        "event_id": event_id,
        "video_offset_ms": int(tr.best_ms),
        "first_seen_ms": int(tr.first_ms),
        "last_seen_ms": int(tr.last_ms),
        "category": tr.category,
        "confidence": round(float(tr.max_conf), 3),
        "status": status,
        "hits": int(tr.hits),
        "bbox": [round(float(v), 4) for v in tr.best_box],
        "evidence_path": ann,
        "evidence_raw_path": raw,
        "notes": notes,
    }


def _validate_events(events: list[dict], output_dir: str, validator) -> None:
    """Attach an optional `validation` to the highest-confidence events. Never drops or re-labels events."""
    for ev in sorted(events, key=lambda e: e["confidence"], reverse=True)[:max_validations()]:
        result = validator.validate(os.path.join(output_dir, ev["evidence_raw_path"]), ev["category"])
        if result is not None:
            ev["validation"] = result


def _write_manifest(output_dir: str, manifest: dict) -> dict:
    validate_manifest(manifest, output_dir)
    tmp = os.path.join(output_dir, "analysis.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    os.replace(tmp, os.path.join(output_dir, "analysis.json"))  # atomic: never a half-written manifest
    return manifest


def analyze_fixture(output_dir: str) -> dict:
    """Deterministic sample result for integration and demo fallback."""
    import shutil

    os.makedirs(os.path.join(output_dir, "evidence"), exist_ok=True)
    with open(_FIXTURE, encoding="utf-8") as f:
        manifest = json.load(f)
    src_dir = os.path.dirname(_FIXTURE)
    for ev in manifest["events"]:
        for k in ("evidence_path", "evidence_raw_path"):
            shutil.copyfile(os.path.join(src_dir, ev[k]), os.path.join(output_dir, ev[k]))
    return _write_manifest(output_dir, manifest)


def analyze(video_path: str, output_dir: str, *, fixture: bool | None = None,
            sample_fps: float = DEFAULT_SAMPLE_FPS, conf: float = DEFAULT_CONF,
            device: str | None = None, params: MergeParams | None = None, detector=None,
            validator=None) -> dict:
    """Analyze one drive clip. Raises InvalidVideoError / ModelError / AnalysisError on failure."""
    required = env("VISION_MODE").lower() == "gemini_required"
    os.makedirs(output_dir, exist_ok=True)
    stale = os.path.join(output_dir, "analysis.json")
    if os.path.exists(stale):  # a failed rerun must not expose an old success
        os.remove(stale)
    if required and (fixture is True or env("ANALYSIS_MODE").lower() == "fixture"):
        raise AnalysisError("Gemini required mode refuses fixture analysis")
    if fixture is None:
        fixture = env("ANALYSIS_MODE").lower() == "fixture"
    if required:
        validator = validator if validator is not None else get_required_validator()
        from .required import FrameSelector
        selected = FrameSelector()
    else:
        selected = None
    if fixture:
        return analyze_fixture(output_dir)
    if not os.path.isfile(video_path):
        raise InvalidVideoError(f"video not found: {video_path!r}")

    t0 = time.perf_counter()
    if detector is None:
        from .detector import PotholeDetector

        detector = PotholeDetector(conf_threshold=conf, device=device)
    params = params or MergeParams()
    merger = EventMerger(params)
    info = VideoInfo()

    batch_t: list[int] = []
    batch_img: list[np.ndarray] = []

    def flush():
        for t, img, dets in zip(batch_t, batch_img, detector.detect(batch_img)):
            merger.add_frame(t, img, dets)
        batch_t.clear()
        batch_img.clear()

    for t_ms, img in sample_frames(video_path, sample_fps, info):
        if selected is not None:
            selected.add(t_ms, img)
        batch_t.append(t_ms)
        batch_img.append(img)
        if len(batch_img) >= BATCH:
            flush()
    if batch_img:
        flush()

    tracks = merger.finish()
    events = [_event_dict(i + 1, tr, output_dir, params.min_hits) for i, tr in enumerate(tracks)]
    if required:
        from .required import reconcile
        events = reconcile(events, selected, output_dir, validator)
    else:
        validator = validator if validator is not None else get_validator()
        if events and validator.describe():
            _validate_events(events, output_dir, validator)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "mode": "model",
        **({"vision_mode": "gemini_required", "gemini_frames_scanned": len(selected.frames)} if required else {}),
        "video": {
            "duration_ms": info.duration_ms,
            "frames_decoded": info.frames_decoded,
            "frames_sampled": info.frames_sampled,
            "sample_fps": info.sample_fps,
            "rotation_deg": info.rotation_deg,
            "width": info.width,
            "height": info.height,
            **info.extra,
        },
        "model": detector.describe(),
        "merge_params": asdict(params),
        "validator": validator.describe(),
        "filtered_detections": merger.dropped_filtered,
        "processing_ms": int((time.perf_counter() - t0) * 1000),
        "events": events,
    }
    return _write_manifest(output_dir, manifest)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PotPatrol pothole analysis worker (schema v1)")
    ap.add_argument("video_path")
    ap.add_argument("output_dir")
    ap.add_argument("--fixture", action="store_true", default=None, help="return the deterministic sample result")
    ap.add_argument("--sample-fps", type=float, default=DEFAULT_SAMPLE_FPS)
    ap.add_argument("--conf", type=float, default=DEFAULT_CONF)
    ap.add_argument("--device", default=None, help="'cpu', '0' (GPU), default auto")
    a = ap.parse_args(argv)
    try:
        m = analyze(a.video_path, a.output_dir, fixture=a.fixture, sample_fps=a.sample_fps,
                    conf=a.conf, device=a.device)
    except AnalysisError as e:
        print(json.dumps({"schema_version": SCHEMA_VERSION,
                          "error": {"type": e.error_type, "message": str(e)}}), file=sys.stderr)
        return e.exit_code
    except Exception as e:  # noqa: BLE001 - anything unexpected is a crash, never "0 hazards"
        print(json.dumps({"schema_version": SCHEMA_VERSION,
                          "error": {"type": "internal_error", "message": f"{type(e).__name__}: {e}"}}),
              file=sys.stderr)
        return 1
    print(json.dumps({"events": len(m["events"]), "mode": m["mode"],
                      "processing_ms": m.get("processing_ms"),
                      "manifest": os.path.join(a.output_dir, "analysis.json")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
