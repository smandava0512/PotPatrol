"""Private review of REAL-model results on real clips (never fixture): misses, false positives, evidence images.

Runs the detector once per clip at a low confidence floor, keeps every raw detection, then replays event merging at
several thresholds so they can be compared without re-running the model.

  python worker/eval/review.py CLIP [CLIP ...] --out worker/eval/out/review [--thresholds 0.25 0.35 0.5] [--device cpu]

Per clip it writes (under --out/<clip>/):
  raw_detections.json          every per-frame detection >= floor (t_ms, conf, bbox)
  contact_sheet.jpg            every frame with a detection >= floor, boxes colored by confidence
  conf<T>/analysis.json        the exact manifest the worker would return at threshold T (+ evidence JPEGs)
and prints a table of events per threshold.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from potpatrol_vision.detector import PotholeDetector  # noqa: E402
from potpatrol_vision.events import EventMerger, MergeParams  # noqa: E402
from potpatrol_vision.frames import VideoInfo, sample_frames  # noqa: E402
from potpatrol_vision.pipeline import _event_dict, _write_manifest  # noqa: E402
from potpatrol_vision.schema import SCHEMA_VERSION  # noqa: E402


def contact_sheet(frames: list[tuple[int, np.ndarray, list]], path: str, thresholds: list[float], cols: int = 4):
    import cv2

    if not frames:
        return
    tiles = []
    lo, hi = min(thresholds), max(thresholds)
    for t, img, dets in frames:
        im = img.copy()
        h, w = im.shape[:2]
        for d in dets:
            # red: >= highest threshold, orange: in between, yellow: below lowest threshold (floor only)
            color = (0, 0, 255) if d.confidence >= hi else (0, 140, 255) if d.confidence >= lo else (0, 230, 255)
            x1, y1, x2, y2 = d.bbox
            cv2.rectangle(im, (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h)), color, max(2, w // 300))
            cv2.putText(im, f"{d.confidence:.2f}", (int(x1 * w), max(20, int(y1 * h) - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, w / 900, color, max(2, w // 400))
        cv2.putText(im, f"t={t / 1000:.2f}s", (10, int(h * 0.06)), cv2.FONT_HERSHEY_SIMPLEX, w / 700, (255, 255, 255),
                    max(2, w // 300))
        tw = 480
        tiles.append(cv2.resize(im, (tw, int(h * tw / w))))
    th = max(t.shape[0] for t in tiles)
    tiles = [np.pad(t, ((0, th - t.shape[0]), (0, 0), (0, 0))) for t in tiles]
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    cv2.imwrite(path, np.vstack(rows[:30]), [cv2.IMWRITE_JPEG_QUALITY, 85])  # cap at 120 frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "review"))
    ap.add_argument("--thresholds", type=float, nargs="+", default=[0.25, 0.35, 0.5])
    ap.add_argument("--floor", type=float, default=0.10)
    ap.add_argument("--sample-fps", type=float, default=4.0)
    ap.add_argument("--device", default=None)
    a = ap.parse_args()

    t0 = time.perf_counter()
    det = PotholeDetector(conf_threshold=a.floor, device=a.device)
    print(f"model={det.name} sha256={det.weights_sha256[:12]} classes={det.describe()['model_classes']} "
          f"load={time.perf_counter() - t0:.1f}s device={a.device or 'auto'}")

    for clip in a.clips:
        name = os.path.splitext(os.path.basename(clip))[0]
        out = os.path.join(a.out, name)
        os.makedirs(out, exist_ok=True)
        info = VideoInfo()
        hits: list[tuple[int, np.ndarray, list]] = []
        raw = []
        t1 = time.perf_counter()
        batch = []

        def flush():
            for (t, img), dets in zip(batch, det.detect([b[1] for b in batch])):
                if dets:
                    hits.append((t, img, dets))
                    raw.extend({"t_ms": t, "conf": round(d.confidence, 3), "bbox": [round(v, 4) for v in d.bbox]}
                               for d in dets)
            batch.clear()

        for t, img in sample_frames(clip, a.sample_fps, info):
            batch.append((t, img))
            if len(batch) >= 8:
                flush()
        if batch:
            flush()
        infer_s = time.perf_counter() - t1
        json.dump({"clip": clip, "video": vars(info), "floor": a.floor, "detections": raw},
                  open(os.path.join(out, "raw_detections.json"), "w"), indent=1, default=str)
        contact_sheet(hits, os.path.join(out, "contact_sheet.jpg"), a.thresholds)

        print(f"\n=== {clip}")
        print(f"    {info.duration_ms / 1000:.1f}s video, {info.width}x{info.height}, rotation={info.rotation_deg}, "
              f"{info.frames_decoded} frames decoded, {info.frames_sampled} sampled, "
              f"processing {infer_s:.1f}s ({infer_s / max(info.duration_ms / 1000, 1e-6):.2f}x realtime)")
        print(f"    frames with any detection >= {a.floor}: {len(hits)}; raw boxes: {len(raw)}")
        for th in a.thresholds:
            params = MergeParams()
            m = EventMerger(params)
            for t, img, dets in hits:
                m.add_frame(t, img, [d for d in dets if d.confidence >= th])
            tracks = m.finish()
            tdir = os.path.join(out, f"conf{th}")
            os.makedirs(tdir, exist_ok=True)
            events = [_event_dict(i + 1, tr, tdir, params.min_hits) for i, tr in enumerate(tracks)]
            _write_manifest(tdir, {
                "schema_version": SCHEMA_VERSION, "mode": "model",
                "video": {"duration_ms": info.duration_ms, "frames_decoded": info.frames_decoded,
                          "frames_sampled": info.frames_sampled, "sample_fps": info.sample_fps,
                          "rotation_deg": info.rotation_deg, "width": info.width, "height": info.height},
                "model": {**det.describe(), "conf_threshold": th},
                "processing_ms": int(infer_s * 1000), "events": events})
            print(f"    conf>={th}: {len(events)} events")
            for e in events:
                print(f"      {e['event_id']} t={e['video_offset_ms'] / 1000:6.2f}s "
                      f"[{e['first_seen_ms'] / 1000:.2f}-{e['last_seen_ms'] / 1000:.2f}] conf={e['confidence']:.2f} "
                      f"{e['status']:<12} hits={e['hits']} -> {os.path.join(tdir, e['evidence_path'])}")
        print(f"    contact sheet: {os.path.join(out, 'contact_sheet.jpg')}")


if __name__ == "__main__":
    main()
