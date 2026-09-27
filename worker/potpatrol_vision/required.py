"""Bounded, fail-closed Gemini-assisted scan of a drive (never uploads its video)."""
from __future__ import annotations

import math
import os

import numpy as np

from .events import center_dist
from .schema import AnalysisError, MAX_EVENTS

SCAN_LIMIT = 24
CANDIDATE_LIMIT = 12


class FrameSelector:
    """Keep evenly spaced JPEGs with a bounded in-memory footprint in one decode pass."""

    def __init__(self):
        self.frames: list[tuple[int, bytes]] = []
        self.stride = 1
        self.count = 0

    def add(self, offset_ms: int, image: np.ndarray) -> None:
        import cv2

        index = self.count
        self.count += 1
        if index % self.stride:
            return
        h, w = image.shape[:2]
        if max(h, w) > 1024:
            image = cv2.resize(image, (round(w * 1024 / max(h, w)), round(h * 1024 / max(h, w))))
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            raise AnalysisError("Gemini frame JPEG encoding failed")
        self.frames.append((offset_ms, buf.tobytes()))
        if len(self.frames) > SCAN_LIMIT:
            self.stride *= 2
            self.frames = [frame for n, frame in enumerate(self.frames) if n % 2 == 0]


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
    os.makedirs(scan_dir, exist_ok=True)
    try:
        for index, (offset, jpeg) in enumerate(selected.frames):
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
                       and center_dist(ev["bbox"], box) < 0.2 for ev in events + accepted):
                    continue  # never resurrect a rejected YOLO curb; avoid duplicate valid events
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
                if len(accepted) > MAX_EVENTS:
                    raise AnalysisError("Gemini required: more hazards than manifest limit")
    finally:
        os.rmdir(scan_dir)
    accepted.sort(key=lambda ev: ev["video_offset_ms"])
    return accepted
