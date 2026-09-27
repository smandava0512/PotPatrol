import json
import os
import subprocess
import sys
import types

import numpy as np
import pytest

from potpatrol_vision import analyze
from potpatrol_vision.detector import Detection
from potpatrol_vision.schema import AnalysisError, validate_manifest


class Detector:
    def __init__(self, alarm=False):
        self.alarm = alarm

    def describe(self):
        return {"name": "stub-yolo", "weights_sha256": None, "classes": ["pothole"]}

    def detect(self, images):
        return [[Detection("pothole", 0.8, (0.75, 0.7, 0.9, 0.85))] if self.alarm else [] for _ in images]


class Gemini:
    def __init__(self, *, hazards=None, negative=False, fail=False):
        self.hazards = hazards or []
        self.negative = negative
        self.fail = fail
        self.scans = []
        self.checks = []

    def describe(self):
        return {"provider": "gemini", "model": "stub-gemini"}

    def scan(self, path):
        assert path.endswith(".jpg") and os.path.isfile(path)
        self.scans.append(path)
        if self.fail:
            return None
        return self.hazards if len(self.scans) == 2 else []

    def validate(self, path, category):
        assert path.endswith("-raw.jpg") and os.path.isfile(path)
        self.checks.append(path)
        if self.fail:
            return None
        return {"is_hazard": not self.negative, "confidence": 0.9,
                "rationale": "visible road surface", "provider": "gemini", "model": "stub-gemini"}


@pytest.fixture
def clip(monkeypatch, tmp_path):
    from potpatrol_vision import pipeline
    video = tmp_path / "input.mp4"
    video.write_bytes(b"synthetic placeholder; frames supplied by stub")

    def frames(path, fps, info):
        info.duration_ms = 48000
        info.width, info.height = 160, 120
        info.sample_fps = fps
        for i in range(193):
            info.frames_decoded += 1
            info.frames_sampled += 1
            yield i * 250, np.full((120, 160, 3), i % 255, np.uint8)

    monkeypatch.setattr(pipeline, "sample_frames", frames)
    monkeypatch.setenv("POTPATROL_VISION_MODE", "gemini_required")
    monkeypatch.setenv("POTPATROL_ANALYSIS_MODE", "model")
    return str(video), str(tmp_path / "out")


def test_required_scans_even_without_yolo_events_and_reports_frame_backed_miss(clip):
    video, out = clip
    gemini = Gemini(hazards=[{"category": "road_damage", "bbox": [0.4, 0.6, 0.6, 0.8], "confidence": 0.83}])
    m = analyze(video, out, detector=Detector(), validator=gemini)
    validate_manifest(m, out)
    assert 2 < len(gemini.scans) <= 24
    assert m["validator"]["model"] == "stub-gemini"
    assert m["model"]["name"] == "stub-yolo"
    (event,) = m["events"]
    assert event["status"] == "needs_review"
    assert event["confidence"] == 0.83 and event["bbox"] == [0.4, 0.6, 0.6, 0.8]
    assert event["source"] == "gemini_scan" and event["category"] == "road_damage"
    from potpatrol_vision.report import draft_report
    report = draft_report(event, None, None, None, None, None)
    assert "road damage" in report["description"]["value"].lower()
    assert report["category"]["source"] == "validator"
    assert os.path.isfile(os.path.join(out, event["evidence_raw_path"]))
    assert m["vision_mode"] == "gemini_required"


def test_required_clean_clip_returns_empty_only_after_scans(clip):
    video, out = clip
    gemini = Gemini()
    m = analyze(video, out, detector=Detector(), validator=gemini)
    assert m["events"] == [] and len(gemini.scans) == m["gemini_frames_scanned"] > 0
    assert os.path.isfile(os.path.join(out, "analysis.json"))


def test_required_rejects_yolo_curb_candidate(clip):
    video, out = clip
    gemini = Gemini(negative=True)
    m = analyze(video, out, detector=Detector(alarm=True), validator=gemini)
    assert m["events"] == []
    assert gemini.checks and gemini.scans


def test_rejected_yolo_curb_is_not_resurrected_by_later_scan(clip):
    video, out = clip
    gemini = Gemini(negative=True, hazards=[{"category": "pothole", "bbox": [0.75, 0.7, 0.9, 0.85],
                                             "confidence": 0.9}])
    m = analyze(video, out, detector=Detector(alarm=True), validator=gemini)
    assert m["events"] == []


