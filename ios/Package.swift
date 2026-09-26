// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "RoadWatchKit",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "RoadWatchCore", targets: ["RoadWatchCore"]),
        .library(name: "RoadWatchCapture", targets: ["RoadWatchCapture"]),
        .library(name: "RoadWatchUI", targets: ["RoadWatchUI"])
    ],
    targets: [
        .target(name: "RoadWatchCore"),
        .target(name: "RoadWatchCapture", dependencies: ["RoadWatchCore"]),
        .target(name: "RoadWatchUI", dependencies: ["RoadWatchCore"]),
        .testTarget(name: "RoadWatchCoreTests", dependencies: ["RoadWatchCore"]),
        .testTarget(name: "RoadWatchCaptureTests", dependencies: ["RoadWatchCapture", "RoadWatchCore"])
    ]
)
