# RoadWatchKit

Requires Swift 5.9+, iOS 17+ or macOS 14+. Open `Package.swift` in Xcode on a Mac, or add this local package to the iOS app target. This is a library and a hazard detail view; camera permissions, the capture session, app navigation, persistent drive management, and backend endpoints still need to be integrated.

## Authenticated MP4 PUT

```swift
let instructions = UploadInstructions(
    url: uploadURLFromBackend,
    headers: ["Authorization": "Bearer \(shortLivedUploadToken)"]
)
let receipt = try await MP4Uploader().upload(fileURL: localMP4, instructions: instructions)
```

The body is the raw file, streamed through `URLSession.upload(for:fromFile:delegate:)`; there is no multipart envelope or base64 conversion. Pass exactly the backend-issued headers. Signed URLs and storage-specific headers also work. `Content-Type` defaults to `video/mp4` only when the backend did not supply it. URLs must use HTTPS. Authentication is per request; no token is embedded in source or applied to evidence URLs.

Only 2xx statuses produce a receipt. Redirects, 401/403, size rejection, and server errors surface to the caller. The file stays local, so the caller can retry with refreshed upload instructions. The helper uses foreground async transfers; background scheduling, retry policy, and app-relaunch recovery are not implemented yet. A PUT receipt does not queue analysis or mark a drive complete.

## First-frame GPS timing

Configure an `AVAssetWriter` with `.mp4`, add its video input, and process frames on one serial recording queue. Call `FirstVideoFrameWriter.append` exactly once with the first candidate video sample and the capture session's synchronization clock (`masterClock` on older SDKs). This helper starts the writing session at that sample's presentation timestamp and returns the origin only after a successful append. If that first frame cannot be written, it cancels the writer; create a new writer rather than keeping an incorrect zero point. Later frames must retain their original presentation timestamps.

```swift
let origin = try FirstVideoFrameWriter.append(
    sampleBuffer, to: writer, input: videoInput, captureClock: captureClock
)
// In CLLocationManagerDelegate.didUpdateLocations, collect all valid readings:
let correlation = CaptureTimeBridge.clockCorrelation()
let readings = locations.compactMap { CaptureTimeBridge.reading(from: $0, correlation: correlation) }
// After capture, using all accumulated readings and the finalized MP4 duration:
let samples = RecordingTimeline(origin: origin).samples(
    from: accumulatedReadings, durationMilliseconds: finalizedVideoDurationMs
)
let rawSampleArray = try JSONEncoder().encode(samples)
// The final backend adapter supplies the POST request and required JSON envelope:
let gpsReceipt = try await GPSBatchSender().send(samples, request: backendGPSRequest) {
    try backendGPSBodyEncoder($0)
}
```

The video timestamp is converted into host-clock time. Each GPS measurement's `CLLocation.timestamp` is correlated with host time when its callback arrives; callback latency does not become part of the offset. Integer `offset_ms` is rounded from the monotonic difference to the first recorded frame. Cached fixes before that frame, invalid fixes, and samples past the finalized video duration are excluded. Valid zero speed/heading stay zero; unavailable values become JSON null. Timestamps are UTC ISO 8601 with fractional seconds. A drive with no valid GPS encodes as an empty array.

Persist the finalized sample JSON as the GPS sidecar alongside the MP4 before upload. Raw host-clock readings are for the current device boot, not relaunch/reboot synchronization. A device wall-clock correction between measurement and callback delivery remains an ambiguity in CoreLocation's wall-clock timestamps; verify clock behavior on the real phone.

The sample field names follow the plan's initial proposal. `GPSBatchSender` sends a JSON POST using a caller-supplied request and body encoder, preserving its authentication and idempotency headers. It reports non-2xx responses and leaves samples unchanged for retries. The location batch envelope, authentication, idempotency, routes, and drive completion response will be supplied by the backend adapter after the final contract is published.

## Hazard without GPS

The backend adapter can pass `coordinate: nil`. `GeoCoordinate(latitude:longitude:)` also returns nil for missing, partial, nonfinite, or out-of-range coordinates. `HazardDetailView` retains category, evidence, and time into drive, displays **Location unavailable**, and asks for location review before choosing a destination. It creates no map or fallback `(0, 0)` pin. Valid coordinates are always labeled **Approximate location**. Evidence URL authentication must be defined by the backend; the current image view accepts directly fetchable URLs.

## Verification on a Mac

From `ios`:

```sh
swift test
swift build --product RoadWatchUI
```

Tests cover PUT/authentication/raw bytes, preserved files and retry, HTTP failures, delayed GPS delivery, first-frame zero, invalid/empty GPS, millisecond/UTC/null encoding, and a hazard without coordinates. The AVFoundation test creates a real H.264 MP4 from a synthetic frame, decodes it, and verifies its first presentation timestamp is zero.

For an iOS SDK compile in Xcode, select the RoadWatchKit package scheme and an iPhone Simulator destination, then Build. Physical camera/GPS tests and a real authenticated backend upload are separate integration checks. Tests have been authored but have not been run on this Windows workspace, which has no Swift or Xcode toolchain.
