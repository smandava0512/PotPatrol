"""The deterministic demo worker is NOT real hazard inference."""
import json
import shutil
from pathlib import Path


def analyze(video_path, output_dir):
    out = Path(output_dir)
    (out / "evidence").mkdir(parents=True, exist_ok=True)
    fixture = Path(__file__).parent.parent / "fixtures" / "sample-evidence.jpg"
    shutil.copyfile(fixture, out / "evidence" / "one.jpg")
    manifest = {"schema_version": 1, "events": [{"video_offset_ms": 1000, "category": "pothole", "confidence": 0.9, "evidence_path": "evidence/one.jpg", "first_seen_ms": 900, "last_seen_ms": 1200, "notes": "Demo fixture, not real inference"}]}
    path = out / "analysis.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path
