# Developer 1 coordination

Historical consumer notes. For the merged backend contract, see the contract-change history below and `docs/contracts/api.md`.

Consumer compatibility notes; no canonical backend/analyzer contract is changed. The human will copy these to Discord. No direct message was sent.

## 2026-09-26 — Adopt v1; retain pending UTC locally

Published v1 adopted. Additive UTC field/report-shape proposals await owner publication. Affects Developers 1, 2 and 3.

| Earlier proposal | Current contract / decision | Migration |
| --- | --- | --- |
| Optional heading | v1 forbids wire heading | Keep locally; add after schema publication |
| Completion metadata | v1 accepts `{}` | Store locally until additive fields published |
| Absolute UTC absent on wire | Developer 2 confirms optional `video_started_at` after contract push | Capture locally; continue `{}` until the pushed schema is supplied |
| Report shape under discussion | Nested `{status,url}` destination | Graceful unknown statuses; agreed adapter before flat shape |
| Auth initially unknown | X-Device-Token for JSON/PUT/private evidence | Privately provision into Keychain |
| Fixture provenance absent on wire | Developer 2 announces `analysis_mode:"fixture"` | Read it when returned; persist and warn on screens and shared text |

No endpoint/unit changes proposed. Copied package fixtures are labeled synthetic.

Developer 3's published `dev3-vision` proposal was inspected. Its report uses structured `{value,source}` fields and `destination:{destination_status,destination_url,candidates,...}`; the live v1 backend returns plain `fields` and `destination:{status,url}`. Developer 2 must map these shapes before the app can consume candidates or field provenance. The proposed report callable also takes evidence, coordinates, accuracy and observation time, while v1 expects a single hazard argument. No alternate report request is sent by the app.

Developer 2's relayed clarification confirms `location:null`, nested `destination.status` with `needs_review`/`unsupported`, optional `video_started_at` after the contract push, and `analysis_mode:"fixture"` for fixture results. This clarification does not publish a new request schema. Completion still sends `{}`. Reading the optional mode is backward compatible; absent mode is not proof of real analysis.

### Copy to Developer 2

> Developer 1 / Pot Patrol: acknowledged. /complete stays {} until you send the pushed contract. First-frame UTC is captured immediately and survives reopening; optional video_started_at can use that value once the schema is published. location:null keeps hazards visible. Nested destination.status needs_review/unsupported keeps drafts editable/shareable and portal opening disabled. Optional analysis_mode:"fixture" is retained and clearly labeled on screens and copied/shared reports; an absent mode is not treated as proof of real analysis. Authenticated MP4 PUT, GPS retries and private evidence passed against your pinned backend with its synthetic worker. Please send the pushed contract plus HTTPS base URL/device token privately; final phone acceptance needs the real analyzer and two real clips.

### Copy to Developer 3

> Developer 1 / Pot Patrol: retain hazards without GPS using nullable location; UI keeps evidence/category/time and shows Location unavailable. Confidence/severity appear only when supplied. Nested destination.status needs_review/unsupported keeps editable/shareable drafts without portal/submission claims. Route report-shape changes through Developer 2's canonical API/fixtures. UTC is captured locally for start UTC + video offset; completion remains {} until optional video_started_at is published. Server analysis_mode:"fixture" receives an explicit synthetic warning. We need one 30–60 second real pothole clip and one clean clip for analyzer acceptance; record as a passenger or while parked. Bundled backup and transport analysis are synthetic.

### Human capture request

Record two short original clips as a passenger or while parked: one real pothole and one clean stretch. Keep originals and share privately with Developers 2 and 3. App captures also retain GPS and first-frame UTC. See [checklist](../ios-demo-checklist.md).

## 2026-09-27 — Developer 3 pre-demo report feedback

Developer 1's consumer fixes are on `codex/developer-1-pot-patrol-ios` at `f6e47f9`. Explicit Refresh draft bypasses the local cache and replaces it after confirmation; earlier receipts remain in history. Candidate agency names/URLs/sources and reason are shown. A local user selection enables a `needs_review` HTTPS agency handoff while retaining the server status and unverified ownership. Coordinate review clears when the original values are restored; missing and null compare equally. Full drive video is off by default; text and available evidence are shared unless the user explicitly includes video.

