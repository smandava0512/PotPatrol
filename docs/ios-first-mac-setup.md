# Pot Patrol: first Mac and iPhone run

Continue editing on Windows and using the existing macOS CI. Use the Mac to sign, install and check the app on your iPhone before the demo. The Xcode project is already generated and checked in.

## Install Xcode

**For this demo:** The available MacBook Air M2 is on macOS Ventura 13.5 and the
iPhone is on iOS 26.6.2. Apple's [Xcode requirements](https://developer.apple.com/support/xcode)
list Xcode 15.2 as compatible with Ventura 13.5, but Xcode 27 requires macOS
Tahoe 26.6 or later. Ventura-era Xcode cannot prepare this iOS 26 phone. With
the Mac owner's approval, back up the Mac and update it to a compatible macOS
before installing the released Xcode 27; otherwise use a different up-to-date Mac.
Do not modify a borrowed Mac's operating system without its owner's consent.

1. Check the Mac's macOS version in **About This Mac** and the phone's iOS version in **Settings → General → About**. Choose a released Xcode that supports both using [Apple's compatibility table](https://developer.apple.com/xcode/system-requirements). The exact installed versions matter; “latest iOS” alone is not enough to choose Xcode.
2. Install Xcode from the Mac App Store or [Apple Developer downloads](https://developer.apple.com/download/all/?q=Xcode). Open it, accept the license and finish the first-launch component installation. Install iOS platform support and an iPhone Simulator runtime when prompted. See [Apple's component instructions](https://developer.apple.com/documentation/xcode/downloading-and-installing-additional-xcode-components).
3. In **Xcode → Settings → Apple Accounts**, sign in with your Apple Account. A [Personal Team](https://developer.apple.com/help/account/basics/about-your-developer-account) supports installing and testing on your own device. Personal Team provisioning expires after seven days, so rebuild/reinstall near the demo if necessary.

## Get the merged source

Open Terminal on the Mac and run:

```sh
git clone --branch main --single-branch https://github.com/smandava0512/PotPatrol.git
cd PotPatrol
open ios/PotPatrol.xcodeproj
```

After PR #3 merges, an existing clone can save local changes, fetch `main`,
and switch to it. The iOS app is already included; do not create a new Xcode project.

Choose scheme **PotPatrol**, an iPhone Simulator, and **Run**. Check **Sample drive → Stop and save → Results → Pothole → Review report**. Under **More sample scenarios**, try missing GPS, unsupported destination and destination candidates. These samples are labeled fixtures.

## Install on the iPhone

1. Connect the iPhone with a data cable, unlock it, and trust the Mac when asked. Let Xcode finish preparing the device.
2. Select the blue **PotPatrol** project, then target **PotPatrol** and **Signing & Capabilities**. Keep automatic signing enabled and select your team. If `com.potpatrol.app` is unavailable to your team, use a unique local bundle identifier such as `com.yourname.potpatrol`. Keep signing changes local. If you run UI tests on the phone, configure the UI-test target's team and a corresponding unique bundle identifier too.
3. Follow Xcode's prompt to enable [Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device) on the phone, including its restart and confirmation.
4. Choose your connected iPhone as the run destination and press **Run**. Xcode signs, installs and launches the app. If the device is unavailable, read its reason in Xcode: unsupported iOS, missing platform support, signing or disabled Developer Mode require different fixes. See [Apple's device-running instructions](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices).

## Connect and record

In the app's **Connection settings**, enter `https://api.potpatrol.miami` and the privately provisioned device token. The token is stored in Keychain. Do not add it to source, screenshots, shared notes or Git. Keep development HTTP disabled for this hosted service.

Tap **Prepare camera and location** while parked. Capture a short clip as a passenger or while parked, stop, and upload. Each real upload obtains a new UUID from `POST /v1/drives`; that server ID is saved for retries. The previously supplied test UUID is not an app constant. Sample drives use the local fixture path and do not exercise the live server.

## Acceptance on the phone

Use the [full demo checklist](ios-demo-checklist.md). For the real-pothole requirement, Developer 2 must confirm the deployed worker uses the real model, and the new drive must return `analysis_mode:"model"` with a pothole. Check its evidence and offset against the original real clip, then confirm the hazard actually appears on the phone. A model label alone does not prove the clip or detection is real.

Also verify:

- A clean real clip yields zero hazards; a detected hazard without GPS stays visible with **Location unavailable**.
- **Refresh draft** replaces the locally cached fields after confirmation. The deployed fixture draft now returns plain category/description and numeric/null coordinate fields; previously cached blank drafts still need refresh.
- Candidate reason, names, URLs and sources are visible. Choosing a candidate retains `needs_review`; opening its page records **Portal opened**. Only an actual receipt can support user-confirmed submission.
- Changing coordinates blocks the portal; restoring the originals clears that review state. Missing and null coordinates compare equally.
- **Include full drive video** starts off. Default sharing contains text and available evidence; adding the whole drive requires an explicit opt-in.

## Verified so far

On 2026-09-27, authenticated checks of the supplied test drive succeeded: complete, two fixture potholes at 12.25 s and 36.7 s, both without GPS. Private JPEG evidence returned HTTP 200. Its report draft returned plain category/description, explicit null latitude/longitude, `destination.status:"needs_review"`, no candidates and `submission_status:"not_submitted"`. No credentials or evidence files were saved for these checks.

[CI 36293356119](https://github.com/smandava0512/PotPatrol/actions/runs/36293356119) passed 33 unit checks, separate synthetic-worker HTTP integration, native Release compilation and six simulator UI scenarios. The real clip, physical camera/GPS timing, signing and real-model result displayed on an iPhone remain unconfirmed.
