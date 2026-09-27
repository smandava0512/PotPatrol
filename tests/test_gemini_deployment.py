"""Ensure Gemini credentials are scoped to the vision worker only."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_aws_compose_injects_private_gemini_file_only_into_worker():
    compose = (ROOT / "compose.aws.yaml").read_text(encoding="utf-8")
    shared, worker = compose.split("  worker:\n", 1)
    worker, _ = worker.split("  caddy:\n", 1)
    assert "GEMINI_API_KEY" not in shared
    assert "GEMINI_API_KEY" not in worker
    assert "gemini.env" not in shared
    assert "path: gemini.env" in worker
    assert "POTPATROL_ANALYSIS_MODE: model" in shared
    assert "POTPATROL_VISION_MODE: gemini_required" in shared
    assert "gemini.env" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "gemini.env" in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
