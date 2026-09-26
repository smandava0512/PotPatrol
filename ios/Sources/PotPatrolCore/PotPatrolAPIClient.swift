import Foundation

public enum PotPatrolAPIError: LocalizedError {
    case configuration(String), invalidResponse, http(Int, String), incompatibleUpload, unsafeEvidence
    public var errorDescription: String? {
        switch self {
        case .configuration(let message): return message
        case .invalidResponse: return "The server returned an unexpected response."
        case .http(let code, let detail):
            if code == 401 { return "The device token was rejected. Check the connection settings." }
            return "Server error \(code): \(detail)"
        case .incompatibleUpload: return "The server did not provide a compatible authenticated PUT upload."
        case .unsafeEvidence: return "The evidence URL does not belong to the configured API server."
        }
    }
    public var canRetry: Bool {
        if case .http(let code, _) = self { return code == 429 || code >= 500 }
        return false
    }
}

public struct APIConnection: Sendable {
    public let baseURL: URL
    private let deviceToken: String
    public let allowDevelopmentHTTP: Bool
    public init(baseURL: URL, deviceToken: String, allowDevelopmentHTTP: Bool = false) throws {
        let scheme = baseURL.scheme?.lowercased()
        guard baseURL.host != nil, baseURL.user == nil, baseURL.password == nil,
              baseURL.query == nil, baseURL.fragment == nil,
              scheme == "https" || (scheme == "http" && allowDevelopmentHTTP) else {
            throw PotPatrolAPIError.configuration("Use an HTTPS server URL, or explicitly enable HTTP for local development.")
        }
        guard !deviceToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw PotPatrolAPIError.configuration("Enter the device token provided by Developer 2.")
        }
        self.baseURL = baseURL
        self.deviceToken = deviceToken
        self.allowDevelopmentHTTP = allowDevelopmentHTTP
    }
    public func isSameOrigin(_ url: URL) -> Bool {
        func port(_ url: URL) -> Int { url.port ?? (url.scheme?.lowercased() == "https" ? 443 : 80) }
        return url.scheme?.lowercased() == baseURL.scheme?.lowercased()
            && url.host?.lowercased() == baseURL.host?.lowercased() && port(url) == port(baseURL)
    }
    public func authenticated(_ request: URLRequest) throws -> URLRequest {
        guard let url = request.url, isSameOrigin(url) else { throw PotPatrolAPIError.unsafeEvidence }
        var request = request
        request.setValue(deviceToken, forHTTPHeaderField: "X-Device-Token")
        return request
    }
}

private final class APIRedirectDelegate: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

