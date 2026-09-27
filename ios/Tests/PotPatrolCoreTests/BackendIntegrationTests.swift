import Foundation
import XCTest
@testable import PotPatrolCore

/// Real HTTP, storage, SQLite, and merged worker/adapter; analysis is explicitly a synthetic fixture.
final class BackendIntegrationTests: XCTestCase {
    func testMergedBackendEndToEndWithAndWithoutGPS() async throws {
        guard let base = ProcessInfo.processInfo.environment["POTPATROL_TEST_BASE_URL"],
              let token = ProcessInfo.processInfo.environment["POTPATROL_TEST_TOKEN"] else {
            throw XCTSkip("Requires the contract backend fixture process")
        }
        let client = PotPatrolAPIClient(connection: try APIConnection(baseURL: URL(string: base)!, deviceToken: token, allowDevelopmentHTTP: true))
        for withGPS in [true, false] {
            let identity = try await client.createDrive()
            let ticket = try await client.initializeUpload(driveID: identity.driveID)
            try await client.uploadVideo(fileURL: DemoFixtures.videoURL, ticket: ticket)
            // The merged worker's explicit fixture events are at 12.25 s and 36.7 s;
            // the package's older 0–2 s location example does not locate them.
            let samples: [GPSSample] = withGPS ? [12_250, 36_700].map { offset in
                GPSSample(offsetMilliseconds: Int64(offset),
                          recordedAt: Date(timeIntervalSince1970: 1_750_000_000 + Double(offset) / 1_000),
                          latitude: 25.7563, longitude: -80.374,
                          horizontalAccuracyMeters: 8, speedMetersPerSecond: nil, headingDegrees: nil)
            } : []
            let accepted = try await client.sendLocations(driveID: identity.driveID, samples: samples)
            XCTAssertEqual(accepted, samples.count)
            let repeated = try await client.sendLocations(driveID: identity.driveID, samples: samples)
            XCTAssertEqual(repeated, 0)
            _ = try await client.completeDrive(driveID: identity.driveID)
            _ = try await client.completeDrive(driveID: identity.driveID)
            var snapshot = try await client.drive(driveID: identity.driveID)
            for _ in 0..<40 where !snapshot.isFinished {
                try await Task.sleep(for: .milliseconds(500))
                snapshot = try await client.drive(driveID: identity.driveID)
            }
            XCTAssertEqual(snapshot.status, "complete", snapshot.error ?? "Worker did not finish")
            XCTAssertEqual(snapshot.analysisMode, "fixture")
            let hazard = try XCTUnwrap(snapshot.hazards.first)
            XCTAssertEqual(hazard.location?.coordinate != nil, withGPS)
            let jpeg = try await client.evidence(path: XCTUnwrap(hazard.evidenceURL))
            XCTAssertEqual(Array(jpeg.prefix(2)), [0xff, 0xd8])
            let report = try await client.reportDraft(hazardID: hazard.id)
            XCTAssertEqual(report.submissionStatus, "not_submitted")
            XCTAssertEqual(report.fields["category"]?.text, "pothole")
            XCTAssertFalse(report.fields["description"]?.text.isEmpty ?? true)
            XCTAssertEqual(report.fields["latitude"]?.number, hazard.location?.latitude)
            XCTAssertEqual(report.fields["longitude"]?.number, hazard.location?.longitude)
            XCTAssertEqual(report.destination.status, "needs_review")
            XCTAssertEqual(report.destination.candidates?.count, withGPS ? 3 : 0)
            XCTAssertNil(EditableReport(package: report).portalURL)
        }
    }
}
