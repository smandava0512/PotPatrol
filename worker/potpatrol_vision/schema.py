"""Manifest schema v1 constants and validation. See docs/contracts/analysis.md."""
from __future__ import annotations

import os

SCHEMA_VERSION = 1
CATEGORIES = ("pothole", "road_damage")
STATUSES = ("confirmed", "needs_review")
MODES = ("model", "fixture")
MAX_EVENTS = 25


class AnalysisError(Exception):
    """Base worker failure. CLI exit code 1."""

    error_type = "internal_error"
    exit_code = 1


class InvalidVideoError(AnalysisError):
    error_type = "invalid_video"
    exit_code = 2


class ModelError(AnalysisError):
    error_type = "model_error"
    exit_code = 3


def validate_manifest(manifest: dict, output_dir: str | None = None) -> None:
    """Raise ValueError if the manifest violates the v1 contract.

    When output_dir is given, also checks that evidence files exist.
    """
    def fail(msg: str):
        raise ValueError(f"invalid manifest: {msg}")

    if manifest.get("schema_version") != SCHEMA_VERSION:
        fail("schema_version must be 1")
    if manifest.get("mode") not in MODES:
        fail(f"mode must be one of {MODES}")
    events = manifest.get("events")
    if not isinstance(events, list):
        fail("events must be a list")
    if len(events) > MAX_EVENTS:
        fail(f"more than {MAX_EVENTS} events")
    prev = -1
    for ev in events:
        eid = ev.get("event_id", "?")
        for k in ("video_offset_ms", "first_seen_ms", "last_seen_ms", "hits"):
            if not isinstance(ev.get(k), int) or ev[k] < 0:
                fail(f"{eid}.{k} must be a non-negative int")
        if not ev["first_seen_ms"] <= ev["video_offset_ms"] <= ev["last_seen_ms"]:
            fail(f"{eid}: first_seen_ms <= video_offset_ms <= last_seen_ms violated")
        if ev["video_offset_ms"] < prev:
            fail("events must be sorted by video_offset_ms")
        prev = ev["video_offset_ms"]
        if ev.get("category") not in CATEGORIES:
            fail(f"{eid}.category {ev.get('category')!r} not in {CATEGORIES}")
        if ev.get("status") not in STATUSES:
            fail(f"{eid}.status not in {STATUSES}")
        c = ev.get("confidence")
        if not isinstance(c, (int, float)) or not 0.0 <= c <= 1.0:
            fail(f"{eid}.confidence must be in [0,1]")
        bbox = ev.get("bbox")
        if (not isinstance(bbox, list) or len(bbox) != 4
                or not all(0.0 <= v <= 1.0 for v in bbox)
                or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]):
            fail(f"{eid}.bbox must be normalized [x1,y1,x2,y2]")
        for k in ("evidence_path", "evidence_raw_path"):
            p = ev.get(k)
            if not isinstance(p, str) or os.path.isabs(p) or ".." in p.replace("\\", "/").split("/"):
                fail(f"{eid}.{k} must be a relative path inside output_dir")
            if output_dir and not os.path.isfile(os.path.join(output_dir, p)):
                fail(f"{eid}.{k} missing on disk: {p}")
        if not isinstance(ev.get("notes"), str):
            fail(f"{eid}.notes must be a string")


def env(name: str, default: str = "") -> str:
    """Read POTPATROL_<name>, falling back to the pre-rename ROADWATCH_<name> (remove once Dev 2 migrates)."""
    return os.environ.get(f"POTPATROL_{name}", os.environ.get(f"ROADWATCH_{name}", default))
