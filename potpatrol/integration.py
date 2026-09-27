"""Adapt Developer 3's worker and report schemas to the canonical backend contract."""
from pathlib import Path


def analyze(video_path: str, output_dir: str) -> str:
    from potpatrol_vision import analyze as vision_analyze

    # Dev 3 returns a manifest dict; the job runner validates the written JSON path.
    vision_analyze(video_path, output_dir)
    return str(Path(output_dir) / "analysis.json")


def draft_report(context: dict) -> dict:
    from potpatrol_vision.report import draft_report as vision_draft

    location = context.get("location") or {}
    report = vision_draft(
        {"event_id": context["event_id"], "category": context["category"],
         "confidence": context["confidence"], "status": context["review_state"]},
        context["evidence_url"], location.get("latitude"), location.get("longitude"),
        location.get("horizontal_accuracy_m"), context.get("observed_at"),
    )
    destination = report.pop("destination")
    status = destination["destination_status"]
    # A candidate link is not a verified destination; review comes first.
    return {
        "fields": {key: value for key, value in report.items() if key not in
                   ("report_schema_version", "event_id", "submission_status", "submission_note")},
        "destination": {"status": status,
                        "url": destination["destination_url"] if status == "verified" else None,
                        "candidates": destination["candidates"],
                        "jurisdiction_candidate": destination["jurisdiction_candidate"],
                        "reason": destination["reason"], "sources": destination["sources"]},
    }
