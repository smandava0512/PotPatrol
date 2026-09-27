# PotPatrol analysis worker contract — schema_version 1

Owner: Developer 3 (vision / AI / reporting). Consumers: Developer 2 (backend), Developer 1 (app, via backend).
Status: **v1 proposed**. Changes go through `docs/coordination/changes.md`.

## 1. Call signature

Python (preferred for the FastAPI job runner):

```python
from potpatrol_vision import analyze, AnalysisError

manifest: dict = analyze(video_path, output_dir)   # also writes output_dir/analysis.json
```

CLI (same behavior, for subprocess execution):

```
python -m potpatrol_vision VIDEO_PATH OUTPUT_DIR [--fixture] [--sample-fps 4] [--conf 0.35] [--device cpu|0]
```

- `output_dir` is created if missing. The worker writes only inside it:
  `analysis.json`, `evidence/event-NNN.jpg` (annotated), `evidence/event-NNN-raw.jpg` (clean frame).
- **Fixture mode** (`--fixture` or env `POTPATROL_ANALYSIS_MODE=fixture`): ignores the model and returns the deterministic
  manifest in `docs/contracts/examples/analysis.example.json` plus evidence JPEGs. Use it for backend/app integration
  and as the live-demo fallback. The fixture manifest has `"mode": "fixture"`, so it can never be confused with a real result.

## 2. Success vs. failure (never conflate a crash with "0 hazards")

| Outcome | Python | CLI exit | `analysis.json` |
| --- | --- | --- | --- |
| Valid clip, hazards found | returns manifest | `0` | written, `events: [...]` |
| Valid clip, no supported hazards | returns manifest | `0` | written, `events: []` |
| Unreadable/missing/zero-frame video | raises `InvalidVideoError` | `2` | **not written** |
| Model missing / wrong classes / inference crash | raises `ModelError` | `3` | **not written** |
| Anything else unexpected | raises `AnalysisError` | `1` | **not written** |

On failure, the CLI prints one JSON line on **stderr**:
`{"schema_version": 1, "error": {"type": "invalid_video" | "model_error" | "internal_error", "message": "..."}}`.
The backend should mark the job failed and must not create an empty-hazard drive from a failure.

## 3. Manifest (`analysis.json`)

```json
{
  "schema_version": 1,
  "mode": "model",
  "video": { "duration_ms": 61233, "frames_decoded": 1837, "frames_sampled": 245, "sample_fps": 4.0, "rotation_deg": 90 },
  "model": { "name": "peterhdd/pothole-detection-yolov8", "weights_sha256": "…", "classes": ["pothole"], "conf_threshold": 0.35 },
  "processing_ms": 18400,
  "events": [
    {
      "event_id": "event-001",
      "video_offset_ms": 36700,
      "first_seen_ms": 36100,
      "last_seen_ms": 37200,
      "category": "pothole",
      "confidence": 0.89,
      "status": "confirmed",
      "hits": 4,
      "bbox": [0.52, 0.61, 0.71, 0.74],
      "evidence_path": "evidence/event-001.jpg",
      "evidence_raw_path": "evidence/event-001-raw.jpg",
      "notes": "Detected in 4 sampled frames over 1.1 s; box in lower-right of frame"
    }
  ]
}
```

### Field rules

| Field | Type | Rule |
| --- | --- | --- |
| `schema_version` | int | `1`. Bumped only on a breaking change. |
| `mode` | `"model"` \| `"fixture"` | Fixture results must never be shown as real detections. |
| `video_offset_ms` | int ≥ 0 | Timestamp of the **evidence frame**. Backend interpolates GPS at this offset. |
| `first_seen_ms`, `last_seen_ms` | int | `first_seen_ms ≤ video_offset_ms ≤ last_seen_ms`. |
| `category` | enum | v1: `"pothole"` only. Future categories (`debris`, `road_damage`) are added only after measured quality and a coordination entry. Backend should store unknown categories as text, not crash. |
| `confidence` | float `[0,1]` | Max detector confidence among the event's frames (rounded to 3 dp). |
| `status` | `"confirmed"` \| `"needs_review"` | `confirmed` = seen in ≥ `min_hits` sampled frames. `needs_review` = single strong frame only. The app should label these differently. |
| `hits` | int ≥ 1 | Number of sampled frames supporting the event. |
| `bbox` | `[x1,y1,x2,y2]` floats `[0,1]` | Normalized to the **display-oriented** evidence image. |
| `evidence_path` | relative path | JPEG under `output_dir`, with the detection box drawn. Always exists when the manifest is written. |
| `evidence_raw_path` | relative path | Same frame, without annotations (for reports / optional validation). |
| `notes` | string | Factual detector-derived text only. No claims about lane, size, depth, ownership or risk. |
| `validation` | object, **optional** | Present only when the optional image check ran and succeeded: `{is_hazard: bool, confidence: [0,1], rationale: str, provider: str, model: str}`. Advisory only: it never removes an event or changes `status`. Absent = not checked. |

