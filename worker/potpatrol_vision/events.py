"""Turn per-frame detections into one event per physical hazard.

A forward-facing camera sees the same pothole in consecutive frames while it slides down the image and
grows, so matching uses time gap + (box IoU OR nearby center) rather than strict IoU.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .detector import Detection


@dataclass(frozen=True)
class MergeParams:
    max_gap_ms: int = 1000          # a track ends if unseen for this long
    min_iou: float = 0.05           # match if IoU >= this ...
    max_center_dist: float = 0.25   # ... or centers within this (normalized units)
    min_hits: int = 2               # frames needed for status=confirmed
    single_hit_conf: float = 0.60   # a 1-frame track is kept as needs_review only above this
    min_box_area: float = 0.0008    # ignore specks (fraction of frame area)
    min_center_y: float = 0.30      # ignore boxes centered in the top 30% (sky, cars, signs)
    dedupe_window_ms: int = 1500    # merge finished tracks this close in time with overlapping x-range
    max_events: int = 25


@dataclass
class Track:
    category: str
    first_ms: int
    last_ms: int
    last_box: tuple[float, float, float, float]
    hits: int = 0
    max_conf: float = 0.0
    best_score: float = -1.0
    best_ms: int = 0
    best_box: tuple[float, float, float, float] = (0, 0, 0, 0)
    best_conf: float = 0.0
    best_image: np.ndarray | None = field(default=None, repr=False)

    def add(self, t_ms: int, det: Detection, image: np.ndarray, score: float):
        self.hits += 1
        self.last_ms = t_ms
        self.last_box = det.bbox
        self.max_conf = max(self.max_conf, det.confidence)
        if score > self.best_score:
            self.best_score, self.best_ms, self.best_box = score, t_ms, det.bbox
            self.best_conf, self.best_image = det.confidence, image


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def center_dist(a, b) -> float:
    ax, ay = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bx, by = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return float(np.hypot(ax - bx, ay - by))


def sharpness(image: np.ndarray, box) -> float:
    """Laplacian variance of the box crop, a cheap motion-blur proxy."""
    import cv2

    h, w = image.shape[:2]
    x1, y1, x2, y2 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    crop = image[max(0, y1):max(y1 + 1, y2), max(0, x1):max(x1 + 1, x2)]
    if crop.size == 0:
        return 0.0
    return float(cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def frame_score(det: Detection, image: np.ndarray) -> float:
    # Confidence dominates; sharpness breaks near-ties toward a clearer evidence frame.
    sharp = min(1.0, sharpness(image, det.bbox) / 300.0)
    return det.confidence * (0.8 + 0.2 * sharp)


class EventMerger:
    def __init__(self, params: MergeParams | None = None):
        self.p = params or MergeParams()
        self.active: list[Track] = []
        self.done: list[Track] = []
        self.dropped_filtered = 0

    def _keep(self, det: Detection) -> bool:
        x1, y1, x2, y2 = det.bbox
        ok = (x2 - x1) * (y2 - y1) >= self.p.min_box_area and (y1 + y2) / 2 >= self.p.min_center_y
        if not ok:
            self.dropped_filtered += 1
        return ok

    def add_frame(self, t_ms: int, image: np.ndarray, dets: list[Detection]):
        # Retire stale tracks.
        still = []
        for tr in self.active:
            (still if t_ms - tr.last_ms <= self.p.max_gap_ms else self.done).append(tr)
        self.active = still

        dets = sorted((d for d in dets if self._keep(d)), key=lambda d: -d.confidence)
        used: set[int] = set()
        for det in dets:
            best_i, best_key = None, None
            for i, tr in enumerate(self.active):
                if i in used or tr.category != det.category:
                    continue
                o, cd = iou(tr.last_box, det.bbox), center_dist(tr.last_box, det.bbox)
                if o >= self.p.min_iou or cd <= self.p.max_center_dist:
                    key = (o, -cd)
                    if best_key is None or key > best_key:
                        best_i, best_key = i, key
            score = frame_score(det, image)
            if best_i is None:
                tr = Track(det.category, t_ms, t_ms, det.bbox)
                tr.add(t_ms, det, image, score)
                self.active.append(tr)
                used.add(len(self.active) - 1)
            else:
                self.active[best_i].add(t_ms, det, image, score)
                used.add(best_i)

    def finish(self) -> list[Track]:
        tracks = sorted(self.done + self.active, key=lambda t: t.first_ms)
        self.active, self.done = [], []
        # Second pass: fuse tracks that broke on a missed frame / box jump for the same obstacle.
        merged: list[Track] = []
        for tr in tracks:
            prev = merged[-1] if merged else None
            if (prev and prev.category == tr.category
                    and tr.first_ms - prev.last_ms <= self.p.dedupe_window_ms
                    and min(prev.last_box[2], tr.last_box[2]) > max(prev.last_box[0], tr.last_box[0]) - 0.15):
                prev.last_ms = max(prev.last_ms, tr.last_ms)
                prev.hits += tr.hits
                prev.max_conf = max(prev.max_conf, tr.max_conf)
                if tr.best_score > prev.best_score:
                    prev.best_score, prev.best_ms, prev.best_box = tr.best_score, tr.best_ms, tr.best_box
                    prev.best_conf, prev.best_image = tr.best_conf, tr.best_image
                prev.last_box = tr.last_box
            else:
                merged.append(tr)
        kept = [t for t in merged
                if t.hits >= self.p.min_hits or t.max_conf >= self.p.single_hit_conf]
        kept.sort(key=lambda t: (-(t.hits >= self.p.min_hits), -t.best_score))
        kept = kept[: self.p.max_events]
        kept.sort(key=lambda t: t.best_ms)
        return kept
