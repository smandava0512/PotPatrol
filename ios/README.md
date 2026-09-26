# Pot Patrol iPhone app

SwiftUI + AVFoundation + CoreLocation; minimum iOS 17. Windows is the primary development environment. Use the planned iPhone 17 Pro / Pro Max on the final Mac once Xcode supports its installed iOS.

## Windows workflow

Edit Swift sources on `codex/developer-1-pot-patrol-ios`. Push runs package tests, iPhone Simulator package compilation, native Release build, native UI tests, and actual HTTP against the pinned Developer 2 backend with its explicitly synthetic analyzer. UI result bundles are GitHub Actions artifacts.

Xcode project and shared scheme are checked in. After adding/removing app or UI-test sources, regenerate with Python's standard library:

```powershell
C:/msys64/mingw64/bin/python.exe ios/scripts/generate_xcode_project.py
```

Tokens, real clips, and signing credentials do not belong in Git. Clips are ignored; the bundled synthetic MP4 is an explicit exception.

## First Mac step

Clone this branch; open `ios/PotPatrol.xcodeproj`. Select **PotPatrol**, choose an iPhone Simulator, then Run. No new project or third-party generator is needed.

Tap **Sample drive → Stop and save**. The labeled fixture moves through upload/processing to a pothole. Open it, review evidence and the approximate map, then edit/save its report. Its unverified destination keeps the portal disabled. **More sample scenarios** covers no GPS, zero hazards, processing failure and unsupported destination. Drives and edits persist through relaunch.

```sh
cd ios
swift test
xcodebuild -project PotPatrol.xcodeproj -scheme PotPatrol -destination 'generic/platform=iOS Simulator' build CODE_SIGNING_ALLOWED=NO
```

## Final phone setup

Connect the phone, enable Developer Mode if requested, select it in Xcode, and choose your Apple team in **Signing & Capabilities**. Use a unique bundle identifier if needed. Xcode manages provisioning; team/certificate changes stay local. Verify Xcode supports the phone's installed iOS before the demo.

Run and tap **Prepare camera and location** while parked. Denied GPS is supported; denied camera gives a Settings message. Video-only capture requests no microphone access. Leaving the foreground or a camera interruption stops/saves recording.

## Server

Enter Developer 2's URL and device token in **Connection settings**. The token goes into Keychain, never drive files. Use HTTPS for the hosted demo. Debug builds can explicitly allow local HTTP; Release enforces HTTPS. On the phone, use the server computer's LAN IP on the same Wi-Fi, not `127.0.0.1`. Developer 2 must bind its local server to the LAN interface.

Flow: create → upload-init → authenticated raw MP4 PUT → GPS batches up to 2,000 → complete `{}` → poll. GPS uses `{"samples":[...]}`, omits v1-forbidden `heading_deg`, and supports an empty track. Private evidence is authenticated and cached. See [compatibility](../docs/ios-backend-handoff.md).

## Capture and recovery

MP4 source time and GPS offsets start at the first successfully appended frame. Capture timestamp and CoreLocation measurement timestamps are correlated to the host clock. Cached pre-frame fixes and points after final duration are excluded. Startup/callback delay does not shift offsets.

Each drive's Application Support folder owns `drive.mp4`, `locations.json`, `capture-origin.json`, and atomic `drive.json`. First-frame UTC is written immediately after frame append, then stored as `videoStartedAt` on finalization. Recovery restores it for readable interrupted clips. Abrupt termination may leave an unreadable MP4; files are retained and the UI reports this. Wall-clock changes still need device verification.

Capture stops below the backend's ten-minute/100-MiB limits. File-backed background URLSession uses a stable identifier. Server ID, transfer acknowledgment, GPS checkpoints, status, errors, private evidence and reports survive reopening. Transient requests retry up to three times; manual retry renews expired tickets. Background transfers can survive system termination; user force-quit cancels them until reopening/retry. Recovered interrupted recordings require review before upload.

Draft edits stay local because v1 has no update endpoint. Portal opening requires a server-verified HTTPS destination and valid coordinates; changing location requires destination review. Opening never confirms submission. An actual user receipt is required, labeled **Submission confirmed by you**. Share includes text, available cached evidence and the whole saved video attachment.

## Verification limits

Synthetic fixtures test behavior/transport, not real detection. Final acceptance needs physical capture/GPS timing, real pothole and clean clips, Developer 3's analyzer and the deployed service. See [demo checklist](../docs/ios-demo-checklist.md).

Apple references: [camera permission](https://developer.apple.com/documentation/avfoundation/requesting-authorization-to-capture-and-save-media), [location permission](https://developer.apple.com/documentation/CoreLocation/requesting-authorization-to-use-location-services), [background sessions](https://developer.apple.com/documentation/foundation/urlsessionconfiguration/background(withidentifier:)), [device setup](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices).
