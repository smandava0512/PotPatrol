# Pot Patrol iPhone app

SwiftUI + AVFoundation + CoreLocation; minimum iOS 17. Windows is the primary development environment. Use the planned iPhone 17 Pro / Pro Max on the final Mac once Xcode supports its installed iOS.

## Windows workflow

Edit Swift sources on a task branch. Pull requests run package tests, iPhone Simulator package compilation, native Release build, native UI tests, and actual HTTP against the backend in the same merged checkout with its explicitly synthetic analyzer. UI result bundles are GitHub Actions artifacts.

Xcode project and shared scheme are checked in. After adding/removing app or UI-test sources, regenerate with Python's standard library:

```powershell
C:/msys64/mingw64/bin/python.exe ios/scripts/generate_xcode_project.py
```

Tokens, real clips, and signing credentials do not belong in Git. Clips are ignored; the bundled synthetic MP4 is an explicit exception.

## First Mac step

Use the [first-time Mac setup guide](../docs/ios-first-mac-setup.md) for Xcode installation, Apple Account/signing and iPhone Developer Mode. Clone `main` after PR #3 merges; open `ios/PotPatrol.xcodeproj`. Select **PotPatrol**, choose an iPhone Simulator, then Run. No new project or third-party generator is needed.

Tap **Sample drive → Stop and save**. The labeled fixture moves through upload/processing to a pothole. Open it, review evidence and the approximate map, then edit/save its report. Its unverified destination keeps the portal disabled. **More sample scenarios** covers no GPS, zero hazards, processing failure, unsupported destination and destination candidates. Drives and edits persist through relaunch.

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

After reviewing the saved recording, choose **Send video and GPS for analysis**. The approval is saved for that server only. Flow: create → upload-init → authenticated raw MP4 PUT → GPS batches up to 2,000 → complete with captured `video_started_at` when available (otherwise `{}`) → poll. GPS uses `{"samples":[...]}`, omits v1-forbidden `heading_deg`, and supports an empty track. Private evidence is authenticated and cached. See [compatibility](../docs/ios-backend-handoff.md).

## Capture and recovery

MP4 source time and GPS offsets start at the first successfully appended frame. Capture timestamp and CoreLocation measurement timestamps are correlated to the host clock. Cached pre-frame fixes and points after final duration are excluded. Startup/callback delay does not shift offsets.

Each drive's Application Support folder owns `drive.mp4`, `locations.json`, `capture-origin.json`, and atomic `drive.json`. First-frame UTC is written immediately after frame append, then stored as `videoStartedAt` on finalization. Recovery restores it for readable interrupted clips. Abrupt termination may leave an unreadable MP4; files are retained and the UI reports this. Wall-clock changes still need device verification.

Capture stops below the backend's ten-minute/100-MiB limits. The file-backed upload uses a **foreground** URLSession: background sessions automatically follow redirects without asking the delegate, which could send a private MP4 to another host. The app refuses all upload redirects. On launch it cancels any outstanding transfers from the previous background-session implementation; footage already sent before launch cannot be recalled. A transfer may stop when the app is suspended or terminated; the saved file and approved server survive, so reopen and retry when foregrounded. Older in-progress drives require explicit review before continuing. Server ID, confirmed upload receipt, GPS checkpoints, status, errors, private evidence and reports survive reopening. Transient requests retry up to three times; manual retry renews expired tickets. Recovered interrupted recordings require review before upload.

Draft edits stay local because v1 has no update endpoint. **Refresh draft** explicitly re-fetches the server package, replacing local edits after confirmation and preserving earlier receipts in history. Developer 2's adapter owns flattening structured category/description/coordinates; it must also repair or flatten previously persisted server drafts.

Reports show destination candidates, agency URLs, sources and the server reason. A valid location and an explicit user choice allow opening a candidate HTTPS agency page under `needs_review`; the server status stays `needs_review` and ownership remains unverified. Verified server destinations also support handoff. Coordinate edits block handoff until restored to the original values or refreshed against the updated server draft. Missing and null coordinates compare equally. Older cached drafts already marked edited without an original-coordinate baseline require refresh.

Opening never confirms submission. An actual user receipt is required, labeled **Submission confirmed by you**. Editing a previously opened/confirmed draft or changing its selected candidate returns it to Draft prepared and retains older receipts as history. Share includes text and available evidence by default; **Include full drive video** is off until the user opts in.

## Verification limits

Synthetic fixtures test behavior/transport, not real detection. Final acceptance needs physical capture/GPS timing, real pothole and clean clips, Developer 3's analyzer and the deployed service. See [demo checklist](../docs/ios-demo-checklist.md).

Apple references: [camera permission](https://developer.apple.com/documentation/avfoundation/requesting-authorization-to-capture-and-save-media), [location permission](https://developer.apple.com/documentation/CoreLocation/requesting-authorization-to-use-location-services), [background sessions](https://developer.apple.com/documentation/foundation/urlsessionconfiguration/background(withidentifier:)), [device setup](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices).
