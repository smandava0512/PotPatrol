import Foundation

public enum ReportHandoffState: String, Codable, Sendable {
    case draftPrepared, portalOpened, submissionConfirmed
    public var label: String {
        switch self {
        case .draftPrepared: return "Draft prepared"
        case .portalOpened: return "Portal opened"
        case .submissionConfirmed: return "Submission confirmed by you"
        }
    }
}

public struct EditableReport: Codable, Sendable {
    public var package: ReportPackage
    public private(set) var handoff: ReportHandoffState = .draftPrepared
    public private(set) var receipt: String?
    public private(set) var previousReceipts: [String]?
    public var destinationNeedsReview = false
    public init(package: ReportPackage) { self.package = package }
    public var coordinate: GeoCoordinate? {
        GeoCoordinate(latitude: package.fields["latitude"]?.number, longitude: package.fields["longitude"]?.number)
    }
    public var portalURL: URL? {
        guard coordinate != nil, !destinationNeedsReview else { return nil }
        return package.destination.verifiedURL
    }
    public mutating func edit(fields: [String: JSONValue]) {
        if package.fields != fields, handoff != .draftPrepared {
            if let receipt { previousReceipts = (previousReceipts ?? []) + [receipt] }
            receipt = nil
            handoff = .draftPrepared
        }
        if package.fields["latitude"] != fields["latitude"] || package.fields["longitude"] != fields["longitude"] {
            destinationNeedsReview = true
        }
        package.fields = fields
    }
    public mutating func recordPortalOpened() {
        guard portalURL != nil else { return }
        if handoff != .submissionConfirmed { handoff = .portalOpened }
    }
    @discardableResult
    public mutating func confirmSubmission(receipt: String) -> Bool {
        let receipt = receipt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard handoff == .portalOpened, !receipt.isEmpty else { return false }
        self.receipt = receipt
        handoff = .submissionConfirmed
        return true
    }
    public var shareText: String {
        var lines = ["Pot Patrol report draft", package.fields["description"]?.text ?? ""]
        if let coordinate { lines.append("Approximate coordinates: \(coordinate.latitude), \(coordinate.longitude)") }
        else { lines.append("Location unavailable — manual review required") }
        lines.append("Destination status: \(package.destination.status)")
        lines.append(handoff.label)
        return lines.joined(separator: "\n")
    }
}
