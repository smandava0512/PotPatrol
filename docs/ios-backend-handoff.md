# iOS capability handoff

The iOS package now implements the three requested integration primitives. This document records app behavior and questions for the backend owner; it does not replace the backend's canonical API contract.

| Capability | App behavior |
| --- | --- |
| Video | Raw MP4 bytes in an HTTPS PUT; preserve the backend URL and required headers, including `Authorization` when provided. Default content type is `video/mp4`. |
| Upload result | Accept 2xx; surface redirects/non-2xx/network errors; retain the MP4 for retry. Do not mark server analysis complete from a PUT response. |
| GPS time origin | `offset_ms = round((GPS measurement host time - first successfully written video-frame host time) * 1000)`. The first frame's source PTS also starts the MP4 writing session. |
| GPS payload proposal | `offset_ms`, UTC `recorded_at`, WGS84 `latitude`/`longitude`, `horizontal_accuracy_m`, nullable `speed_mps`/`heading_deg`. These names come from the attached plan's initial proposal and await the canonical contract. The sender takes a caller-supplied POST request and JSON envelope encoder. |
| Missing GPS | Empty valid sample array; retain video. No synthetic coordinates. Backend acceptance and completion semantics still need agreement. |
| Hazard location | Coordinates may be absent. Category, evidence and video offset remain visible; show “Location unavailable” and require manual location review. |

## Needed from the backend contract

1. Upload response field names for URL, method, required headers, expiration, and expected success status. Confirm how expired authentication is refreshed and whether PUT retries overwrite the same object safely.
2. The location endpoint's request envelope, batch limits, idempotency/deduplication rules, and an example with zero samples. Confirm first-recorded-frame offsets and UTC timestamp precision.
3. A hazard response fixture with no GPS: confirm missing/null coordinate representation, evidence URL access/expiry, and report/jurisdiction status when location is unavailable.
4. The completion call and ordering guarantees: upload video and GPS successfully, then request analysis. Confirm how no-GPS drives are finalized.

No endpoint paths or hazard JSON keys have been implemented. Add a contract-specific adapter when the backend schema and fixtures are published; supply its authenticated GPS POST request and envelope encoder, and map missing coordinates to nil instead of force-unwrapping or defaulting to zero.

## Validation status

Swift unit tests, including a synthetic MP4 round trip, and the hazard view build [passed on GitHub's macOS runner](https://github.com/smandava0512/potholepatel/actions/runs/36268702885). CI also includes an iPhone Simulator SDK compile check. Real authenticated upload/GPS delivery, physical camera/GPS timing, and persistence remain integration work.

## Apple references

- [File-backed URLSession upload](https://developer.apple.com/documentation/foundation/urlsession/upload(for:fromfile:delegate:))
- [AVAssetWriter session start](https://developer.apple.com/documentation/avfoundation/avassetwriter/startsession(atsourcetime:))
- [Capture output synchronization clock](https://developer.apple.com/documentation/avfoundation/avcapturesession/synchronizationclock)
- [Clock conversion](https://developer.apple.com/documentation/coremedia/cmsyncconverttime(_:from:to:))
- [CoreLocation horizontal accuracy](https://developer.apple.com/documentation/corelocation/cllocation/horizontalaccuracy)
