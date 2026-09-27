# Pot Patrol — iOS compatibility

This consumer note follows the [merged v1 contract](contracts/api.md). The iOS contract test runs the merged backend and the explicitly synthetic fixture worker; physical-camera and real-model acceptance remain separate.

| Capability | App behavior |
| --- | --- |
| Video | H.264 MP4; raw file-backed PUT with backend headers plus same-origin `X-Device-Token`. |
| GPS | `{samples:[...]}`, max 2,000/batch; WGS84/meters/integer ms/UTC. Duplicate rounded offsets choose best accuracy; retries are stable/idempotent. |
| Heading | Valid values local only; omitted from v1 wire. |
| Origin | First successfully written frame; source PTS and GPS host-clock zero are the same frame. |
| First-frame UTC | Immediately saved to `capture-origin.json`, then finalized `videoStartedAt`. Server observation time = first-frame UTC + video offset when supplied. |
| Complete | Video/GPS succeed first; send `video_started_at` from the first appended frame when known, otherwise `{}`. Empty GPS supported. |
| Upload consent | Real MP4 and optional GPS stay local until the user chooses **Send video and GPS for analysis**. Approval is bound to the selected server and survives a retry; old saved drives without approval do not auto-upload. |
| Recovery | Persist server ID, consented origin, transfer receipt, GPS index, status/errors, evidence and edits. Poll same drive on reopening. Foreground transfers interrupted by termination restart from retained media rather than continuing in the background. |
| Evidence | Same-origin authenticated GET/private cache; reject foreign origins to protect device token. |
| Missing location | Keep hazard/evidence/time; show Location unavailable, no invented pin. Editable/shareable report. |
| Destination | Decode nested status/url/candidates/reason/sources. Valid unchanged coordinates plus an explicit candidate selection allow a `needs_review` HTTPS agency handoff without upgrading ownership status. Verified HTTPS destinations also work; unknown/unverified/unsupported remain disabled. |
| Analysis mode | Optional `analysis_mode` is retained if returned. `fixture` labels saved drives, results, hazard details, reports and copied/shared text as synthetic. An absent mode remains unknown. |
| Unsupported | Explicit message; save/edit/share remain available. Isolated demo fixture exercises it, not current server emission. |
| Submission | Draft / portal opened / actual user receipt. Portal opening never confirms submission. |
| Draft refresh | Explicit re-fetch replaces the cache after user confirmation and retains receipt history. Developer 2 owns flattening fields, including previously persisted server drafts. |
| Sharing | Text and available evidence photo by default. Full drive video is opt-in and defaults off. |

## Remaining acceptance

Missing origins stay unknown; never substitute create/upload time. The backend adapts Developer 3's structured report fields to plain strings and flat coordinates, repairing old server drafts on re-fetch. Draft edits remain local until an update endpoint exists. Confirm the deployed worker uses real analysis for phone acceptance; `analysis_mode:"fixture"` identifies synthetic results. The [coordination log](coordination/changes.md) keeps historical decisions and acknowledgments.
