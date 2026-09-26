# Pot Patrol — Developer 1 iOS

Native iPhone app: record a drive, upload MP4 and synchronized GPS, review server hazards and private evidence, edit a report, and follow a verified reporting destination.

Developer 1's work lives on `codex/developer-1-pot-patrol-ios`. The default `main` intentionally has no files. Develop on Windows; GitHub macOS runners compile/test. A Mac with Xcode is needed for final signing and the physical demo.

Open `ios/PotPatrol.xcodeproj` on the Mac with the **PotPatrol** scheme. Labeled sample scenarios cover a hazard, missing GPS, zero hazards, processing failure, and unsupported destination.

- [Windows development / Mac setup](ios/README.md)
- [Backend compatibility / UTC](docs/ios-backend-handoff.md)
- [Copyable Discord messages](docs/coordination/changes.md)
- [Real clips / demo checklist](docs/ios-demo-checklist.md)

Developer 2 owns the canonical contract on their branch. This branch contains the consumer adapter and copied demo fixtures; it does not modify the backend or analyzer.
