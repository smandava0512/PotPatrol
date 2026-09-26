import Foundation

/// App-side instructions. The backend adapter will populate these from the final contract.
/// Headers can contain a bearer token or storage-specific authentication; the URL can be signed.
public struct UploadInstructions: Sendable {
    public let url: URL
    public let headers: [String: String]

    public init(url: URL, headers: [String: String]) {
        self.url = url
        self.headers = headers
    }
}

public struct UploadReceipt: Sendable {
    public let statusCode: Int
    public let responseBody: Data
}

public enum UploadError: Error, Equatable {
    case invalidURL
    case missingOrEmptyMP4
    case nonHTTPResponse
    case rejected(statusCode: Int)
}

public protocol FileUploadTransport {
    func upload(_ request: URLRequest, fileURL: URL) async throws -> (Data, HTTPURLResponse)
}

/// Redirects require new backend instructions, so PUT cannot silently become GET or change host.
private final class UploadTaskDelegate: NSObject, URLSessionTaskDelegate {
    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping @Sendable (URLRequest?) -> Void
    ) {
        completionHandler(nil)
    }
}

public final class URLSessionFileUploadTransport: FileUploadTransport {
    private let session: URLSession

    public init(session: URLSession = .shared) {
        self.session = session
    }

    public func upload(_ request: URLRequest, fileURL: URL) async throws -> (Data, HTTPURLResponse) {
        let delegate = UploadTaskDelegate()
        let (data, response) = try await session.upload(for: request, fromFile: fileURL, delegate: delegate)
        guard let response = response as? HTTPURLResponse else {
            throw UploadError.nonHTTPResponse
        }
        return (data, response)
    }
}

public struct MP4Uploader {
    private let transport: any FileUploadTransport

    public init(transport: any FileUploadTransport = URLSessionFileUploadTransport()) {
        self.transport = transport
    }

    /// Uploads the MP4 as the raw request body. Keeps the local file on both success and failure.
    /// A receipt confirms only the PUT; the backend's drive completion step remains separate.
    public func upload(fileURL: URL, instructions: UploadInstructions) async throws -> UploadReceipt {
        guard instructions.url.scheme?.lowercased() == "https", instructions.url.host != nil else {
            throw UploadError.invalidURL
        }
        guard fileURL.isFileURL, fileURL.pathExtension.lowercased() == "mp4",
              let values = try? fileURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey]),
              values.isRegularFile == true, (values.fileSize ?? 0) > 0 else {
            throw UploadError.missingOrEmptyMP4
        }

        var request = URLRequest(url: instructions.url)
        request.httpMethod = "PUT"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        for (name, value) in instructions.headers {
            request.setValue(value, forHTTPHeaderField: name)
        }
        if request.value(forHTTPHeaderField: "Content-Type") == nil {
            request.setValue("video/mp4", forHTTPHeaderField: "Content-Type")
        }

        let (body, response) = try await transport.upload(request, fileURL: fileURL)
        guard (200..<300).contains(response.statusCode) else {
            // In particular, 401/403 must surface so the caller can obtain fresh authentication.
            throw UploadError.rejected(statusCode: response.statusCode)
        }
        return UploadReceipt(statusCode: response.statusCode, responseBody: body)
    }
}