[CI 36293356119](https://github.com/smandava0512/PotPatrol/actions/runs/36293356119) passed: 33 unit checks, the separate synthetic-worker HTTP integration, native Release compilation, and all six simulator UI scenarios. This validates the consumer changes, not physical real-model acceptance.

Developer 2 owns flattening `{value,source}` fields to category/description/latitude/longitude, including previously persisted server drafts. Refresh can only show the fields the server actually returns; no client-side structured-field migration was added. The existing completion body remains `{}`.

Changes #1–#5 were acknowledged directly on `dev3-vision` in [19a4b2a](https://github.com/smandava0512/PotPatrol/commit/19a4b2a1af6d6f863d3a6615ff83d07c1d9833df). Developer 2's pending acknowledgments/data-sharing approval were preserved. Optional advisory AI metadata remains compatible, without claiming it is user confirmation or activating an external provider.

Public `https://api.potpatrol.miami/health` returned `status:ok`. Authenticated checks of the supplied test UUID returned a complete fixture drive with two potholes without GPS. Private evidence and its report draft returned HTTP 200; category/description are now plain strings, latitude/longitude explicit nulls, destination `needs_review` with no candidates, submission `not_submitted`. The deployed fixture's flattened fields are verified; no real-model app acceptance is claimed. Credentials and media were not saved. New app uploads already obtain and persist their own UUID from `POST /v1/drives`.

The iPhone is available; the Mac can be available but needs Xcode and signing setup. Follow [first-time Mac setup](../ios-first-mac-setup.md), then capture real pothole/clean clips safely and verify a model result on the phone.

### Current copy to Developer 2 / Developer 3

> Developer 1 / Pot Patrol: all four report fixes are pushed on f6e47f9, with 33 unit checks and six simulator UI scenarios passing. Acks #1–#5 are on dev3-vision at 19a4b2a. Authenticated checks of the supplied test UUID confirm two fixture potholes without GPS and working private evidence. Its deployed report now has plain category/description and explicit null coordinates; use Refresh draft for old local caches. New uploads get IDs from POST /v1/drives. Candidate choice remains needs_review and opening records Portal opened; full video is opt-in. Real-pothole app acceptance remains pending real clips/model inference and the first Mac/iPhone run. Xcode/signing setup instructions are ready.

---

# Contract changes

## Applied: PotPatrol naming (brand-only; no endpoint or JSON shape change)

- **Old → new:** `RoadWatch` display name → `PotPatrol`; Python package/worker path `roadwatch.*` → `potpatrol.*`; `ROADWATCH_*` environment settings → `POTPATROL_*`. Existing `ROADWATCH_*` settings remain accepted as fallback, with the new names taking precedence. `X-Device-Token`, `/v1/...` paths, offset semantics, worker manifest, and response fields are unchanged.
- **Reason:** project-wide rebrand requested by owner. **Affected:** both teammates' run instructions, Dev 3 worker integration, and deployment configuration. **Migration:** use `python -m potpatrol.worker` and `POTPATROL_ANALYZER=module:function`; existing environment variables keep working. API contract, generated OpenAPI title and fixtures must be updated together. No old import path is promised; coordinate any direct `roadwatch.*` imports before upgrading.
- **Notification:** pending human forwarding to Dev 1 and Dev 3; ask them to acknowledge the branding change before switching deployments. GitHub repository rename is separately pending with its admin.

The initial v1 contract is in `docs/contracts/api.md`. Any subsequent change to an endpoint, response shape, timestamp origin/unit, enum, auth, upload method, worker manifest, evidence policy, report fields or demo URL must record old → new, reason, impacted teams, compatibility/migration, and notification/acknowledgments here before breaking consumers. Until a direct channel is agreed, changes remain pending and a ready-to-forward notice goes to the human developer for both Developer 1 and Developer 3.

## Applied: additive first-frame time and Dev 3 report adapter (backend feature branch)

- **Old → new time:** `/complete` still accepts `{}`; it also accepts optional `video_started_at` (UTC time of first successfully written frame). `GET /drives/{id}` hazards add nullable `observed_at` calculated from the first-frame time plus Dev 3's `video_offset_ms`; no start time means null even if GPS timestamps exist. Store both in a nullable migration. Existing clients may keep sending `{}`; sending a conflicting time after completion yields 409. Shravya confirmed she captures the first-frame UTC time and will keep `{}` until this contract is available to her.
- **Old → new report:** The Dev 3 report module's exact Python signature is published in `docs/contracts/analysis.md`. `potpatrol.integration:draft_report` adapts it to the **existing nested** `destination` response; adds `needs_review` and `unsupported` states, candidates/reason/sources; verified URL only with ownership. Missing GPS remains a persisted hazard and yields `needs_review`/empty candidates; outside registry coverage yields `unsupported`. Existing no-reporter fallback remains `unverified`, so deployments must set `POTPATROL_REPORTER=potpatrol.integration:draft_report` for the new behavior. Reports remain `not_submitted`.
- **Worker:** `potpatrol.integration:analyze` invokes the pushed Dev 3 `potpatrol_vision` module, and `analysis_mode` exposes `fixture` vs `model` to the app. Fixture detections must never be presented as real. See `docs/contracts/examples/backend-additions.json` and regenerated OpenAPI. Dev 3's branch is not merged into main; its files have been imported on Dev 2's feature branch without touching others' branches.
- **Coordination:** Dev 1 acknowledged auth, upload, GPS offset, null location, editable unsupported drafts, first-frame UTC capture, and using `{}` until the optional field is published. Ask Dev 1 to consume this contract after it is pushed and Dev 3 to review this adapter's nested destination shape before either is considered a cross-team release.

## Prior proposals (resolved by the implementation above; retained for decision history)

- **Observation time:** Old `POST /v1/drives/{id}/complete` accepts `{}` and hazard/draft responses have no absolute observed time. Proposed: optionally accept `video_started_at` as UTC time of the first actual video frame, then persist `observed_at = video_started_at + video_offset_ms` on each hazard and draft. If omitted, `observed_at:null`; do not infer it from upload time or GPS. Reason: accurate date/time in editable reports, including drives without GPS. Affects Dev 1 upload metadata/types and Dev 3 draft input. Migration: additive nullable fields, keep `{}` valid until clients migrate; update API schema/fixtures together after both acknowledge.
- **Report handoff:** Old optional `draft_report(hazard: dict)` returns nested `fields` and `destination` (`verified`/`unverified`/`unknown`). Proposed adapter input remains `draft_report(hazard: dict, evidence_path: str, lat: float | None, lon: float | None, accuracy_m: float | None, observed_at: str | None)` (exact signature still to confirm with Dev 3). Dev 3 now specifies output keys `destination_status` (`verified` | `needs_review` | `unsupported`), `destination_url` (nullable), `candidates` (array), `submission_status` (`not_submitted`) and nullable time in report fields. No coordinates → `needs_review`, empty candidates, null URL; outside currently supported Miami-Dade → `unsupported`, null URL; inside Miami-Dade → `needs_review` with County 311, City of Miami, FDOT District 6 candidates, because GPS alone cannot prove road ownership; `verified` requires an explicit `owner_hint` ownership source. Missing `observed_at` yields null time and omits it from description. **Adapter decision pending:** normalize this flat output to a persisted public response (possibly nested `destination` for backward compatibility); never claim a report was submitted. Reason: Dev 1 needs accurate destination states and candidates; Dev 3 needs exact input fields. Affects both. Migration: update API docs/OpenAPI/fixtures together after acknowledgment; no live shape change yet.
- **Severity:** Old optional severity and severity_basis in hazards; proposed leave both null at detection until a defensible worker source exists. No API shape change. Affects both app display and worker expectations.
- **Worker:** Dev 3 confirms `analyze(video_path, output_dir)` returning `output_dir/analysis.json`, JPEGs relative to output_dir, one event per physical pothole, `events:[]` for clean clips, and errors for failed analysis. Still need confirmation of `schema_version:1`, importable Python module path, fixture invocation, and pushed code before integration. Extra event fields are ignored; category/confidence/offset/evidence remain unchanged.

**Historical notification status:** The proposals above were pending at the time. For this implementation, Shravya has confirmed the recorder/UI behavior; forward the finalized backend branch link and request Param's adapter review before claiming cross-team adoption.

## Dev 3 interface log (worker / report)

Any change to categories, manifest fields/types, offset origin, evidence files, model output semantics, report fields,
destination statuses, latency assumptions or deployment dependencies gets an entry here **before** it ships.
Keep the old shape working until both other developers acknowledge.

| # | Date | Owner | Interface | Old → New | Reason | Affected | Migration | Status / acks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-09-26 | Dev 3 | `analysis.json` v1 (initial) | — → schema v1 per `docs/contracts/analysis.md` | First publication. Adds `event_id`, `status` (`confirmed`/`needs_review`), `hits`, `bbox`, `evidence_raw_path`, `mode` beyond the brief's proposal. | Dev 2 (ingest/storage), Dev 1 (render `status`, evidence) | New interface; nothing to migrate. Consumers ignore unknown fields. | **Pending ack**: Dev 2 ☐ Dev 1 ☑ |
| 2 | 2026-09-26 | Dev 3 | Report fields v1 (initial) | — → `examples/report.example.json` | First publication. `destination_status ∈ {verified, needs_review, unsupported}`; `submission_status` always `not_submitted` from worker. | Dev 2 (store/serve), Dev 1 (edit form, destination picker) | New interface. | **Pending ack**: Dev 2 ☐ Dev 1 ☑ |
| 3 | 2026-09-26 | Dev 3 | Package / CLI / env var names (project renamed to PotPatrol) | `roadwatch_vision`, `python -m roadwatch_vision`, `ROADWATCH_*` → `potpatrol_vision`, `python -m potpatrol_vision`, `POTPATROL_*` | Team picked final name PotPatrol. | Dev 2 (imports, subprocess command, env vars) | Old names still work: `roadwatch_vision` is a deprecated alias package and `ROADWATCH_*` env vars are read as fallback. Manifest schema unchanged. Alias removed after ack. | **Pending ack**: Dev 2 ☐ Dev 1 ☑ |
| 4 | 2026-09-26 | Dev 3 (requested by Dev 2) | `draft_report` signature | `draft_report(event, gps_dict, observed_at, *, ...)` → `draft_report(hazard, evidence_path, lat, lon, accuracy_m, observed_at, *, address=None, owner_hint=None, user_reviewed=False)`; location/time/evidence nullable | Match Dev 2's adapter. Missing location → `needs_review` with no candidates; outside coverage → `unsupported`. | Dev 2 (caller), Dev 1 (null location/time display) | Old signature was never called (not yet pushed), so no shim needed. Report output fields unchanged, except that values can now be `null`. | Dev 2 ☑ (proposed it) Dev 1 ☑ |
| 5 | 2026-09-26 | Dev 3 | Optional Gemini image check (additive fields + optional deployment dependency) | — → event `validation` (optional), manifest `validator`, report `ai_check`, new provenance source `validator`; optional `google-genai` + `GEMINI_API_KEY` | Brief step 6: second opinion on a few evidence frames (e.g. manhole false positives) using Gemini instead of Snowflake. | Dev 2 (must approve sending evidence JPEGs to Google; set env in job runner if approved), Dev 1 (may show `ai_check` as advisory) | Additive: off by default (`POTPATROL_VALIDATOR` unset), so nothing changes until enabled. Consumers ignore unknown fields. | **Pending ack**: Dev 2 ☐ (incl. data-sharing OK) Dev 1 ☑ |
| 6 | 2026-09-27 | Dev 3 (PR #2 review) | Event merging semantics; evaluation mode | Tracks seen at the same time in the same horizontal band could be fused into one event → only sequential tracks (gap 0–1500 ms) are fused, so simultaneous potholes are separate events. `eval/evaluate.py` honored `POTPATROL_ANALYSIS_MODE=fixture` → always real model, validator off. | Reviewer reproduced merged simultaneous potholes and fixture results scored as the real detector. | Dev 2 (a clip may yield more events than before; still ≤ 25), Dev 1 (more hazard rows possible) | No schema change. HTTP `ai_check` is still always `unassessed` until Dev 2 stores event `validation` and passes it to the reporter (requested; see #5). | **Pending ack**: Dev 2 ☐ Dev 1 ☐ |

### Developer 1 acknowledgment — 2026-09-27

Dev 1 acknowledges changes #1–#5 as consumer compatibility. iOS changes are on `codex/developer-1-pot-patrol-ios` at `f6e47f9`; [macOS CI 36293356119](https://github.com/smandava0512/PotPatrol/actions/runs/36293356119) passed 33 unit checks, the separate synthetic-worker HTTP integration, native Release compilation and all six simulator UI scenarios.

- #1: consume backend hazard category/confidence/review state/evidence/first-frame offsets, keep missing locations visible, and label fixture analysis explicitly. Unknown additive manifest fields remain compatible.
- #2: consume the canonical nested API destination with candidates/reason/sources. Candidate choice is explicit and local; it never proves ownership or changes the server status. Opening an agency page records Portal opened. Dev 2 owns flattening report fields, including existing persisted drafts; Refresh draft re-fetches the server package and keeps earlier receipts in history.
- #3: Pot Patrol is the product name; use the `potpatrol_vision` / `POTPATROL_*` interface through the backend. iOS does not import the deprecated Python package.
- #4: acknowledge the published backend adapter signature and nullable location/time/evidence. The app does not call the worker directly or invent missing coordinates/timestamps.
- #5: acknowledge optional validation/validator/ai_check as additive advisory metadata; unknown fields decode without breaking the app. iOS does not enable Gemini, approve sending footage externally, or present its opinion as user confirmation. Dev 2's data-sharing approval and persistence/adapter work remain pending.

Authenticated acceptance on the supplied test UUID confirms a complete fixture drive with two potholes without GPS, HTTP 200 private evidence, and a report with plain category/description, explicit null latitude/longitude, `needs_review` and `not_submitted`. Real-model app acceptance is still pending: the iPhone is available, but the Mac needs Xcode/signing setup and a safely recorded real clip must produce a model result displayed in the app. No real detected pothole has been confirmed in the app yet. Full-video sharing is opt-in; text and available evidence are shared by default. New app uploads obtain and persist their UUID from `POST /v1/drives`.

### Developer 2 compatibility follow-up

- The backend adapter restores plain category/description strings and numeric/null latitude/longitude for the iOS v1 contract. Observation time stays structured; original worker field provenance is retained under `fields.provenance`. Old wrapped server drafts are repaired on re-fetch with the same ID, destination and submission status. The phone's Refresh draft action is still required for locally cached data.
- Change #5 is acknowledged as an optional/advisory interface only. **Sending evidence JPEGs to Google is not approved.** AWS explicitly keeps `POTPATROL_VALIDATOR=off`. Event validation is not yet persisted through the backend hazard model, so `ai_check` is not an end-to-end app feature.
- Validator configuration now fails closed: explicit disablement skips dotenv loading, failed dotenv loading skips the optional check, and invalid/negative image limits send no images. Offline regression tests cover these paths; no provider calls were made.
- Change #6 is compatible with the backend's bounded event ingestion; the latest full suite includes the simultaneous-pothole and evaluation-mode regressions. Fixture outputs remain synthetic, not real-video acceptance.
- Verified existing HTTPS fixture drive: `f1dda379-bf7c-47b1-a238-437ebcd74f61` (HTTP 200, complete, two synthetic hazards), accessible with its existing privately provisioned demo credential. New drives must use the UUID returned by POST /v1/drives, not this ID as a constant. Credentials never belong in this document.
