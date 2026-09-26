import Foundation
import XCTest
@testable import PotPatrolCore

/// Real HTTP, storage, SQLite, and worker; the analyzer is explicitly a synthetic fixture.
final class BackendIntegrationTests: XCTestCase {
    func testPublishedV1EndToEndWithAndWithoutGPS() async throws {
        guard let base = ProcessInfo.processInfo.environment["POTPATROL_TEST_BASE_URL"],
              let token = ProcessInfo.processInfo.environment["POTPATROL_TEST_TOKEN"] else {
            throw XCTSkip("Requires the contract backend fixture process")
        }
        let client = PotPatrolAPIClient(connection: try APIConnection(baseURL: URL(string: base)!, deviceToken: token, allowDevelopmentHTTP: true))
        for withGPS in [true, false] {
            let identity = try await client.createDrive()
            let ticket = try await client.initializeUpload(driveID: identity.driveID)
            try await client.uploadVideo(fileURL: DemoFixtures.videoURL, ticket: ticket)
            let samples = withGPS ? try DemoFixtures.samples() : []
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
            let hazard = try XCTUnwrap(snapshot.hazards.first)
            XCTAssertEqual(hazard.location?.coordinate != nil, withGPS)
            let jpeg = try await client.evidence(path: XCTUnwrap(hazard.evidenceURL))
            XCTAssertEqual(Array(jpeg.prefix(2)), [0xff, 0xd8])
            let report = try await client.reportDraft(hazardID: hazard.id)
            XCTAssertEqual(report.submissionStatus, "not_submitted")
            XCTAssertNil(EditableReport(package: report).portalURL)
        }
    }
}
