# PotPatrol API v1 — Developer 2 contract

Base URL: `http://127.0.0.1:8000` locally. JSON endpoints require `X-Device-Token: <POTPATROL_DEVICE_TOKEN>` (demo device access); configure a nonempty token before starting. The authenticated upload PUT requires the same header. IDs are UUIDs. Times are absolute UTC ISO 8601 (`Z`); offsets in integer milliseconds from the **first actual recorded video frame**, not app launch or upload time. Locations are WGS84 phone positions, not surveyed pothole coordinates. Unknown accuracy, speed, severity, and location are `null`.

| Call | Request | Success |
| --- | --- | --- |
| `POST /v1/drives` | `{}` | `201 {"drive_id": UUID, "status":"created"}` |
| `POST /v1/drives/{id}/upload-init` | `{}` | `200 {"upload_url": absolute authenticated local URL, "method":"PUT", "headers":{"Content-Type":"video/mp4"}, "expires_at": UTC time}` |
| `PUT /v1/drives/{id}/video` | MP4 body, `Content-Type: video/mp4`, device token | `204` |
| `POST /v1/drives/{id}/locations` | `{"samples":[{"offset_ms":0,"recorded_at":"2026-09-26T12:00:00Z","latitude":25.7617,"longitude":-80.1918,"horizontal_accuracy_m":5.0,"speed_mps":4.0}]}` | `200 {"accepted":1}`; identical repeated offset is idempotent, conflicting repeat is `409` |
| `POST /v1/drives/{id}/complete` | `{}` | `200 {"drive_id":UUID,"status":"queued"}` (or current status if already queued/processing/complete); `409` if video absent |
| `POST /v1/drives/{id}/retry` | `{}` | `200 {"drive_id":UUID,"status":"queued"}` only after `failed` |
| `GET /v1/drives/{id}` | — | `200 {"drive_id":UUID,"status":enum,"stage":string/null,"error":string/null,"hazards":[...]}` |
| `GET /v1/hazards/{id}/evidence` | — | private authenticated JPEG |
| `POST /v1/hazards/{id}/report-draft` | `{}` | persisted editable draft package (`report_id`, `fields`, `destination`, `submission_status`) |
| `GET /health` | — | `{"status":"ok"}` (no auth) |

Status enum: `created`, `uploading`, `queued`, `processing`, `complete`, `failed`. `GET` hazard: `hazard_id`, `category`, `confidence` [0,1], `severity` nullable, `severity_basis` nullable, `evidence_url` (authenticated API path), `video_offset_ms`, `location` nullable (`latitude`, `longitude`, `horizontal_accuracy_m`, `source":"phone_interpolated"|"phone_sample"`), `review_state` (`needs_review`). Missing/low-quality GPS yields `location:null`. Report destination defaults to `{ "status":"unverified", "url":null }`, never implies submission; `submission_status:"not_submitted"`. A portal handoff is not submission. Errors use HTTP status with `detail`.

Limits: max MP4 size 100 MiB, max duration 10 minutes (if readable by ffprobe), max 2000 location samples per batch, offset <= 600000 ms. Raw video never has a public URL. The upload URL expires in 15 minutes; request a new upload-init to renew. Completing with no GPS is allowed and yields location-unavailable hazards. For local development use SQLite by default; set `POTPATROL_DATABASE_URL` to a Postgres URL for local/hosted Postgres. No extensions required. `POTPATROL_DEVICE_TOKEN`, `POTPATROL_STORAGE_DIR`, `POTPATROL_ANALYZER`, `POTPATROL_REPORTER`, and optional `POTPATROL_S3_BUCKET`/`POTPATROL_S3_PREFIX`/`POTPATROL_S3_ENDPOINT_URL` configure the service. Legacy `ROADWATCH_*` settings remain accepted as fallback for existing deployments; new names take precedence.

Worker handoff (Developer 3): `analyze(video_path, output_dir) -> analysis.json` callable via `POTPATROL_ANALYZER=module:function`, producing local JPEGs and JSON `{ "schema_version":1, "events":[{"video_offset_ms":1000,"category":"pothole","confidence":0.9,"evidence_path":"evidence/one.jpg","first_seen_ms":900,"last_seen_ms":1200,"notes":"optional"}] }`. One event per physical hazard. We validate schema, event ranges and local evidence paths, save one hazard/evidence per event, and associate GPS. Optional report module interface is `draft_report(hazard: dict) -> {"fields":object,"destination":{"status":"unverified"|"verified"|"unknown","url":string|null}}`; absent module uses a safe local editable draft. Coordinate signature changes before integrating. Fixture mode (`POTPATROL_ANALYZER=potpatrol.fixture_worker:analyze`) is demo-only and must not be presented as real inference. Worker is a separate `python -m potpatrol.worker --once` / `--loop` process.

See `docs/contracts/examples.json` and generated `docs/contracts/openapi.json`. Developer 1: confirm auth and PUT support, use device token from local secret provisioning, and show `location:null` clearly. Developer 3: confirm schema version, single-event clustering, safe relative JPEG paths, and report adapter signature. There is no team messaging channel yet; forward this contract link to both teammates before client/worker integration.
