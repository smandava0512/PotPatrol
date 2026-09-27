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
    func testCompleteWithoutRecordedOriginKeepsEmptyBody() async throws {
        let id = UUID()
        APIStub.handler = { request in
            XCTAssertEqual(String(data: self.body(request), encoding: .utf8), "{}")
            return (200, Data("{\"drive_id\":\"\(id.uuidString)\",\"status\":\"queued\"}".utf8))
        }
        _ = try await client().completeDrive(driveID: id)
    }
    func testCompleteSendsCapturedFirstFrameUTC() async throws {
        let id = UUID()
        let firstFrame = try XCTUnwrap(PotPatrolJSON.date("2026-09-26T12:00:00.125Z"))
        APIStub.handler = { request in
            let object = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(object["video_started_at"] as? String, "2026-09-26T12:00:00.125Z")
            return (200, Data("{\"drive_id\":\"\(id.uuidString)\",\"status\":\"queued\"}".utf8))
        }
        _ = try await client().completeDrive(driveID: id, videoStartedAt: firstFrame)
    }
    func testSavedVideoRequiresExplicitApprovalForTheSelectedServer() throws {
        var drive = SavedDrive()
        drive.state = .saved
        let first = URL(string: "https://api.potpatrol.miami")!
        let other = URL(string: "https://other.example")!
        XCTAssertFalse(drive.mayUpload(to: first))
        drive.approvedUploadBaseURL = first.absoluteString
        XCTAssertTrue(drive.mayUpload(to: first))
        XCTAssertFalse(drive.mayUpload(to: other))
        let encoder = PotPatrolJSON.encoder(), decoder = PotPatrolJSON.decoder()
        XCTAssertTrue(try decoder.decode(SavedDrive.self, from: encoder.encode(drive)).mayUpload(to: first))
        var legacy = try JSONSerialization.jsonObject(with: encoder.encode(drive)) as! [String: Any]
        legacy.removeValue(forKey: "approvedUploadBaseURL")
        let recovered = try decoder.decode(SavedDrive.self, from: JSONSerialization.data(withJSONObject: legacy))
        XCTAssertFalse(recovered.mayUpload(to: first))
        XCTAssertTrue(recovered.canReviewForUpload)
        var legacyUploading = recovered
        legacyUploading.state = .uploading
        XCTAssertTrue(legacyUploading.canReviewForUpload)
        legacyUploading.state = .failed
        legacyUploading.serverID = UUID()
        XCTAssertTrue(legacyUploading.canReviewForUpload)
        legacyUploading.serverID = nil
        XCTAssertFalse(legacyUploading.canReviewForUpload)
    }
    func testPrivateUploadUsesForegroundSessionAndRejectsEveryRedirect() {
        let configuration = UploadSessionSafety.configuration()
        XCTAssertNil(configuration.identifier) // Background sessions ignore redirect delegates.
        for url in ["https://api.potpatrol.miami/video", "https://other.example/collect"] {
            XCTAssertNil(UploadSessionSafety.redirect(URLRequest(url: URL(string: url)!)))
        }
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
        XCTAssertNil(ReportDestination(status: "needs_review", url: "https://example.com").verifiedURL)
    }
    func testServerFixtureModeIsRetainedWithoutChangingUploadWorkflow() throws {
        let result = Data("{\"drive_id\":\"11111111-1111-4111-8111-111111111111\",\"status\":\"complete\",\"stage\":\"complete\",\"error\":null,\"hazards\":[]}".utf8)
        var drive = SavedDrive()
        drive.snapshot = try PotPatrolJSON.decoder().decode(DriveSnapshot.self, from: result)
        XCTAssertNil(drive.snapshot?.analysisMode)
        XCTAssertFalse(drive.usesFixtureAnalysis)
        var object = try JSONSerialization.jsonObject(with: result) as! [String: Any]
        object["analysis_mode"] = "fixture"
        drive.snapshot = try PotPatrolJSON.decoder().decode(DriveSnapshot.self, from: JSONSerialization.data(withJSONObject: object))
        XCTAssertTrue(drive.usesFixtureAnalysis)
        XCTAssertFalse(drive.isDemo) // Server fixtures still use the normal authenticated workflow.
        let reopened = try PotPatrolJSON.decoder().decode(SavedDrive.self, from: PotPatrolJSON.encoder().encode(drive))
        XCTAssertEqual(reopened.snapshot?.analysisMode, "fixture")
        XCTAssertTrue(reopened.usesFixtureAnalysis)
        for mode in ["model", "future_mode"] {
            object["analysis_mode"] = mode
            drive.snapshot = try PotPatrolJSON.decoder().decode(DriveSnapshot.self, from: JSONSerialization.data(withJSONObject: object))
            XCTAssertEqual(drive.snapshot?.analysisMode, mode)
            XCTAssertFalse(drive.usesFixtureAnalysis)
        }
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
    func testCoordinateReviewClearsOnRevertAndMissingEqualsNull() throws {
        let base = try DemoFixtures.report(for: SavedDrive(demoScenario: .pothole))
        var report = EditableReport(package: ReportPackage(reportID: base.reportID, fields: base.fields,
                                   destination: ReportDestination(status: "verified", url: "https://example.com/report"), submissionStatus: "not_submitted"))
        var edited = report.package.fields
        edited["latitude"] = .number(26)
        report.edit(fields: edited)
        XCTAssertTrue(report.destinationNeedsReview)
        XCTAssertNil(report.portalURL)
        report.edit(fields: base.fields)
        XCTAssertFalse(report.destinationNeedsReview)
        XCTAssertNotNil(report.portalURL)
        let reopened = try PotPatrolJSON.decoder().decode(EditableReport.self, from: PotPatrolJSON.encoder().encode(report))
        XCTAssertFalse(reopened.destinationNeedsReview)
        var noCoordinates = base.fields
        noCoordinates.removeValue(forKey: "latitude")
        noCoordinates.removeValue(forKey: "longitude")
        var missing = EditableReport(package: ReportPackage(reportID: base.reportID, fields: noCoordinates,
                                    destination: base.destination, submissionStatus: "not_submitted"))
        noCoordinates["latitude"] = .null
        noCoordinates["longitude"] = .null
        missing.edit(fields: noCoordinates)
        XCTAssertFalse(missing.destinationNeedsReview)
        // Old drafts already marked edited cannot safely infer their original coordinates.
        var legacy = try JSONSerialization.jsonObject(with: PotPatrolJSON.encoder().encode(report)) as! [String: Any]
        legacy.removeValue(forKey: "originalCoordinates")
        legacy["destinationNeedsReview"] = true
        var oldReport = try PotPatrolJSON.decoder().decode(EditableReport.self, from: JSONSerialization.data(withJSONObject: legacy))
        oldReport.edit(fields: oldReport.package.fields)
        XCTAssertTrue(oldReport.destinationNeedsReview)
    }
    func testCandidateSelectionPreservesNeedsReviewAndReceiptHonesty() throws {
        let package = try DemoFixtures.report(for: SavedDrive(demoScenario: .destinationCandidates))
        XCTAssertEqual(package.destination.candidates?.count, 3)
        XCTAssertFalse(package.destination.reason!.isEmpty)
        XCTAssertNotNil(package.destination.candidates?.first?.sources?.first?.httpsURL)
        var report = EditableReport(package: package)
        XCTAssertNil(report.portalURL)
        XCTAssertFalse(report.selectCandidate("unknown-agency"))
        XCTAssertTrue(report.selectCandidate("miami-dade-dtpw-311"))
        XCTAssertEqual(report.package.destination.status, "needs_review")
        XCTAssertEqual(report.handoff, .draftPrepared)
        XCTAssertNotNil(report.portalURL)
        XCTAssertFalse(report.confirmSubmission(receipt: "receipt"))
        report.recordPortalOpened()
        XCTAssertEqual(report.handoff, .portalOpened)
        XCTAssertTrue(report.confirmSubmission(receipt: "receipt"))
        XCTAssertTrue(report.selectCandidate("fdot-d6"))
        XCTAssertEqual(report.handoff, .draftPrepared)
        XCTAssertNil(report.receipt)
        XCTAssertEqual(report.previousReceipts, ["receipt"])
        let reopened = try PotPatrolJSON.decoder().decode(EditableReport.self, from: PotPatrolJSON.encoder().encode(report))
        XCTAssertEqual(reopened.selectedCandidateID, "fdot-d6")
        XCTAssertEqual(reopened.portalURL, report.portalURL)
        var edited = report.package.fields
        edited["latitude"] = .number(26)
        report.edit(fields: edited)
        XCTAssertNil(report.portalURL)
        XCTAssertFalse(report.selectCandidate("miami-dade-dtpw-311"))
        XCTAssertNil(report.selectedCandidateID)
    }
    func testRefreshReplacesBrokenFieldsAndKeepsEarlierReceipts() throws {
        let fresh = try DemoFixtures.report(for: SavedDrive(demoScenario: .destinationCandidates))
        var fields = fresh.fields
        fields["description"] = .object(["value": .string("Previously nested description"), "source": .string("template")])
        fields.removeValue(forKey: "latitude")
        fields.removeValue(forKey: "longitude")
        var broken = EditableReport(package: ReportPackage(reportID: fresh.reportID, fields: fields,
                                   destination: fresh.destination, submissionStatus: "not_submitted"))
        XCTAssertEqual(broken.package.fields["description"]?.text, "")
        let refreshed = broken.refreshed(with: fresh)
        XCTAssertFalse(refreshed.package.fields["description"]!.text.isEmpty)
        XCTAssertNotNil(refreshed.coordinate)
        XCTAssertFalse(refreshed.destinationNeedsReview)
        broken = EditableReport(package: fresh)
        XCTAssertTrue(broken.selectCandidate("miami-dade-dtpw-311"))
        broken.recordPortalOpened()
        XCTAssertTrue(broken.confirmSubmission(receipt: "real-receipt"))
        let replacement = broken.refreshed(with: fresh)
        XCTAssertEqual(replacement.handoff, .draftPrepared)
        XCTAssertEqual(replacement.previousReceipts, ["real-receipt"])
        XCTAssertNil(replacement.receipt)
        XCTAssertNil(replacement.selectedCandidateID)
    }
}
