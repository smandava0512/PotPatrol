# Pot Patrol — Developer 1 iOS

Native Swift components for Pot Patrol. Developer 1's iOS work lives on `codex/developer-1-pot-patrol-ios`; `main` starts with no project files. The backend contract is still being built, so this branch contains an iOS integration package, not a complete runnable app or an invented API client.

- `PotPatrolCore`: authenticated raw MP4 PUT uploads, GPS offset calculation/encoding and batch submission, and hazards with optional coordinates.
- `PotPatrolCapture`: AVFoundation first-frame anchoring and CoreLocation clock conversion.
- `PotPatrolUI`: hazard evidence and approximate location, including a location-unavailable state.

See [the backend handoff](docs/ios-backend-handoff.md) for the supported behavior and remaining contract details, and [the package instructions](ios/README.md) for Mac verification.
