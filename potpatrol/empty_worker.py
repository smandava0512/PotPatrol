"""Demo no-hazard fixture worker, not inference."""
import json
from pathlib import Path


def analyze(video_path, output_dir):
    path = Path(output_dir) / "analysis.json"
    path.write_text(json.dumps({"schema_version": 1, "events": []}), encoding="utf-8")
    return path
