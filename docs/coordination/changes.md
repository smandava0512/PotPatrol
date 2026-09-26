# Developer 1 coordination

Consumer compatibility notes; no canonical backend/analyzer contract is changed. The human will copy these to Discord. No direct message was sent.

## 2026-09-26 — Adopt v1; retain pending UTC locally

Published v1 adopted. Additive UTC field/report-shape proposals await owner publication. Affects Developers 1, 2 and 3.

| Earlier proposal | Current contract / decision | Migration |
| --- | --- | --- |
| Optional heading | v1 forbids wire heading | Keep locally; add after schema publication |
| Completion metadata | v1 accepts `{}` | Store locally until additive fields published |
| Absolute UTC absent on wire | Developer 2 proposes capture field | Capture now; await exact name/type/endpoint and response |
| Report shape under discussion | Nested `{status,url}` destination | Graceful unknown statuses; agreed adapter before flat shape |
| Auth initially unknown | X-Device-Token for JSON/PUT/private evidence | Privately provision into Keychain |

No endpoint/unit changes proposed. Copied package fixtures are labeled synthetic.

Developer 3's published `dev3-vision` proposal was inspected. Its report uses structured `{value,source}` fields and `destination:{destination_status,destination_url,candidates,...}`; the live v1 backend returns plain `fields` and `destination:{status,url}`. Developer 2 must map these shapes before the app can consume candidates or field provenance. The proposed report callable also takes evidence, coordinates, accuracy and observation time, while v1 expects a single hazard argument. No alternate report request is sent by the app. Please also preserve an explicit fixture/model indicator when the analyzer is connected so server fixtures cannot be mistaken for live detection.

### Copy to Developer 2

> Developer 1 / Pot Patrol: yes, iOS supports raw MP4 PUT with X-Device-Token, {samples:[...]}, integer GPS offsets from the first successfully written frame, idempotent GPS retries, and private authenticated evidence. We omit heading_deg; /complete remains {}. First-frame UTC is captured immediately and survives reopening. Please publish the additive field's exact name/type/endpoint and observation-time fixture before we send it. Missing GPS keeps the hazard visible. Unsupported destination keeps the draft editable/shareable and disables portal opening. Current adapter reads nested destination:{status,url}. Please provide HTTPS base URL and device token privately. Transport tests passed against your pinned backend with the synthetic fixture worker; final phone acceptance needs the real analyzer.

### Copy to Developer 3

> Developer 1 / Pot Patrol: retain hazards without GPS using nullable location; UI keeps evidence/category/time and shows Location unavailable. Confidence/severity appear only when supplied. Unsupported/unverified destinations keep editable/shareable drafts without portal/submission claims. Route report-shape changes through Developer 2's canonical API/fixtures; app reads nested destination:{status,url}. UTC is captured locally for start UTC + video offset once the additive field is published. We need one real pothole clip and one clean clip for analyzer acceptance; the human will record as a passenger or while parked. Our bundled backup and transport analyzer are explicitly synthetic.

### Human capture request

Record two short original clips as a passenger or while parked: one real pothole and one clean stretch. Keep originals and share privately with Developers 2 and 3. App captures also retain GPS and first-frame UTC. See [checklist](../ios-demo-checklist.md).
