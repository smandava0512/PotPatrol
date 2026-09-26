# RoadWatch iOS

Native Swift components for RoadWatch. The backend contract is still being built, so this branch contains an iOS integration package, not a complete runnable app or an invented API client.

- `RoadWatchCore`: authenticated raw MP4 PUT uploads, GPS offset calculation/encoding and batch submission, and hazards with optional coordinates.
- `RoadWatchCapture`: AVFoundation first-frame anchoring and CoreLocation clock conversion.
- `RoadWatchUI`: hazard evidence and approximate location, including a location-unavailable state.

See [the backend handoff](docs/ios-backend-handoff.md) for the supported behavior and remaining contract details, and [the package instructions](ios/README.md) for Mac verification.
