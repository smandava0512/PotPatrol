"""Bounded, fail-closed Gemini-assisted scan of a drive (never uploads its video)."""
from __future__ import annotations

import math
import os
import random

import numpy as np

from .events import iou
from .schema import AnalysisError, MAX_EVENTS

SCAN_LIMIT = 24
CANDIDATE_LIMIT = 12


def _moving_match(previous, current) -> bool:
    """Conservative forward-camera association; adjacent boxes alone are not identity."""
    px = (previous[0] + previous[2]) / 2
    cx = (current[0] + current[2]) / 2
    py = (previous[1] + previous[3]) / 2
    cy = (current[1] + current[3]) / 2
    old_area = (previous[2] - previous[0]) * (previous[3] - previous[1])
    new_area = (current[2] - current[0]) * (current[3] - current[1])
    return (abs(px - cx) <= 0.08 and 0 <= cy - py <= 0.22
            and 0.8 * old_area <= new_area <= 2.5 * old_area
            and iou(previous, current) > 0)


def _matches_validated_yolo(event, box, offset: int, category: str) -> bool:
    """Match a scanned object to a confirmed candidate on either side of its evidence frame."""
    if event["category"] != category:
        return False
    gap = offset - event["video_offset_ms"]
    if 0 < gap <= 5000:
        return _moving_match(event["bbox"], box)
    if -5000 <= gap < 0:
        return _moving_match(box, event["bbox"])
    return False


class FrameSelector:
    """Uniform streaming reservoir: bounded JPEG memory, first/last frame retained."""

    def __init__(self):
        self._first: tuple[int, bytes] | None = None
        self._last: tuple[int, bytes] | None = None
        self._middle: list[tuple[int, bytes]] = []
        self._rng = random.Random(0)  # stable sampling for reproducible analysis
        self.count = 0

    @property
    def frames(self) -> list[tuple[int, bytes]]:
        return sorted([*([self._first] if self._first else []), *self._middle,
                       *([self._last] if self._last else [])], key=lambda frame: frame[0])

    def add(self, offset_ms: int, image: np.ndarray) -> None:
        import cv2

        self.count += 1
        # The previous tail joins the interior reservoir; it may be displaced later.
        if self._last is not None:
            interior_count = self.count - 2
            if len(self._middle) < SCAN_LIMIT - 2:
                self._middle.append(self._last)
            else:
                index = self._rng.randrange(interior_count)
                if index < len(self._middle):
                    self._middle[index] = self._last
        h, w = image.shape[:2]
        if max(h, w) > 1024:
            image = cv2.resize(image, (round(w * 1024 / max(h, w)), round(h * 1024 / max(h, w))))
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            raise AnalysisError("Gemini frame JPEG encoding failed")
        frame = (offset_ms, buf.tobytes())
        if self._first is None:
            self._first = frame
        else:
            self._last = frame


def _valid_box(box) -> bool:
    return (isinstance(box, list) and len(box) == 4
            and all(type(v) in (float, int) and math.isfinite(v) and 0 <= v <= 1 for v in box)
            and box[0] < box[2] and box[1] < box[3]
            and (box[1] + box[3]) / 2 >= 0.30)


def _valid_score(value) -> bool:
    return type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 1


