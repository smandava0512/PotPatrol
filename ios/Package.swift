// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PotPatrolKit",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "PotPatrolCore", targets: ["PotPatrolCore"]),
        .library(name: "PotPatrolCapture", targets: ["PotPatrolCapture"]),
        .library(name: "PotPatrolUI", targets: ["PotPatrolUI"])
    ],
    targets: [
        .target(name: "PotPatrolCore"),
        .target(name: "PotPatrolCapture", dependencies: ["PotPatrolCore"]),
        .target(name: "PotPatrolUI", dependencies: ["PotPatrolCore"]),
        .testTarget(name: "PotPatrolCoreTests", dependencies: ["PotPatrolCore"]),
        .testTarget(name: "PotPatrolCaptureTests", dependencies: ["PotPatrolCapture", "PotPatrolCore"])
    ]
)
