import json
import os
import subprocess
import sys
from fractions import Fraction

import numpy as np
import pytest

from potpatrol_vision import InvalidVideoError, ModelError, analyze, validate_manifest
from potpatrol_vision.detector import Detection
from potpatrol_vision.events import EventMerger, MergeParams
from potpatrol_vision.frames import VideoInfo, sample_frames
from potpatrol_vision.jurisdiction import resolve_destination
from potpatrol_vision.report import draft_report

WORKER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = np.zeros((360, 640, 3), np.uint8)


def D(conf, box):
    return Detection("pothole", conf, box)


# ---------- event merging ----------

def test_consecutive_detections_merge_into_one_event():
    m = EventMerger()
    # pothole slides down and grows as the car approaches
    for i, t in enumerate(range(1000, 2250, 250)):
        y = 0.55 + 0.04 * i
        m.add_frame(t, IMG, [D(0.5 + 0.05 * i, (0.45, y, 0.55 + 0.01 * i, y + 0.08))])
    (ev,) = m.finish()
    assert ev.hits == 5 and ev.first_ms == 1000 and ev.last_ms == 2000
    assert ev.best_ms == 2000  # highest confidence frame chosen as evidence


def test_separate_potholes_in_time_stay_separate():
    m = EventMerger()
    for t in (1000, 1250, 1500):
        m.add_frame(t, IMG, [D(0.7, (0.4, 0.6, 0.5, 0.7))])
    for t in (8000, 8250):
        m.add_frame(t, IMG, [D(0.7, (0.4, 0.6, 0.5, 0.7))])
    assert len(m.finish()) == 2


def test_two_potholes_side_by_side_are_two_events():
    m = EventMerger()
    for t in (1000, 1250, 1500):
        m.add_frame(t, IMG, [D(0.7, (0.05, 0.6, 0.15, 0.7)), D(0.7, (0.8, 0.6, 0.9, 0.7))])
    assert len(m.finish()) == 2


def test_weak_single_frame_dropped_strong_single_frame_needs_review():
    m = EventMerger()
    m.add_frame(1000, IMG, [D(0.4, (0.4, 0.6, 0.5, 0.7))])
    m.add_frame(9000, IMG, [D(0.8, (0.4, 0.6, 0.5, 0.7))])
    (ev,) = m.finish()
    assert ev.hits == 1 and ev.best_ms == 9000


def test_sky_and_speck_boxes_filtered():
    m = EventMerger()
    m.add_frame(1000, IMG, [D(0.9, (0.4, 0.05, 0.5, 0.15)), D(0.9, (0.5, 0.7, 0.505, 0.705))])
    assert m.finish() == [] and m.dropped_filtered == 2


def test_event_cap():
    m = EventMerger(MergeParams(max_events=3))
    for k in range(10):
        for t in (0, 250):
            m.add_frame(k * 5000 + t, IMG, [D(0.7, (0.4, 0.6, 0.5, 0.7))])
    assert len(m.finish()) == 3


# ---------- frames: PTS-based offsets on variable-frame-rate video ----------

def _write_vfr_video(path, gaps_ms, rotate=None):
    av = pytest.importorskip("av")
    with av.open(path, "w") as c:
        s = c.add_stream("libx264" if "libx264" in av.codecs_available else "mpeg4", rate=30)
        s.width, s.height, s.pix_fmt = 320, 240, "yuv420p"
        s.codec_context.time_base = s.time_base = Fraction(1, 1000)
        t = 500  # first frame does not start at 0: offsets must be relative to it
        for i, g in enumerate(gaps_ms):
            f = av.VideoFrame.from_ndarray(np.full((240, 320, 3), i % 255, np.uint8), format="rgb24")
            f.pts, f.time_base = t, Fraction(1, 1000)
            for p in s.encode(f):
                c.mux(p)
            t += g
        for p in s.encode():
            c.mux(p)


def test_sampled_offsets_follow_pts_not_frame_index(tmp_path):
    p = str(tmp_path / "vfr.mp4")
    gaps = [33] * 30 + [100] * 20 + [20] * 50  # 30fps, then 10fps, then 50fps
    _write_vfr_video(p, gaps)
    info = VideoInfo()
    offs = [t for t, _ in sample_frames(p, 4.0, info)]
    assert offs[0] == 0
    expected_total = sum(gaps[:-1])
    assert abs(info.duration_ms - expected_total) <= 2
    # sampled roughly every 250 ms of real time regardless of frame rate changes
    diffs = np.diff(offs)
    assert diffs.min() >= 200 and diffs.max() <= 350
    assert info.frames_decoded == len(gaps)