def test_scan_keeps_adjacent_pothole_next_to_rejected_yolo_curb(clip):
    video, out = clip
    gemini = Gemini(negative=True, hazards=[{"category": "pothole", "bbox": [0.59, 0.7, 0.74, 0.85],
                                             "confidence": 0.9}])
    m = analyze(video, out, detector=Detector(alarm=True), validator=gemini)
    validate_manifest(m, out)
    assert len(m["events"]) == 1
    assert m["events"][0]["bbox"] == [0.59, 0.7, 0.74, 0.85]
    assert m["events"][0]["source"] == "gemini_scan"
    assert len(gemini.checks) == 1
    assert len(gemini.scans) == m["gemini_frames_scanned"] <= 24


def test_moving_camera_scan_associates_downward_same_hazard_across_sparse_frames(clip):
    video, out = clip

    class MovingGemini(Gemini):
        def scan(self, path):
            super().scan(path)
            boxes = {2: [0.4, 0.46, 0.54, 0.59],
                     3: [0.39, 0.57, 0.56, 0.74],
                     4: [0.38, 0.69, 0.58, 0.88]}
            return ([{"category": "pothole", "bbox": boxes[len(self.scans)], "confidence": 0.9}]
                    if len(self.scans) in boxes else [])

    gemini = MovingGemini()
    m = analyze(video, out, detector=Detector(), validator=gemini)
    validate_manifest(m, out)
    assert len(m["events"]) == 1
    assert m["events"][0]["source"] == "gemini_scan"
    assert len(gemini.scans) == m["gemini_frames_scanned"] <= 24
    assert not gemini.checks


