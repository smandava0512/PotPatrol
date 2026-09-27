"""Deterministic, evidence-bounded report drafting. Every field carries provenance.

Never states dimensions, depth, lane, route, ownership or injury risk; those are not observable from what we have.
An optional validator result (validators.py) is passed through as `ai_check` and never changes the text.
"""
from __future__ import annotations

from .jurisdiction import resolve_destination

REPORT_SCHEMA_VERSION = 1


def _f(value, source: str) -> dict:
    return {"value": value, "source": source}


def _missing_location_destination() -> dict:
    return {
        "destination_status": "needs_review",
        "jurisdiction_candidate": None,
        "destination_url": None,
        "candidates": [],
        "reason": "Location is missing, so no agency can be suggested. Add or confirm the location first.",
        "sources": [],
    }


def draft_report(hazard: dict, evidence_path: str | None, lat: float | None, lon: float | None,
                 accuracy_m: float | None, observed_at: str | None, *, address: dict | None = None,
                 owner_hint: dict | None = None, user_reviewed: bool = False) -> dict:
    """Build editable report fields for one stored hazard.

    hazard: the stored event (docs/contracts/analysis.md); needs `category`, other fields optional.
    evidence_path: path/URL of the evidence image as the backend stores it (echoed back, not read).
    lat, lon, accuracy_m: GPS interpolated by the backend at video_offset_ms; any may be None.
    observed_at: ISO-8601 time of the evidence frame, or None if unknown.
    address: optional reverse-geocode {"display": "..."}; labeled as approximate, never used for ownership.
    user_reviewed: True once the user confirmed the hazard in the app.
    """
    has_loc = lat is not None and lon is not None
    acc_txt = (f" (GPS accuracy about ±{accuracy_m:.0f} m)" if isinstance(accuracy_m, (int, float))
               else " (GPS accuracy unknown)")
    if has_loc:
        lat, lon = float(lat), float(lon)
        coords = f"{lat:.5f}, {lon:.5f}"
        if address and address.get("display"):
            location = _f(f"Near {address['display']} (approximate, from reverse geocoding); GPS {coords}{acc_txt}",
                          "reverse_geocode+gps")
        else:
            location = _f(f"GPS {coords}{acc_txt}", "gps")
        where = f", at GPS {coords}{acc_txt}"
        dest = resolve_destination(lat, lon, accuracy_m, address=address, owner_hint=owner_hint)
    else:
        location = _f(None, "unassessed")
        where = ""
        dest = _missing_location_destination()

    when = f" at {observed_at}" if observed_at else ""
    label = "road damage" if hazard["category"] == "road_damage" else "pothole"
    what = label.capitalize() if user_reviewed else f"Possible {label}"
    review = ("Automatically detected and confirmed by the reporter from the attached photo."
              if user_reviewed else "Automatically detected; not yet confirmed by the reporter.")
    description = f"{what} visible in the attached photo taken from a vehicle-mounted phone camera{when}{where}. {review}"

    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "event_id": hazard.get("event_id"),
        "category": _f(hazard["category"], "user" if user_reviewed else
                       "validator" if hazard.get("source") == "gemini_scan" else "detector"),
        "observation_time": _f(observed_at, "device_clock" if observed_at else "unassessed"),
        "location_description": location,
        "coordinates": _f({"lat": lat, "lon": lon, "accuracy_m": accuracy_m} if has_loc else None,
                          "gps" if has_loc else "unassessed"),
        "description": _f(description, "template"),
        "severity": {"value": None, "basis": "not assessed from a single camera frame", "source": "unassessed"},
        "detector": _f({"confidence": hazard.get("confidence"), "hits": hazard.get("hits"),
                        "status": hazard.get("status")}, "detector"),
        "evidence_path": _f(evidence_path, "detector" if evidence_path else "unassessed"),
        # Advisory second opinion on the evidence image; never overrides the user's review or the description.
        "ai_check": _f(hazard.get("validation"), "validator" if hazard.get("validation") else "unassessed"),
        "destination": {**dest, "source": "registry"},
        "submission_status": "not_submitted",
        "submission_note": "Opening the agency page is a hand-off, not a submission. Mark submitted only with a "
                           "confirmation/receipt number from the agency.",
    }
