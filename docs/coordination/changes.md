# Developer 1 coordination

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