@pytest.mark.parametrize("yolo_offset,scan_offset,yolo_box,scan_box", [
    (1000, 2000, [0.4, 0.5, 0.55, 0.65], [0.39, 0.62, 0.56, 0.79]),
    (2000, 1000, [0.39, 0.62, 0.56, 0.79], [0.4, 0.5, 0.55, 0.65]),
])
def test_moving_camera_scan_does_not_duplicate_validated_yolo(
        tmp_path, yolo_offset, scan_offset, yolo_box, scan_box):
    import cv2
    from potpatrol_vision.required import FrameSelector, reconcile

    frame = np.zeros((120, 160, 3), np.uint8)
    selected = FrameSelector()
    for offset in (0, 1000, 2000):
        selected.add(offset, frame)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    assert cv2.imwrite(str(evidence / "event-001-raw.jpg"), frame)
    yolo = {"event_id": "event-001", "category": "pothole", "video_offset_ms": yolo_offset,
            "first_seen_ms": yolo_offset, "last_seen_ms": yolo_offset,
            "bbox": yolo_box, "evidence_raw_path": "evidence/event-001-raw.jpg"}

    class MovingGemini(Gemini):
        def scan(self, path):
            super().scan(path)
            return ([{"category": "pothole", "bbox": scan_box, "confidence": 0.9}]
                    if len(self.scans) == scan_offset // 1000 + 1 else [])

    result = reconcile([yolo], selected, str(tmp_path), MovingGemini())
    assert len(result) == 1
    assert result[0]["source"] == "yolo_gemini_validated"


def test_scan_keeps_distinct_pothole_below_validated_yolo(tmp_path):
    import cv2
    from potpatrol_vision.required import FrameSelector, reconcile

    frame = np.zeros((120, 160, 3), np.uint8)
    selected = FrameSelector()
    for offset in (0, 1000, 2000):
        selected.add(offset, frame)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    assert cv2.imwrite(str(evidence / "event-001-raw.jpg"), frame)
    yolo = {"event_id": "event-001", "category": "pothole", "video_offset_ms": 1000,
            "first_seen_ms": 1000, "last_seen_ms": 1000,
            "bbox": [0.4, 0.5, 0.55, 0.65], "evidence_raw_path": "evidence/event-001-raw.jpg"}

    class DistinctGemini(Gemini):
        def scan(self, path):
            super().scan(path)
            return ([{"category": "pothole", "bbox": [0.4, 0.67, 0.55, 0.82],
                     "confidence": 0.9}] if len(self.scans) == 3 else [])

    result = reconcile([yolo], selected, str(tmp_path), DistinctGemini())
    assert len(result) == 2
    assert {item["source"] for item in result} == {"gemini_scan", "yolo_gemini_validated"}


def test_scan_keeps_distinct_potholes_in_successive_nonoverlapping_frames(clip):
    video, out = clip

    class DistinctGemini(Gemini):
        def scan(self, path):
            super().scan(path)
            boxes = {2: [0.4, 0.5, 0.55, 0.65], 3: [0.4, 0.67, 0.55, 0.82]}
            return ([{"category": "pothole", "bbox": boxes[len(self.scans)], "confidence": 0.9}]
                    if len(self.scans) in boxes else [])

    m = analyze(video, out, detector=Detector(), validator=DistinctGemini())
    assert len(m["events"]) == 2
    assert all(item["source"] == "gemini_scan" for item in m["events"])


def test_scan_keeps_distinct_hazards_in_same_and_later_frames(clip):
    video, out = clip

    class DistinctGemini(Gemini):
        def scan(self, path):
            super().scan(path)
            boxes = {2: [[0.4, 0.55, 0.54, 0.68], [0.4, 0.74, 0.54, 0.87]],
                     3: [[0.4, 0.38, 0.54, 0.51]]}
            return [{"category": "pothole", "bbox": box, "confidence": 0.9}
                    for box in boxes.get(len(self.scans), [])]

    gemini = DistinctGemini()
    m = analyze(video, out, detector=Detector(), validator=gemini)
    assert len(m["events"]) == 3
    assert len({e["event_id"] for e in m["events"]}) == 3
    assert len(gemini.scans) == m["gemini_frames_scanned"] <= 24


def test_required_accepts_yolo_only_for_review(clip):
    video, out = clip
    m = analyze(video, out, detector=Detector(alarm=True), validator=Gemini())
    assert m["events"] and all(e["status"] == "needs_review" for e in m["events"])
    assert m["events"][0]["validation"]["is_hazard"] is True


@pytest.mark.parametrize("fixture", [None, True])
def test_required_refuses_fixture_even_when_explicit(clip, monkeypatch, fixture):
    video, out = clip
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "analysis.json"), "w") as stale:
        stale.write('{"mode":"fixture"}')
    monkeypatch.setenv("POTPATROL_ANALYSIS_MODE", "fixture")
    with pytest.raises(AnalysisError, match="fixture"):
        analyze(video, out, fixture=fixture, detector=Detector(), validator=Gemini())
    assert not os.path.exists(os.path.join(out, "analysis.json"))


def test_required_fails_if_scan_fails_even_when_yolo_empty(clip):
    video, out = clip
    with pytest.raises(AnalysisError, match="Gemini"):
        analyze(video, out, detector=Detector(), validator=Gemini(fail=True))
    assert not os.path.exists(os.path.join(out, "analysis.json"))


def test_required_fails_if_candidate_validation_fails(clip):
    video, out = clip
    with pytest.raises(AnalysisError, match="Gemini"):
        analyze(video, out, detector=Detector(alarm=True), validator=Gemini(fail=True))
    assert not os.path.exists(os.path.join(out, "analysis.json"))


def test_required_without_key_fails_before_detector_or_video(monkeypatch, tmp_path):
    monkeypatch.setenv("POTPATROL_VISION_MODE", "gemini_required")
    monkeypatch.setenv("POTPATROL_ANALYSIS_MODE", "model")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(AnalysisError, match="GEMINI_API_KEY"):
        analyze("absent.mp4", str(tmp_path / "out"))