def reconcile(events: list[dict], selected: FrameSelector, output_dir: str, validator) -> list[dict]:
    """Validate all YOLO events, scan independent samples, fail on any incomplete provider response."""
    import cv2
    from .pipeline import _write_evidence

    if len(events) > CANDIDATE_LIMIT:
        raise AnalysisError("Gemini required: too many YOLO candidates for bounded validation")
    description = validator.describe()
    if not isinstance(description, dict) or description.get("provider") != "gemini" or not description.get("model"):
        raise AnalysisError("Gemini required: validator unavailable")
    accepted = []
    for ev in events:
        try:
            result = validator.validate(os.path.join(output_dir, ev["evidence_raw_path"]), ev["category"])
        except Exception as e:
            raise AnalysisError(f"Gemini candidate validation failed ({type(e).__name__})") from e
        if (not isinstance(result, dict) or type(result.get("is_hazard")) is not bool
                or not _valid_score(result.get("confidence"))
                or result.get("provider") != "gemini" or result.get("model") != description["model"]):
            raise AnalysisError("Gemini candidate validation failed or returned invalid data")
        if result["is_hazard"]:
            ev["status"] = "needs_review"  # machine agreement is not human confirmation
            ev["source"] = "yolo_gemini_validated"
            ev["validation"] = result
            accepted.append(ev)

    scan_dir = os.path.join(output_dir, ".gemini-scan")
    scan_tracks: list[tuple[dict, list, int]] = []  # accepted scan event, latest box, latest offset
    os.makedirs(scan_dir, exist_ok=True)
    try:
        for index, (offset, jpeg) in enumerate(selected.frames):
            matched_in_frame: set[str] = set()
            path = os.path.join(scan_dir, f"frame-{index:03d}.jpg")
            with open(path, "wb") as f:
                f.write(jpeg)
            try:
                findings = validator.scan(path)
            except Exception as e:
                raise AnalysisError(f"Gemini frame scan failed ({type(e).__name__})") from e
            finally:
                os.remove(path)
            if not isinstance(findings, list) or len(findings) > 5:
                raise AnalysisError("Gemini frame scan failed or returned invalid data")
            for finding in findings:
                if (not isinstance(finding, dict) or finding.get("category") not in ("pothole", "road_damage")
                        or not _valid_box(finding.get("bbox"))
                        or not _valid_score(finding.get("confidence"))):
                    raise AnalysisError("Gemini frame scan failed or returned invalid box")
                box = finding["bbox"]
                if any(ev["first_seen_ms"] - 1500 <= offset <= ev["last_seen_ms"] + 1500
                       and iou(ev["bbox"], box) >= 0.5 for ev in events + accepted):
                    continue  # duplicate localization, not merely a nearby hazard
                if any(_matches_validated_yolo(ev, box, offset, finding["category"])
                       for ev in accepted if ev["source"] == "yolo_gemini_validated"):
                    continue  # account for a moving candidate beyond its original YOLO box
                match = next((n for n, (ev, last_box, last_offset) in enumerate(scan_tracks)
                              if ev["event_id"] not in matched_in_frame
                              and ev["category"] == finding["category"]
                              and 0 < offset - last_offset <= 5000
                              and _moving_match(last_box, box)), None)
                if match is not None:
                    ev, _, _ = scan_tracks[match]
                    ev["last_seen_ms"] = offset
                    ev["hits"] += 1
                    ev["notes"] = "Possible road surface damage in multiple Gemini-scanned frames; review required"
                    scan_tracks[match] = (ev, box, offset)
                    matched_in_frame.add(ev["event_id"])
                    continue
                image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    raise AnalysisError("Gemini evidence JPEG decoding failed")
                event_id = f"event-{len(events) + len(accepted) + 1:03d}"
                ann, raw = _write_evidence(output_dir, event_id, image, box, "possible road damage")
                accepted.append({"event_id": event_id, "video_offset_ms": offset,
                                 "first_seen_ms": offset, "last_seen_ms": offset,
                                 "category": finding["category"], "confidence": round(finding["confidence"], 3),
                                 "status": "needs_review", "hits": 1,
                                 "bbox": [round(v, 4) for v in box],
                                 "evidence_path": ann, "evidence_raw_path": raw,
                                 "notes": "Possible road surface damage in one Gemini-scanned frame; review required",
                                 "source": "gemini_scan"})
                scan_tracks.append((accepted[-1], box, offset))
                matched_in_frame.add(event_id)
                if len(accepted) > MAX_EVENTS:
                    raise AnalysisError("Gemini required: more hazards than manifest limit")
    finally:
        os.rmdir(scan_dir)
    accepted.sort(key=lambda ev: ev["video_offset_ms"])
    return accepted
