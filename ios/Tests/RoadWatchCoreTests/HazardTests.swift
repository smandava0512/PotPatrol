import Foundation
import XCTest
@testable import RoadWatchCore

final class HazardTests: XCTestCase {
    func testNoGPSPreservesHazardEvidenceAndTimeButRequiresReview() {
        let id = UUID()
        let evidence = URL(string: "https://evidence.example.test/pothole.jpg")!
        let hazard = Hazard(
            id: id, category: "pothole", videoOffsetMilliseconds: 4_500,
            evidenceURL: evidence, coordinate: nil
        )
        XCTAssertEqual(hazard.id, id)
        XCTAssertEqual(hazard.category, "pothole")
        XCTAssertEqual(hazard.evidenceURL, evidence)
        XCTAssertEqual(hazard.videoOffsetMilliseconds, 4_500)
        XCTAssertNil(hazard.coordinate)
        XCTAssertEqual(hazard.locationLabel, "Location unavailable")
        XCTAssertTrue(hazard.requiresLocationReview)
    }

    func testIncompleteOrInvalidCoordinatesDoNotCreateAPin() {
        XCTAssertNil(GeoCoordinate(latitude: nil, longitude: nil))
        XCTAssertNil(GeoCoordinate(latitude: 25, longitude: nil))
        XCTAssertNil(GeoCoordinate(latitude: nil, longitude: -80))
        XCTAssertNil(GeoCoordinate(latitude: 91, longitude: -80))
        XCTAssertNil(GeoCoordinate(latitude: .nan, longitude: -80))
    }

    func testValidCoordinatesRemainApproximateIncludingARealZeroCoordinate() {
        let coordinate = GeoCoordinate(latitude: 0, longitude: 0)
        XCTAssertNotNil(coordinate)
        let hazard = Hazard(
            id: UUID(), category: "pothole", videoOffsetMilliseconds: 0,
            evidenceURL: nil, coordinate: coordinate, horizontalAccuracyMeters: 12
        )
        XCTAssertFalse(hazard.requiresLocationReview)
        XCTAssertEqual(hazard.locationLabel, "Approximate location")
        XCTAssertEqual(hazard.horizontalAccuracyMeters, 12)
    }
}