def test_worker_startup_fails_closed_without_key(tmp_path):
    repo = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    environment = {**os.environ, "POTPATROL_VISION_MODE": "gemini_required",
                   "POTPATROL_ANALYSIS_MODE": "model", "POTPATROL_STORAGE_DIR": str(tmp_path),
                   "PYTHONPATH": os.path.join(repo, "worker") + os.pathsep + repo}
    environment.pop("GEMINI_API_KEY", None)
    environment.pop("GOOGLE_API_KEY", None)
    result = subprocess.run([sys.executable, "-m", "potpatrol.worker", "--once"],
                            cwd=repo, env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "GEMINI_API_KEY" in result.stderr


def test_frame_selection_stays_bounded_and_covers_long_clip():
    from potpatrol_vision.required import FrameSelector
    selector = FrameSelector()
    frame = np.zeros((120, 160, 3), np.uint8)
    for i in range(2401):  # ten minutes of 4-fps samples
        selector.add(i * 250, frame)
    offsets = [t for t, _ in selector.frames]
    assert len(offsets) <= 24
    assert offsets[0] == 0 and offsets[-1] >= 550000
    assert all(jpeg.startswith(b"\xff\xd8\xff") for _, jpeg in selector.frames)


def test_frame_selection_uses_full_budget_on_48_second_clip():
    from potpatrol_vision.required import FrameSelector
    selector = FrameSelector()
    frame = np.zeros((120, 160, 3), np.uint8)
    for i in range(193):
        selector.add(i * 250, frame)
    offsets = [t for t, _ in selector.frames]
    assert len(offsets) == 24
    assert offsets == sorted(offsets)
    assert offsets[0] == 0 and offsets[-1] == 48000
    assert all(sum(start <= t < start + 12000 for t in offsets) >= 3
               for start in (0, 12000, 24000, 36000))


def test_gemini_sdk_receives_only_selected_jpeg_bytes_and_prompt(monkeypatch, tmp_path):
    from potpatrol_vision.validators import GeminiValidator
    calls = []

    def generate_content(**kwargs):
        calls.append(kwargs)
        return types.SimpleNamespace(text=json.dumps({"hazards": []}))

    sdk_types = types.SimpleNamespace(
        HttpOptions=lambda **kwargs: kwargs,
        Part=types.SimpleNamespace(from_bytes=lambda **kwargs: kwargs),
        GenerateContentConfig=lambda **kwargs: kwargs,
        AutomaticFunctionCallingConfig=lambda **kwargs: kwargs,
    )
    genai = types.ModuleType("google.genai")
    genai.types = sdk_types
    genai.Client = lambda **kwargs: types.SimpleNamespace(models=types.SimpleNamespace(generate_content=generate_content))
    google = types.ModuleType("google")
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    frame = tmp_path / "selected.jpg"
    frame.write_bytes(b"\xff\xd8\xffselected-pixels")
    validator = GeminiValidator("fake-test-key")
    assert validator.scan(str(frame)) == []
    (request,) = calls
    assert request["contents"][0] == {"data": frame.read_bytes(), "mime_type": "image/jpeg"}
    assert isinstance(request["contents"][1], str)
    assert "latitude" not in request["contents"][1].lower()
    assert len(request["contents"]) == 2


def test_required_rejects_invalid_scan_boxes(clip):
    video, out = clip
    gemini = Gemini(hazards=[{"bbox": [0, 0, 1.5, 1], "confidence": 0.9}])
    with pytest.raises(AnalysisError, match="Gemini"):
        analyze(video, out, detector=Detector(), validator=gemini)
    assert not os.path.exists(os.path.join(out, "analysis.json"))


def test_required_ignores_well_formed_boxes_above_the_road_without_failing(clip):
    video, out = clip
    gemini = Gemini(hazards=[{"category": "road_damage", "bbox": [0.473, 0.082, 0.695, 0.345],
                             "confidence": 0.81}])
    manifest = analyze(video, out, detector=Detector(), validator=gemini)
    assert manifest["events"] == []
    assert len(gemini.scans) == manifest["gemini_frames_scanned"] == 24


def test_required_preserves_reversed_corner_coordinates_as_one_box(clip):
    video, out = clip
    gemini = Gemini(hazards=[{"category": "road_damage", "bbox": [0.466, 0.75, 0.589, 0.363],
                             "confidence": 0.75}])
    manifest = analyze(video, out, detector=Detector(), validator=gemini)
    validate_manifest(manifest, out)
    assert manifest["vision_mode"] == "gemini_required"
    assert manifest["gemini_frames_scanned"] == 24
    assert len(manifest["events"]) == 1
    assert manifest["events"][0]["bbox"] == [0.466, 0.363, 0.589, 0.75]
    assert manifest["events"][0]["source"] == "gemini_scan"