public struct PotPatrolAPIClient {
    public let connection: APIConnection
    private let session: URLSession
    public init(connection: APIConnection, session: URLSession = .shared) {
        self.connection = connection
        self.session = session
    }
    private func request(_ path: String, method: String = "GET", body: Data? = nil) throws -> URLRequest {
        var request = URLRequest(url: connection.baseURL.appendingPathComponent(path))
        request.httpMethod = method
        request.httpBody = body
        request.cachePolicy = .reloadIgnoringLocalCacheData
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        return try connection.authenticated(request)
    }
    private func perform(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: request, delegate: APIRedirectDelegate())
        guard let response = response as? HTTPURLResponse else { throw PotPatrolAPIError.invalidResponse }
        guard (200..<300).contains(response.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"]
            throw PotPatrolAPIError.http(response.statusCode, detail.map { String(describing: $0).prefix(500).description } ?? "Request failed")
        }
        return data
    }
    private func decode<T: Decodable>(_ type: T.Type, path: String, method: String = "GET", body: Data? = nil) async throws -> T {
        try PotPatrolJSON.decoder().decode(type, from: await perform(request(path, method: method, body: body)))
    }
    public func createDrive() async throws -> DriveIdentity {
        try await decode(DriveIdentity.self, path: "v1/drives", method: "POST", body: Data("{}".utf8))
    }
    public func initializeUpload(driveID: UUID) async throws -> UploadTicket {
        try await decode(UploadTicket.self, path: "v1/drives/\(driveID.uuidString)/upload-init", method: "POST", body: Data("{}".utf8))
    }
    public func uploadRequest(ticket: UploadTicket) throws -> URLRequest {
        guard ticket.method.uppercased() == "PUT", connection.isSameOrigin(ticket.uploadURL) else {
            throw PotPatrolAPIError.incompatibleUpload
        }
        var request = URLRequest(url: ticket.uploadURL)
        request.httpMethod = "PUT"
        for (name, value) in ticket.headers { request.setValue(value, forHTTPHeaderField: name) }
        if request.value(forHTTPHeaderField: "Content-Type") == nil { request.setValue("video/mp4", forHTTPHeaderField: "Content-Type") }
        return try connection.authenticated(request)
    }
    public func uploadVideo(fileURL: URL, ticket: UploadTicket) async throws {
        let (data, response) = try await session.upload(for: uploadRequest(ticket: ticket), fromFile: fileURL, delegate: APIRedirectDelegate())
        guard let response = response as? HTTPURLResponse else { throw PotPatrolAPIError.invalidResponse }
        guard (200..<300).contains(response.statusCode) else {
            throw PotPatrolAPIError.http(response.statusCode, String(data: data, encoding: .utf8)?.prefix(500).description ?? "Upload rejected")
        }
    }
    public static func canonicalSamples(_ samples: [GPSSample]) -> [GPSSample] {
        var byOffset: [Int64: GPSSample] = [:]
        for sample in samples {
            if let old = byOffset[sample.offsetMilliseconds],
               old.horizontalAccuracyMeters < sample.horizontalAccuracyMeters
                || (old.horizontalAccuracyMeters == sample.horizontalAccuracyMeters && old.recordedAt <= sample.recordedAt) { continue }
            byOffset[sample.offsetMilliseconds] = sample
        }
        return byOffset.keys.sorted().compactMap { byOffset[$0] }
    }
    public func sendLocations(driveID: UUID, samples: [GPSSample]) async throws -> Int {
        guard samples.count <= 2_000, samples.allSatisfy({ (0...600_000).contains($0.offsetMilliseconds) }) else {
            throw PotPatrolAPIError.configuration("The GPS batch exceeds the v1 recording limits.")
        }
        struct Point: Encodable {
            let sample: GPSSample
            enum CodingKeys: String, CodingKey { case offset_ms, recorded_at, latitude, longitude, horizontal_accuracy_m, speed_mps }
            func encode(to encoder: Encoder) throws {
                var container = encoder.container(keyedBy: CodingKeys.self)
                try container.encode(sample.offsetMilliseconds, forKey: .offset_ms)
                try container.encode(PotPatrolJSON.timestamp(sample.recordedAt), forKey: .recorded_at)
                try container.encode(sample.latitude, forKey: .latitude)
                try container.encode(sample.longitude, forKey: .longitude)
                try container.encode(sample.horizontalAccuracyMeters, forKey: .horizontal_accuracy_m)
                try container.encode(sample.speedMetersPerSecond, forKey: .speed_mps)
                // v1 forbids heading_deg. Keep heading in the local sidecar only.
            }
        }
        struct Batch: Encodable { let samples: [Point] }
        struct Receipt: Decodable { let accepted: Int }
        let body = try PotPatrolJSON.encoder().encode(Batch(samples: Self.canonicalSamples(samples).map { Point(sample: $0) }))
        return try await decode(Receipt.self, path: "v1/drives/\(driveID.uuidString)/locations", method: "POST", body: body).accepted
    }
    public func completeDrive(driveID: UUID) async throws -> DriveIdentity {
        // video_started_at/duration are proposals, not part of the current authoritative v1 body.
        try await decode(DriveIdentity.self, path: "v1/drives/\(driveID.uuidString)/complete", method: "POST", body: Data("{}".utf8))
    }
    public func retryAnalysis(driveID: UUID) async throws -> DriveIdentity {
        try await decode(DriveIdentity.self, path: "v1/drives/\(driveID.uuidString)/retry", method: "POST", body: Data("{}".utf8))
    }
    public func drive(driveID: UUID) async throws -> DriveSnapshot {
        try await decode(DriveSnapshot.self, path: "v1/drives/\(driveID.uuidString)")
    }
    public func reportDraft(hazardID: UUID) async throws -> ReportPackage {
        try await decode(ReportPackage.self, path: "v1/hazards/\(hazardID.uuidString)/report-draft", method: "POST", body: Data("{}".utf8))
    }
    public func evidence(path: String) async throws -> Data {
        guard let url = URL(string: path, relativeTo: connection.baseURL)?.absoluteURL,
              connection.isSameOrigin(url) else { throw PotPatrolAPIError.unsafeEvidence }
        return try await perform(connection.authenticated(URLRequest(url: url)))
    }
}
