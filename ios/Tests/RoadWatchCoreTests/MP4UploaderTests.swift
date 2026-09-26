import Foundation
import XCTest
@testable import RoadWatchCore

final class MP4UploaderTests: XCTestCase {
    private final class Transport: FileUploadTransport {
        var request: URLRequest?
        var fileURL: URL?
        var uploadedBytes: Data?
        var statusCode = 204
        var error: Error?

        func upload(_ request: URLRequest, fileURL: URL) async throws -> (Data, HTTPURLResponse) {
            self.request = request
            self.fileURL = fileURL
            if let error { throw error }
            uploadedBytes = try Data(contentsOf: fileURL)
            return (Data(), HTTPURLResponse(
                url: request.url!, statusCode: statusCode, httpVersion: "HTTP/1.1", headerFields: nil
            )!)
        }
    }

    private func fixtureFile() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID()).mp4")
        // Transport fixture only. Capture tests separately create and read a real MP4.
        try Data([0, 0, 0, 24, 102, 116, 121, 112, 109, 112, 52, 50]).write(to: url)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }

    func testAuthenticatedPUTUsesRawFileAndKeepsLocalCopy() async throws {
        let file = try fixtureFile()
        let transport = Transport()
        let instructions = UploadInstructions(
            url: URL(string: "https://upload.example.test/video?signature=fixture")!,
            headers: ["Authorization": "Bearer test-token", "x-upload-id": "test-drive"]
        )
        let receipt = try await MP4Uploader(transport: transport).upload(fileURL: file, instructions: instructions)
        XCTAssertEqual(receipt.statusCode, 204)
        XCTAssertEqual(transport.request?.httpMethod, "PUT")
        XCTAssertEqual(transport.request?.url, instructions.url)
        XCTAssertEqual(transport.request?.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
        XCTAssertEqual(transport.request?.value(forHTTPHeaderField: "Content-Type"), "video/mp4")
        XCTAssertEqual(transport.request?.value(forHTTPHeaderField: "x-upload-id"), "test-drive")
        XCTAssertNil(transport.request?.httpBody)
        XCTAssertEqual(transport.fileURL, file)
        XCTAssertEqual(transport.uploadedBytes, try Data(contentsOf: file))
        XCTAssertTrue(FileManager.default.fileExists(atPath: file.path))
    }

    func testPreservesBackendContentTypeAndSignedURLWithoutBearerToken() async throws {
        let transport = Transport()
        let instructions = UploadInstructions(
            url: URL(string: "https://storage.example.test/object?token=signed")!,
            headers: ["content-type": "application/octet-stream", "x-storage-token": "fixture"]
        )
        _ = try await MP4Uploader(transport: transport).upload(fileURL: fixtureFile(), instructions: instructions)
        XCTAssertEqual(transport.request?.value(forHTTPHeaderField: "Content-Type"), "application/octet-stream")
        XCTAssertEqual(transport.request?.url, instructions.url)
        XCTAssertNil(transport.request?.value(forHTTPHeaderField: "Authorization"))
    }

    func testHTTPFailuresKeepFileAndSurfaceStatusIncludingExpiredAuth() async throws {
        let file = try fixtureFile()
        for status in [301, 307, 401, 403, 413, 500] {
            let transport = Transport()
            transport.statusCode = status
            do {
                _ = try await MP4Uploader(transport: transport).upload(
                    fileURL: file,
                    instructions: UploadInstructions(url: URL(string: "https://upload.example.test/video")!, headers: [:])
                )
                XCTFail("Expected status \(status) to fail")
            } catch let error as UploadError {
                XCTAssertEqual(error, .rejected(statusCode: status))
            }
            XCTAssertTrue(FileManager.default.fileExists(atPath: file.path))
        }
    }

    func testNetworkFailureCanRetrySavedFileWithFreshHeaders() async throws {
        let file = try fixtureFile()
        let transport = Transport()
        transport.error = URLError(.networkConnectionLost)
        let uploader = MP4Uploader(transport: transport)
        let url = URL(string: "https://upload.example.test/video")!
        do {
            _ = try await uploader.upload(fileURL: file, instructions: UploadInstructions(url: url, headers: [:]))
            XCTFail("Expected network failure")
        } catch let error as URLError {
            XCTAssertEqual(error.code, .networkConnectionLost)
        }
        transport.error = nil
        _ = try await uploader.upload(
            fileURL: file, instructions: UploadInstructions(url: url, headers: ["Authorization": "Bearer refreshed"])
        )
        XCTAssertEqual(transport.request?.value(forHTTPHeaderField: "Authorization"), "Bearer refreshed")
        XCTAssertTrue(FileManager.default.fileExists(atPath: file.path))
    }

    func testMissingFileIsRejectedBeforeNetworkRequest() async throws {
        let transport = Transport()
        do {
            _ = try await MP4Uploader(transport: transport).upload(
                fileURL: URL(fileURLWithPath: "/missing-\(UUID()).mp4"),
                instructions: UploadInstructions(url: URL(string: "https://upload.example.test/video")!, headers: [:])
            )
            XCTFail("Expected missing file error")
        } catch let error as UploadError {
            XCTAssertEqual(error, .missingOrEmptyMP4)
        }
        XCTAssertNil(transport.request)
    }
}
