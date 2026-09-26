"""Mini evaluation on labeled clips: hits, misses, false positives, latency.

labels.csv columns: clip,pothole_offsets_ms,notes
  clip                path relative to this CSV (e.g. clips/positive_1.mp4)
  pothole_offsets_ms  ';'-separated ms offsets when each known pothole is closest/clearest; empty for a negative clip

Usage:
  python eval/evaluate.py eval/labels.csv [--conf 0.25 0.35 0.5] [--tolerance-ms 1500] [--sample-fps 4]
  POTPATROL_MODEL=path/to/other.pt python eval/evaluate.py ...   # compare models
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from potpatrol_vision import analyze  # noqa: E402
from potpatrol_vision.detector import PotholeDetector  # noqa: E402


def score(events, labels, tol):
    used = set()
    tp = 0
    for lab in labels:
        match = next((i for i, e in enumerate(events) if i not in used
                      and e["first_seen_ms"] - tol <= lab <= e["last_seen_ms"] + tol), None)
        if match is not None:
            used.add(match)
            tp += 1
    return tp, len(labels) - tp, [e for i, e in enumerate(events) if i not in used]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels")
    ap.add_argument("--conf", type=float, nargs="+", default=[0.35])
    ap.add_argument("--tolerance-ms", type=int, default=1500)
    ap.add_argument("--sample-fps", type=float, default=4.0)
    ap.add_argument("--out", default=None, help="output root (default: eval/out)")
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.labels))
    out_root = a.out or os.path.join(base, "out")
    rows = list(csv.DictReader(open(a.labels, encoding="utf-8")))

    summary = []
    for conf in a.conf:
        det = PotholeDetector(conf_threshold=conf)
        tot = {"tp": 0, "miss": 0, "fp": 0, "fp_review": 0, "sec": 0.0, "video_s": 0.0}
        print(f"\n== model={det.name} conf={conf} sample_fps={a.sample_fps} ==")
        for r in rows:
            clip = os.path.join(base, r["clip"])
            labels = [int(x) for x in r["pothole_offsets_ms"].split(";") if x.strip()]
            out = os.path.join(out_root, f"conf{conf}", os.path.splitext(os.path.basename(clip))[0])
            t0 = time.perf_counter()
            m = analyze(clip, out, detector=det, sample_fps=a.sample_fps)
            dt = time.perf_counter() - t0
            tp, miss, fps = score(m["events"], labels, a.tolerance_ms)
            tot["tp"] += tp
            tot["miss"] += miss
            tot["fp"] += sum(e["status"] == "confirmed" for e in fps)
            tot["fp_review"] += sum(e["status"] == "needs_review" for e in fps)
            tot["sec"] += dt
            tot["video_s"] += m["video"]["duration_ms"] / 1000
            print(f"{r['clip']:<32} labels={len(labels)} events={len(m['events'])} hit={tp} miss={miss} "
                  f"fp={[(e['video_offset_ms'], e['status'], e['confidence']) for e in fps]} "
                  f"time={dt:.1f}s video={m['video']['duration_ms'] / 1000:.1f}s -> {out}")
        print(f"TOTAL hit={tot['tp']} miss={tot['miss']} fp_confirmed={tot['fp']} fp_needs_review={tot['fp_review']} "
              f"processing={tot['sec']:.1f}s for {tot['video_s']:.1f}s of video")
        summary.append({"conf": conf, "model": det.name, **tot})
    os.makedirs(out_root, exist_ok=True)
    with open(os.path.join(out_root, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
