import Foundation
import XCTest
@testable import RoadWatchCore

final class RecordingTimelineTests: XCTestCase {
    private let epoch = Date(timeIntervalSince1970: 1_700_000_000)

    private var timeline: RecordingTimeline {
        RecordingTimeline(origin: VideoTimeOrigin(
            firstFrameHostTimeSeconds: 100, firstFrameRecordedAt: epoch
        ))
    }

    private func reading(
        hostTime: Double, accuracy: Double = 5, latitude: Double = 25.75,
        speed: Double? = nil, heading: Double? = nil
    ) -> GPSReading {
        GPSReading(
            recordedAt: epoch.addingTimeInterval(hostTime - 100),
            measuredHostTimeSeconds: hostTime,
            latitude: latitude, longitude: -80.25,
            horizontalAccuracyMeters: accuracy,
            speedMetersPerSecond: speed, headingDegrees: heading
        )
    }

    func testZeroIsFirstFrameRatherThanStartButtonOrCallback() {
        // Start was tapped at host 98; the first recorded frame arrived at host 100.
        let received = ClockCorrelation(recordedAt: epoch.addingTimeInterval(8), hostTimeSeconds: 108)
        let actualMeasurement = epoch.addingTimeInterval(2.5)
        let gps = GPSReading(
            recordedAt: actualMeasurement,
            measuredHostTimeSeconds: received.hostTime(for: actualMeasurement),
            latitude: 25.75, longitude: -80.25, horizontalAccuracyMeters: 5
        )
        let samples = timeline.samples(from: [gps, reading(hostTime: 100)])
        XCTAssertEqual(samples.map(\.offsetMilliseconds), [0, 2_500])
        XCTAssertEqual(samples.last?.recordedAt, actualMeasurement)
    }

    func testPreFrameCachedFixesAreDroppedRatherThanClampedToZero() {
        let samples = timeline.samples(from: [reading(hostTime: 99), reading(hostTime: 99.9999)])
        XCTAssertTrue(samples.isEmpty)
    }

    func testUsesIntegerMillisecondsAndOrdersBatchedLocations() {
        let samples = timeline.samples(from: [reading(hostTime: 102.125), reading(hostTime: 100.125)])
        XCTAssertEqual(samples.map(\.offsetMilliseconds), [125, 2_125])
    }

    func testEmptyTrackStaysEmpty() {
        XCTAssertEqual(timeline.samples(from: []), [])
    }

    func testInvalidAccuracyCoordinatesAndTimesAreDropped() {
        XCTAssertTrue(timeline.samples(from: [
            reading(hostTime: 101, accuracy: -1),
            reading(hostTime: 101, accuracy: .nan),
            reading(hostTime: 101, latitude: 91),
            reading(hostTime: .nan),
            reading(hostTime: .infinity)
        ]).isEmpty)
    }

    func testReadingsAfterVideoDurationAreExcluded() {
        let samples = timeline.samples(
            from: [reading(hostTime: 101), reading(hostTime: 102.001)], durationMilliseconds: 2_000
        )
        XCTAssertEqual(samples.map(\.offsetMilliseconds), [1_000])
    }

    func testWallClockChangeDoesNotChangeMonotonicOffsets() {
        // Device wall time moved forward an hour. Correlate each delivered CLLocation timestamp
        // with current host time instead of subtracting two wall times across the clock change.
        let current = ClockCorrelation(recordedAt: epoch.addingTimeInterval(3_608), hostTimeSeconds: 108)
        let measurement = epoch.addingTimeInterval(3_606)
        let gps = GPSReading(
            recordedAt: measurement, measuredHostTimeSeconds: current.hostTime(for: measurement),
            latitude: 25.75, longitude: -80.25, horizontalAccuracyMeters: 5
        )
        XCTAssertEqual(timeline.samples(from: [gps]).first?.offsetMilliseconds, 6_000)
    }

    func testPayloadUsesProposedFieldsUTCAndNullUnavailableSensors() throws {
        let data = try JSONEncoder().encode(timeline.samples(from: [
            reading(hostTime: 101.25, speed: -1, heading: -1)
        ]))
        let array = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [[String: Any]])
        let sample = try XCTUnwrap(array.first)
        XCTAssertEqual(sample["offset_ms"] as? Int, 1_250)
        XCTAssertEqual(sample["recorded_at"] as? String, "2023-11-14T22:13:21.250Z")
        XCTAssertEqual(sample["horizontal_accuracy_m"] as? Double, 5)
        XCTAssertTrue(sample["speed_mps"] is NSNull)
        XCTAssertTrue(sample["heading_deg"] is NSNull)
        XCTAssertNil(sample["measuredHostTimeSeconds"])
    }

    func testMeasuredZeroSpeedAndHeadingArePreserved() {
        let sample = timeline.samples(from: [reading(hostTime: 101, speed: 0, heading: 0)]).first
        XCTAssertEqual(sample?.speedMetersPerSecond, 0)
        XCTAssertEqual(sample?.headingDegrees, 0)
    }
}
