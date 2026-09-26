"""Florida-first reporting-destination resolver.

A reverse-geocoded road or city name does NOT prove who maintains a road (city vs county vs FDOT vs toll
authority). Unless ownership comes from an explicit verified rule, the result is `needs_review` with candidates.
"""
from __future__ import annotations

import json
import os

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "data", "fl_registry.json")
STATUSES = ("verified", "needs_review", "unsupported")


def load_registry(path: str = REGISTRY_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _in_bbox(lat, lon, b) -> bool:
    return b["min_lat"] <= lat <= b["max_lat"] and b["min_lon"] <= lon <= b["max_lon"]


def _in_polygon(lat, lon, poly) -> bool:
    """Ray casting; poly is [[lat, lon], ...]."""
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if (xi > lon) != (xj > lon) and lat < (yj - yi) * (lon - xi) / (xj - xi) + yi:
            inside = not inside
        j = i
    return inside


def _candidate(agency: dict, why: str) -> dict:
    return {
        "agency_id": agency["id"],
        "name": agency["name"],
        "handles": agency["handles"],
        "destination_url": agency["destination_url"],
        "destination_kind": agency["destination_kind"],
        "phone": agency.get("phone"),
        "sources": agency["sources"],
        "why_candidate": why,
    }


def resolve_destination(lat: float, lon: float, accuracy_m: float | None = None,
                        address: dict | None = None, owner_hint: dict | None = None,
                        registry: dict | None = None) -> dict:
    """Return {destination_status, jurisdiction_candidate, destination_url, candidates, reason, sources}.

    address: optional reverse-geocode dict, e.g. {"city": "Miami", "road": "SW 8th St"} (hint only).
    owner_hint: optional {"agency_id": ..., "source": url} from an authoritative road-ownership lookup
                (e.g. an official GIS layer queried by the backend) or a registry rule; never from reverse geocoding.
    """
    reg = registry or load_registry()
    agencies = {a["id"]: a for a in reg["agencies"]}
    region = next((r for r in reg["coverage_regions"] if _in_bbox(lat, lon, r["bbox_approx"])), None)
    if region is None:
        return {
            "destination_status": "unsupported",
            "jurisdiction_candidate": None,
            "destination_url": None,
            "candidates": [],
            "reason": "Location is outside the verified agency registry coverage (currently Miami-Dade County, FL). "
                      "Find the local 311/public-works reporting page manually.",
            "sources": [],
        }

    def verified(agency: dict, basis: str, basis_source: str | None) -> dict:
        srcs = list(agency["sources"]) + ([{"url": basis_source, "what": "ownership basis"}] if basis_source else [])
        return {
            "destination_status": "verified",
            "jurisdiction_candidate": agency["name"],
            "destination_url": agency["destination_url"],
            "candidates": [_candidate(agency, basis)],
            "reason": basis,
            "sources": srcs,
        }

    if owner_hint and owner_hint.get("agency_id") in agencies and owner_hint.get("source"):
        return verified(agencies[owner_hint["agency_id"]],
                        f"Road ownership from authoritative source: {owner_hint['source']}", owner_hint["source"])

    for zone in reg.get("ownership_zones", []):
        buf = zone.get("max_gps_accuracy_m", 15)
        if _in_polygon(lat, lon, zone["polygon"]) and (accuracy_m is None or accuracy_m <= buf):
            return verified(agencies[zone["agency_id"]], zone["basis"], zone.get("source"))

    # Registry order is kept on purpose. A postal "city" from reverse geocoding is not a municipal boundary
    # (e.g. FIU has a "Miami" mailing address but is outside City of Miami limits), so it must not rank candidates.
    cands = [a for a in reg["agencies"] if a["region"] == region["id"]]
    candidates = [_candidate(a, "Agency serves this area; road ownership not established") for a in cands]
    return {
        "destination_status": "needs_review",
        "jurisdiction_candidate": candidates[0]["name"] if candidates else None,
        "destination_url": candidates[0]["destination_url"] if candidates else None,
        "candidates": candidates,
        "reason": "Road ownership (city / county / FDOT state road) could not be established from GPS alone. "
                  "Confirm which agency maintains this road before reporting.",
        "sources": [s for a in cands for s in a["sources"]],
    }
