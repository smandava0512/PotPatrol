import Foundation

public enum GPSSubmissionError: Error, Equatable {
    case invalidRequest
    case nonHTTPResponse
    case rejected(statusCode: Int)
}

public protocol GPSRequestTransport {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionGPSRequestTransport: GPSRequestTransport {
    private let session: URLSession

    public init(session: URLSession = .shared) {
        self.session = session
    }

    public func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await session.data(for: request, delegate: GPSRequestDelegate())
        guard let response = response as? HTTPURLResponse else {
            throw GPSSubmissionError.nonHTTPResponse
        }
        return (data, response)
    }
}

private final class GPSRequestDelegate: NSObject, URLSessionTaskDelegate {
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

public struct GPSBatchReceipt: Sendable {
    public let statusCode: Int
    public let responseBody: Data
}

public struct GPSBatchSender {
    private let transport: any GPSRequestTransport

    public init(transport: any GPSRequestTransport = URLSessionGPSRequestTransport()) {
        self.transport = transport
    }

    /// The backend adapter supplies the endpoint, authentication/idempotency headers and envelope.
    /// Reuse the same finalized samples on retry; this helper never recalculates offsets.
    public func send(
        _ samples: [GPSSample],
        request: URLRequest,
        encodeBody: ([GPSSample]) throws -> Data
    ) async throws -> GPSBatchReceipt {
        guard request.httpMethod == "POST",
              request.url?.scheme?.lowercased() == "https", request.url?.host != nil else {
            throw GPSSubmissionError.invalidRequest
        }
        var request = request
        request.httpBody = try encodeBody(samples)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        if request.value(forHTTPHeaderField: "Content-Type") == nil {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (body, response) = try await transport.send(request)
        guard (200..<300).contains(response.statusCode) else {
            throw GPSSubmissionError.rejected(statusCode: response.statusCode)
        }
        return GPSBatchReceipt(statusCode: response.statusCode, responseBody: body)
    }
}