def test_invalid_video_is_error_not_zero_hazards(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(InvalidVideoError):
        analyze(str(bad), str(tmp_path / "out"), detector=FakeDetector([]))
    assert not (tmp_path / "out" / "analysis.json").exists()


def test_cli_exit_codes(tmp_path):
    env = {**os.environ, "PYTHONPATH": WORKER_DIR}
    r = subprocess.run([sys.executable, "-m", "potpatrol_vision", str(tmp_path / "missing.mp4"),
                        str(tmp_path / "o")], capture_output=True, text=True, env=env)
    assert r.returncode == 2
    assert json.loads(r.stderr.strip().splitlines()[-1])["error"]["type"] == "invalid_video"
    r = subprocess.run([sys.executable, "-m", "potpatrol_vision", "x", str(tmp_path / "f"), "--fixture"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    m = json.load(open(tmp_path / "f" / "analysis.json"))
    assert m["mode"] == "fixture"
    validate_manifest(m, str(tmp_path / "f"))


# ---------- pipeline end-to-end with a fake detector ----------

class FakeDetector:
    """Fires on frames whose offset falls in given windows."""

    def __init__(self, windows):
        self.windows = windows
        self.t = []

    def describe(self):
        return {"name": "fake", "weights_sha256": None, "classes": ["pothole"], "conf_threshold": 0.35}

    def detect(self, images):
        out = []
        for img in images:
            v = int(img[0, 0, 0])  # frame index encoded in pixel value by _write_vfr_video
            out.append([D(0.8, (0.4, 0.6, 0.55, 0.75))] if any(a <= v <= b for a, b in self.windows) else [])
        return out


def test_pipeline_writes_valid_manifest_and_evidence(tmp_path):
    p = str(tmp_path / "clip.mp4")
    _write_vfr_video(p, [33] * 150)
    out = str(tmp_path / "out")
    m = analyze(p, out, detector=FakeDetector([(60, 80)]))
    validate_manifest(m, out)
    (ev,) = m["events"]
    assert ev["status"] == "confirmed"
    assert 60 * 33 - 300 <= ev["video_offset_ms"] <= 80 * 33 + 300
    assert os.path.getsize(os.path.join(out, ev["evidence_path"])) > 0


def test_pipeline_negative_clip_returns_empty_events(tmp_path):
    p = str(tmp_path / "clip.mp4")
    _write_vfr_video(p, [33] * 60)
    m = analyze(p, str(tmp_path / "out"), detector=FakeDetector([]))
    assert m["events"] == [] and m["mode"] == "model"


def test_generic_coco_model_rejected(monkeypatch, tmp_path):
    pytest.importorskip("ultralytics")
    coco = os.path.expanduser("~/weights/yolo26n.pt")
    if not os.path.isfile(coco):
        pytest.skip("no generic checkpoint available")
    monkeypatch.setenv("POTPATROL_MODEL", coco)
    from potpatrol_vision.detector import PotholeDetector

    with pytest.raises(ModelError, match="no 'pothole' class"):
        PotholeDetector()


# ---------- jurisdiction + report ----------

FIU = {"lat": 25.7563, "lon": -80.3740, "accuracy_m": 8.0}


def test_miami_dade_without_ownership_needs_review():
    r = resolve_destination(FIU["lat"], FIU["lon"], 8.0, address={"city": "Miami"})
    assert r["destination_status"] == "needs_review"
    assert {c["agency_id"] for c in r["candidates"]} >= {"miami-dade-dtpw-311", "fdot-d6"}
    assert all(s["checked"] for c in r["candidates"] for s in c["sources"])


def test_outside_registry_unsupported():
    assert resolve_destination(40.71, -74.0)["destination_status"] == "unsupported"


def test_owner_hint_with_source_verifies():
    r = resolve_destination(FIU["lat"], FIU["lon"], owner_hint={"agency_id": "fdot-d6", "source": "https://example.gov/gis"})
    assert r["destination_status"] == "verified" and "District Six" in r["jurisdiction_candidate"]


def test_report_is_evidence_bounded():
    ev = json.load(open(os.path.join(WORKER_DIR, "potpatrol_vision", "fixtures", "analysis.fixture.json")))["events"][0]
    r = draft_report(ev, "evidence/event-001-raw.jpg", FIU["lat"], FIU["lon"], 8.0, "2026-09-26T18:04:12Z")
    text = r["description"]["value"].lower()
    for banned in ("inch", "deep", "lane", "danger", "injur", "owned by", "submitted"):
        assert banned not in text
    assert r["severity"]["value"] is None
    assert r["submission_status"] == "not_submitted"
    assert r["destination"]["destination_status"] == "needs_review"
    assert r["evidence_path"]["value"] == "evidence/event-001-raw.jpg"
    assert text.startswith("possible pothole")
    reviewed = draft_report(ev, None, FIU["lat"], FIU["lon"], None, None, user_reviewed=True)
    assert reviewed["category"]["source"] == "user"


def test_report_missing_location_and_time_needs_review():
    r = draft_report({"category": "pothole"}, None, None, None, None, None)
    assert r["destination"]["destination_status"] == "needs_review"
    assert r["destination"]["candidates"] == [] and r["destination"]["destination_url"] is None
    assert r["coordinates"]["value"] is None and r["location_description"]["value"] is None
    assert r["observation_time"] == {"value": None, "source": "unassessed"}
    assert "None" not in r["description"]["value"]


def test_report_outside_coverage_unsupported():
    r = draft_report({"category": "pothole"}, "e.jpg", 40.71, -74.0, 5.0, "2026-09-26T18:04:12Z")
    assert r["destination"]["destination_status"] == "unsupported"
    assert r["destination"]["destination_url"] is None
