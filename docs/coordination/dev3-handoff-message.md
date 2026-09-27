# Developer 3 (vision/AI) → Developer 2 (backend) and Developer 1 (iOS)

Paste this into your coding agent.

```
Message from Developer 3 (vision/AI) for the PotPatrol backend integration.

CONFIRMED CONTRACT
- analysis.json has "schema_version": 1. Full contract: docs/contracts/analysis.md, examples in docs/contracts/examples/.
- Branch: dev3/vision-worker
- Install: pip install -e worker

IMPORTS
  from potpatrol_vision import analyze, AnalysisError, InvalidVideoError, ModelError
  from potpatrol_vision.report import draft_report
(The old name roadwatch_vision is a temporary alias. Use potpatrol_vision.)

ANALYZE
  manifest = analyze(video_path, output_dir)   # writes output_dir/analysis.json + output_dir/evidence/*.jpg
  CLI: python -m potpatrol_vision VIDEO_PATH OUTPUT_DIR
- One event per physical pothole. Each has: video_offset_ms (int, ms from the first decoded video frame),
  category ("pothole"), confidence (0-1), evidence_path (relative to output_dir), plus optional:
  event_id, first_seen_ms, last_seen_ms, status ("confirmed" | "needs_review"), hits, bbox, evidence_raw_path, notes.
- A clean clip returns events: [] with exit code 0.
- Failures never look like "0 hazards": InvalidVideoError = exit 2, ModelError = exit 3, other errors = exit 1.
  No analysis.json is written on failure; stderr has one JSON line {"schema_version":1,"error":{"type","message"}}.
  Mark the job failed in that case.
- Map video_offset_ms to wall time using the recording start of the first frame, then interpolate GPS there.

FIXTURE (deterministic, for integration and demo fallback)
  python -m potpatrol_vision any_path OUTPUT_DIR --fixture
  or env POTPATROL_ANALYSIS_MODE=fixture, or analyze(video_path, output_dir, fixture=True)
  -> 2 events + 4 JPEGs, "mode": "fixture", exit 0. Video path is ignored.

DRAFT_REPORT
  draft_report(hazard, evidence_path, lat, lon, accuracy_m, observed_at)
  Optional keyword-only: user_reviewed=False, address=None, owner_hint=None
- lat, lon, accuracy_m, observed_at and evidence_path may each be None.
- Missing lat or lon -> destination_status "needs_review", candidates [], destination_url null,
  coordinates and location_description null.
- Location outside supported coverage (currently Miami-Dade) -> destination_status "unsupported", destination_url null.
- Inside Miami-Dade -> "needs_review" with 3 candidates (Miami-Dade County 311, City of Miami, FDOT District 6),
  because GPS alone cannot prove road ownership.
- "verified" only when an ownership source is passed via owner_hint={"agency_id": ..., "source": url}.
- Missing observed_at -> observation_time value null; the time is left out of the description.
- Every field is {"value", "source"}. severity is always null in v1. submission_status is always "not_submitted";
  only a real agency confirmation number may mark a report submitted (backend-owned).
- Examples: docs/contracts/examples/report.example.json and report.missing-location.example.json

FOR DEVELOPER 1 (iOS)
- Per event show: category, confidence, status (style "confirmed" and "needs_review" differently), evidence JPEG, time.
- Destination: let the user pick from the candidates when status is "needs_review".
  Opening the agency page is a handoff; never show "submitted" without a confirmation number.
- Dev 3 needs: one short (30-90 s) clip passing a real pothole and one smooth-road clip, both from the real phone mount,
  and how the app records the recording start time of the first frame.

ACTION
- Build your adapter against fixture mode now.
- Ack rows 1-4 in docs/coordination/changes.md.
```
