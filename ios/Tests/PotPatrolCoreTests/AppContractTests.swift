import Foundation
import XCTest
@testable import PotPatrolCore

private final class APIStub: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, data) = try Self.handler!(request)
            client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { }
}

final class AppContractTests: XCTestCase {
    private func client() throws -> PotPatrolAPIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [APIStub.self]
        return PotPatrolAPIClient(connection: try APIConnection(baseURL: URL(string: "https://api.example")!, deviceToken: "test-token"), session: URLSession(configuration: config))
    }
    private func body(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open()
        defer { stream.close() }
        var data = Data(), buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            guard count > 0 else { break }
            data.append(contentsOf: buffer.prefix(count))
        }
        return data
    }
    func testLocationWireShapeAuthenticationAndDuplicateOffsets() async throws {
        let date = PotPatrolJSON.date("2026-09-26T12:00:00.125Z")!
        let sample = GPSSample(offsetMilliseconds: 125, recordedAt: date, latitude: 25, longitude: -80,
                               horizontalAccuracyMeters: 5, speedMetersPerSecond: nil, headingDegrees: 180)
        let worse = GPSSample(offsetMilliseconds: 125, recordedAt: date, latitude: 26, longitude: -80,
                              horizontalAccuracyMeters: 50, speedMetersPerSecond: nil, headingDegrees: nil)
        APIStub.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Device-Token"), "test-token")
            let object = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            let samples = object["samples"] as! [[String: Any]]
            XCTAssertEqual(samples.count, 1)
            XCTAssertEqual(samples[0]["offset_ms"] as? Int, 125)
            XCTAssertEqual(samples[0]["latitude"] as? Double, 25)
            XCTAssertEqual(samples[0]["recorded_at"] as? String, "2026-09-26T12:00:00.125Z")
            XCTAssertNil(samples[0]["heading_deg"])
            return (200, Data("{\"accepted\":1}".utf8))
        }
        let accepted = try await client().sendLocations(driveID: UUID(), samples: [worse, sample])
        XCTAssertEqual(accepted, 1)
    }
    func testCompleteDoesNotSendProposedTimestampField() async throws {
        let id = UUID()
        APIStub.handler = { request in
            XCTAssertEqual(String(data: self.body(request), encoding: .utf8), "{}")
            return (200, Data("{\"drive_id\":\"\(id.uuidString)\",\"status\":\"queued\"}".utf8))
        }
        _ = try await client().completeDrive(driveID: id)
    }
    func testUploadAndEvidenceAuthDoNotLeakToForeignOrigin() async throws {
        let client = try client()
        let ticket = UploadTicket(uploadURL: URL(string: "https://api.example/video")!, method: "PUT", headers: ["Content-Type":"video/mp4"], expiresAt: Date())
        let request = try client.uploadRequest(ticket: ticket)
        XCTAssertEqual(request.httpMethod, "PUT")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Device-Token"), "test-token")
        let foreign = UploadTicket(uploadURL: URL(string: "https://other.example/video")!, method: "PUT", headers: [:], expiresAt: Date())
        XCTAssertThrowsError(try client.uploadRequest(ticket: foreign))
        do { _ = try await client.evidence(path: "https://other.example/image"); XCTFail("Foreign evidence allowed") } catch { }
        APIStub.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Device-Token"), "test-token")
            return (200, Data([0xff, 0xd8]))
        }
        let data = try await client.evidence(path: "/v1/hazards/test/evidence")
        XCTAssertEqual(data, Data([0xff, 0xd8]))
    }
    func testMissingGPSUnsupportedAndUnknownDestinationFixtures() throws {
        let noGPS = SavedDrive(demoScenario: .noGPS)
        let hazard = try XCTUnwrap(DemoFixtures.snapshot(for: noGPS).hazards.first)
        XCTAssertNil(hazard.location)
        XCTAssertEqual(hazard.locationLabel, "Location unavailable")
        XCTAssertNil(EditableReport(package: try DemoFixtures.report(for: noGPS)).portalURL)
        var unsupported = EditableReport(package: try DemoFixtures.report(for: SavedDrive(demoScenario: .unsupportedDestination)))
        XCTAssertEqual(unsupported.package.destination.status, "unsupported")
        XCTAssertNil(unsupported.portalURL)
        XCTAssertTrue(unsupported.shareText.contains("Pot Patrol"))
        unsupported.recordPortalOpened()
        XCTAssertEqual(unsupported.handoff, .draftPrepared)
        XCTAssertFalse(unsupported.confirmSubmission(receipt: "receipt"))
        XCTAssertEqual(try DemoFixtures.snapshot(for: SavedDrive(demoScenario: .noHazards)).hazards.count, 0)
        XCTAssertEqual(try DemoFixtures.snapshot(for: SavedDrive(demoScenario: .processingFailure)).status, "failed")
        XCTAssertNil(ReportDestination(status: "future_status", url: "https://example.com").verifiedURL)
    }
    func testPortalOpenRequiresActualReceiptForConfirmationAndLocationEditInvalidatesDestination() throws {
        var package = try DemoFixtures.report(for: SavedDrive(demoScenario: .pothole))
        package = ReportPackage(reportID: package.reportID, fields: package.fields,
                                destination: ReportDestination(status: "verified", url: "https://example.com/report"), submissionStatus: "not_submitted")
        var report = EditableReport(package: package)
        XCTAssertNotNil(report.portalURL)
        XCTAssertFalse(report.confirmSubmission(receipt: "receipt"))
        report.recordPortalOpened()
        XCTAssertEqual(report.handoff, .portalOpened)
        XCTAssertFalse(report.confirmSubmission(receipt: " "))
        XCTAssertTrue(report.confirmSubmission(receipt: "ABC-123"))
        XCTAssertEqual(report.handoff, .submissionConfirmed)
        var fields = package.fields
        fields["latitude"] = .number(26)
        report.edit(fields: fields)
        XCTAssertNil(report.portalURL)
        XCTAssertEqual(report.handoff, .draftPrepared)
        XCTAssertNil(report.receipt)
        XCTAssertEqual(report.previousReceipts, ["ABC-123"])
    }
    func testUTCOriginCheckpointsAndReportsSurviveRepositoryReopen() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let repository = SavedDriveRepository(root: root)
        var drive = SavedDrive()
        let firstFrame = PotPatrolJSON.date("2026-09-26T12:00:00.125Z")!
        drive.videoStartedAt = firstFrame
        drive.serverID = UUID()
        drive.videoUploaded = true
        drive.nextGPSIndex = 2000
        drive.state = .uploading
        let report = EditableReport(package: try DemoFixtures.report(for: drive))
        drive.reports["hazard"] = report
        try await repository.save(drive)
        try await repository.saveSamples(DemoFixtures.samples(), id: drive.id)
        let reopened = SavedDriveRepository(root: root)
        let loaded = try await reopened.load(drive.id)
        XCTAssertEqual(loaded.videoStartedAt, firstFrame)
        XCTAssertEqual(loaded.nextGPSIndex, 2000)
        XCTAssertTrue(loaded.videoUploaded)
        XCTAssertEqual(loaded.reports["hazard"]?.handoff, .draftPrepared)
        let samples = try await reopened.samples(drive.id)
        XCTAssertEqual(samples.count, 2)
        let corrupt = SavedDrive()
        try await reopened.save(corrupt)
        let directory = await reopened.directory(corrupt.id)
        try Data("broken".utf8).write(to: directory.appendingPathComponent("drive.json"))
        let library = try await reopened.library()
        XCTAssertEqual(library.drives.map(\.id), [drive.id])
        XCTAssertEqual(library.unreadableDriveIDs, [corrupt.id])
    }
}
