import Foundation

public enum JSONValue: Codable, Equatable, Sendable {
    case string(String), number(Double), bool(Bool), object([String: JSONValue]), array([JSONValue]), null
    public init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer()
        if value.decodeNil() { self = .null }
        else if let result = try? value.decode(Bool.self) { self = .bool(result) }
        else if let result = try? value.decode(Double.self) { self = .number(result) }
        else if let result = try? value.decode(String.self) { self = .string(result) }
        else if let result = try? value.decode([String: JSONValue].self) { self = .object(result) }
        else { self = .array(try value.decode([JSONValue].self)) }
    }
    public func encode(to encoder: Encoder) throws {
        var value = encoder.singleValueContainer()
        switch self {
        case .string(let item): try value.encode(item)
        case .number(let item): try value.encode(item)
        case .bool(let item): try value.encode(item)
        case .object(let item): try value.encode(item)
        case .array(let item): try value.encode(item)
        case .null: try value.encodeNil()
        }
    }
    public var text: String {
        switch self {
        case .string(let text): return text
        case .number(let number): return String(number)
        case .bool(let bool): return String(bool)
        case .null: return ""
        default: return ""
        }
    }
    public var number: Double? {
        if case .number(let number) = self { return number }
        return nil
    }
}

public enum PotPatrolJSON {
    public static func date(_ string: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: string) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: string)
    }
    public static func timestamp(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: date)
    }
    public static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let string = try decoder.singleValueContainer().decode(String.self)
            guard let date = Self.date(string) else {
                throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Invalid ISO 8601 timestamp"))
            }
            return date
        }
        return decoder
    }
    public static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            try container.encode(timestamp(date))
        }
        return encoder
    }
}

public struct DriveIdentity: Codable, Sendable {
    public let driveID: UUID
    public let status: String
    enum CodingKeys: String, CodingKey { case driveID = "drive_id", status }
}

public struct UploadTicket: Codable, Sendable {
    public let uploadURL: URL
    public let method: String
    public let headers: [String: String]
    public let expiresAt: Date
    enum CodingKeys: String, CodingKey {
        case uploadURL = "upload_url", method, headers, expiresAt = "expires_at"
    }
}

public struct HazardLocation: Codable, Sendable {
    public let latitude: Double?
    public let longitude: Double?
    public let horizontalAccuracyMeters: Double?
    public let source: String?
    enum CodingKeys: String, CodingKey {
        case latitude, longitude, horizontalAccuracyMeters = "horizontal_accuracy_m", source
    }
    public var coordinate: GeoCoordinate? { GeoCoordinate(latitude: latitude, longitude: longitude) }
}

public struct APIHazard: Codable, Identifiable, Sendable {
    public var id: UUID
    public let category: String
    public let confidence: Double?
    public let severity: String?
    public let severityBasis: String?
    public let evidenceURL: String?
    public let videoOffsetMilliseconds: Int64
    public let location: HazardLocation?
    public let reviewState: String?
    enum CodingKeys: String, CodingKey {
        case id = "hazard_id", category, confidence, severity, severityBasis = "severity_basis"
        case evidenceURL = "evidence_url", videoOffsetMilliseconds = "video_offset_ms", location
        case reviewState = "review_state"
    }
    public var locationLabel: String { location?.coordinate == nil ? "Location unavailable" : "Approximate location" }
}

public struct DriveSnapshot: Codable, Sendable {
    public var driveID: UUID
    public var status: String
    public var stage: String?
    public var error: String?
    public var hazards: [APIHazard]
    public var analysisMode: String?
    enum CodingKeys: String, CodingKey {
        case driveID = "drive_id", status, stage, error, hazards, analysisMode = "analysis_mode"
    }
    public var isFinished: Bool { status == "complete" || status == "failed" }
}

public struct ReportDestination: Codable, Sendable {
    public let status: String
    public let url: String?
    public var verifiedURL: URL? {
        guard status == "verified", let url = url.flatMap(URL.init(string:)),
              url.scheme?.lowercased() == "https", url.host != nil else { return nil }
        return url
    }
}

public struct ReportPackage: Codable, Sendable {
    public let reportID: UUID
    public var fields: [String: JSONValue]
    public let destination: ReportDestination
    public let submissionStatus: String
    enum CodingKeys: String, CodingKey {
        case reportID = "report_id", fields, destination, submissionStatus = "submission_status"
    }
}