Top-level `validator` is `null` when the optional check is off, or `{provider, model}` when it is on. The check runs only in
model mode, only on the `POTPATROL_VALIDATE_MAX` (default 5) highest-confidence events, and only on `evidence_raw_path`.
It is enabled with `POTPATROL_VALIDATOR=gemini` + `GEMINI_API_KEY`. Any provider error means no `validation` field; the job never fails because of it.

Bounds: at most **25** events per clip (highest scores kept). Events are sorted by `video_offset_ms`.

### Explicit `gemini_required` vision mode (staged; not deployed)

`POTPATROL_VISION_MODE=gemini_required` requires `POTPATROL_ANALYSIS_MODE=model` and a private `GEMINI_API_KEY`. It rejects fixture runs, missing SDK/key, incomplete API responses and >12 YOLO event candidates rather than returning success. It sends at most 24 PTS-selected frame JPEGs throughout each clip and at most 12 raw YOLO evidence JPEGs to Gemini (no video or metadata). It validates every retained YOLO event, drops Gemini-rejected candidates, and scans even zero-YOLO clips for missed damage. Results from Gemini alone have category `pothole` or `road_damage`, `source=gemini_scan`, confidence from that image response, a boxed frame JPEG and `status=needs_review`; validated YOLO results have `source=yolo_gemini_validated` and `status=needs_review`. `road_damage` is additive to the v1 category enum; consumers should handle category as text. The report draft for that category says "Possible road damage". Top-level additive `vision_mode=gemini_required` and `gemini_frames_scanned` record the path used, while existing `model` and `validator` name both actual systems. This does not claim measured accuracy or human confirmation.

### Time origin

All `*_ms` values are **milliseconds from the first decoded video frame's presentation timestamp (PTS)**:
`(frame.pts - first_frame.pts) * time_base * 1000`. This is not wall-clock time or FFmpeg processing time, and it is
not a frame index × nominal FPS, so it stays correct for iPhone variable-frame-rate video. The backend maps offset → wall
time using the recording start time the app captured for the first frame, then interpolates GPS.

## 4. Report module

```python
from potpatrol_vision.report import draft_report
report = draft_report(hazard, evidence_path, lat, lon, accuracy_m, observed_at)
# lat / lon / accuracy_m / observed_at / evidence_path may each be None.
# Optional keyword-only: address={"display": ...}, owner_hint={"agency_id", "source"}, user_reviewed=False
```

- Missing `lat` or `lon`: `destination_status = "needs_review"`, no candidates, and `coordinates` / `location_description` are `null`.
- Location outside registry coverage: `destination_status = "unsupported"` with `destination_url = null`.
- Missing `observed_at`: `observation_time.value = null` and the time is left out of the description (never the string "None").

It returns editable structured fields. Each field is `{"value": ..., "source": ...}`, where `source` is one of
`detector | gps | device_clock | reverse_geocode | registry | template | user | validator | unassessed`.
See `examples/report.example.json`.

- `ai_check` (optional pass-through of the event's `validation`, source `validator`, else `null` / `unassessed`). It is advisory and never changes `description`.
- `category`, `observation_time`, `location_description`, `description`, `severity` (always `null` in v1, with basis
  `"not assessed from a single camera frame"`), `evidence_path`.
- `destination`: `{ jurisdiction_candidate, destination_url, destination_status, candidates[], reason, sources[] }`
  - `destination_status`: `verified` (ownership established by registry rule **and** URL verified from an official page, with a
    source URL and check date), `needs_review` (candidates shown to the user; ownership not established), `unsupported` (outside
    registry coverage).
- `submission_status` is always `"not_submitted"`. The worker only produces a draft and a browser handoff link.
  Only a real portal receipt/confirmation number entered or received later may set `submitted`, and that state belongs to the backend.

## 5. Versioning

Additive optional fields may be added without a version bump. Consumers must ignore unknown fields. Renames, removals, or
semantic changes bump `schema_version` and require acknowledgement from both teammates first (see coordination rules).
