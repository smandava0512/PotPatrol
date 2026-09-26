# Pot Patrol — iOS compatibility

This consumer note follows Developer 2's [published v1 contract](https://github.com/smandava0512/PotPatrol/blob/2392ff54b977ff78a0dfe312f15e1236b741ef89/docs/contracts/api.md). The app/tests target that snapshot. The owner must publish additions before adoption.

| Capability | App behavior |
| --- | --- |
| Video | H.264 MP4; raw file-backed PUT with backend headers plus same-origin `X-Device-Token`. |
| GPS | `{samples:[...]}`, max 2,000/batch; WGS84/meters/integer ms/UTC. Duplicate rounded offsets choose best accuracy; retries are stable/idempotent. |
| Heading | Valid values local only; omitted from v1 wire. |
| Origin | First successfully written frame; source PTS and GPS host-clock zero are the same frame. |
| First-frame UTC | Immediately saved to `capture-origin.json`, then finalized `videoStartedAt`. Local observation time = first-frame UTC + video offset. |
| Complete | Video/GPS succeed first; body exactly `{}`. Empty GPS supported. Proposed metadata not sent. |
| Recovery | Persist server ID, transfer receipt, GPS index, status/errors, evidence and edits. Poll same drive on reopening. |
| Evidence | Same-origin authenticated GET/private cache; reject foreign origins to protect device token. |
| Missing location | Keep hazard/evidence/time; show Location unavailable, no invented pin. Editable/shareable report. |
| Destination | Nested `destination:{status,url}`. Verified HTTPS + valid location required for portal. `needs_review`/unknown/unverified/unsupported remain disabled. |
| Analysis mode | Optional `analysis_mode` is retained if returned. `fixture` labels saved drives, results, hazard details, reports and copied/shared text as synthetic. An absent mode remains unknown. |
| Unsupported | Explicit message; save/edit/share remain available. Isolated demo fixture exercises it, not current server emission. |
| Submission | Draft / portal opened / actual user receipt. Portal opening never confirms submission. |

## Pending additions

Developer 2 clarified on 2026-09-26: keep sending `{}` until the pushed contract is supplied; optional `video_started_at` will carry first-frame UTC afterward. The app captures UTC now and keeps it local. Await the published endpoint/schema, UTC precision and observation-time fixtures before sending the field. Missing origins must stay unknown; never substitute create/upload time.

Developer 2 confirms `location:null` and nested `destination.status` (`needs_review` or `unsupported`); these are already supported. Developer 3's structured fields and `destination_status`/`destination_url` names need Developer 2's canonical mapping before adoption. Draft edits are local until an update endpoint exists. Developer 2 also announced `analysis_mode:"fixture"`; the app can read and label it without requiring it from the pinned v1 server. Confirm the deployed server uses real analysis for phone acceptance. [Discord notes](coordination/changes.md) are pending human forwarding/owner acknowledgment.
