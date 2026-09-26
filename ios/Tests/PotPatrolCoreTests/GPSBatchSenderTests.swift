import Foundation
import XCTest
@testable import PotPatrolCore

final class GPSBatchSenderTests: XCTestCase {
    private final class Transport: GPSRequestTransport {
        var request: URLRequest?
        var statusCode = 200

        func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
            self.request = request
            return (Data(), HTTPURLResponse(
                url: request.url!, statusCode: statusCode, httpVersion: "HTTP/1.1", headerFields: nil
            )!)
        }
    }

    private func request() -> URLRequest {
        // This path is a transport-test fixture; the adapter will use the backend's actual URL.
        var request = URLRequest(url: URL(string: "https://backend.example.test/test-fixture")!)
        request.httpMethod = "POST"
        request.setValue("Bearer test-token", forHTTPHeaderField: "Authorization")
        request.setValue("fixed-batch-fixture", forHTTPHeaderField: "x-test-batch-id")
        return request
    }

    func testSendsMillisecondSamplesWithAdapterSuppliedEnvelopeAndAuth() async throws {
        let date = Date(timeIntervalSince1970: 1_700_000_000)
        let samples = RecordingTimeline(origin: VideoTimeOrigin(
            firstFrameHostTimeSeconds: 100, firstFrameRecordedAt: date
        )).samples(from: [GPSReading(
            recordedAt: date.addingTimeInterval(1.5), measuredHostTimeSeconds: 101.5,
            latitude: 25.75, longitude: -80.25, horizontalAccuracyMeters: 5
        )])
        struct TestEnvelope: Encodable { let fixturePoints: [GPSSample] }
        let transport = Transport()
        let receipt = try await GPSBatchSender(transport: transport).send(samples, request: request()) {
            try JSONEncoder().encode(TestEnvelope(fixturePoints: $0))
        }
        XCTAssertEqual(receipt.statusCode, 200)
        let sent = try XCTUnwrap(transport.request)
        XCTAssertEqual(sent.httpMethod, "POST")
        XCTAssertEqual(sent.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
        XCTAssertEqual(sent.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertEqual(sent.value(forHTTPHeaderField: "x-test-batch-id"), "fixed-batch-fixture")
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(sent.httpBody)) as? [String: Any])
        let points = try XCTUnwrap(json["fixturePoints"] as? [[String: Any]])
        XCTAssertEqual(points.first?["offset_ms"] as? Int, 1_500)
    }

    func testEmptyGPSTrackCanBeSentWithoutInventedPoints() async throws {
        let transport = Transport()
        _ = try await GPSBatchSender(transport: transport).send([], request: request()) {
            try JSONEncoder().encode($0)
        }
        XCTAssertEqual(transport.request?.httpBody, Data("[]".utf8))
    }

    func testRejectedGPSBatchDoesNotAppearComplete() async throws {
        let transport = Transport()
        transport.statusCode = 401
        do {
            _ = try await GPSBatchSender(transport: transport).send([], request: request()) {
                try JSONEncoder().encode($0)
            }
            XCTFail("Expected auth rejection")
        } catch let error as GPSSubmissionError {
            XCTAssertEqual(error, .rejected(statusCode: 401))
        }
    }
}
