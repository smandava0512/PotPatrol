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
    public private(set) var selectedCandidateID: String?
    private var originalCoordinates: [String: JSONValue]?
    public var destinationNeedsReview = false
    public init(package: ReportPackage) {
        self.package = package
        originalCoordinates = Self.coordinates(in: package.fields)
    }
    public var coordinate: GeoCoordinate? {
        GeoCoordinate(latitude: package.fields["latitude"]?.number, longitude: package.fields["longitude"]?.number)
    }
    public var portalURL: URL? {
        guard coordinate != nil, !destinationNeedsReview else { return nil }
        if package.destination.status == "verified" { return package.destination.verifiedURL }
        guard package.destination.status == "needs_review" else { return nil }
        return selectedCandidate?.httpsURL
    }
    public var selectedCandidate: ReportDestinationCandidate? {
        package.destination.candidates?.first { $0.id == selectedCandidateID }
    }
    private static func coordinates(in fields: [String: JSONValue]) -> [String: JSONValue] {
        ["latitude": fields["latitude"] ?? .null, "longitude": fields["longitude"] ?? .null]
    }
    private static func normalized(_ fields: [String: JSONValue]) -> [String: JSONValue] {
        fields.merging(coordinates(in: fields)) { _, coordinate in coordinate }
    }
    private mutating func invalidateHandoff() {
        if let receipt { previousReceipts = (previousReceipts ?? []) + [receipt] }
        receipt = nil
        handoff = .draftPrepared
    }
    public mutating func edit(fields: [String: JSONValue]) {
        if Self.normalized(package.fields) != Self.normalized(fields), handoff != .draftPrepared {
            invalidateHandoff()
        }
        // Old saved drafts have no baseline. Trust their current fields only if they were not already marked edited.
        if originalCoordinates == nil, !destinationNeedsReview {
            originalCoordinates = Self.coordinates(in: package.fields)
        }
        destinationNeedsReview = originalCoordinates.map { $0 != Self.coordinates(in: fields) } ?? true
        if destinationNeedsReview { selectedCandidateID = nil }
        package.fields = fields
    }
    @discardableResult
    public mutating func selectCandidate(_ id: String) -> Bool {
        guard package.destination.status == "needs_review", coordinate != nil, !destinationNeedsReview,
              let candidate = package.destination.candidates?.first(where: { $0.id == id }),
              candidate.httpsURL != nil else { return false }
        if selectedCandidateID != id {
            invalidateHandoff()
            selectedCandidateID = id
        }
        return true
    }
    public func refreshed(with package: ReportPackage) -> EditableReport {
        var refreshed = EditableReport(package: package)
        refreshed.previousReceipts = previousReceipts
        if let receipt { refreshed.previousReceipts = (previousReceipts ?? []) + [receipt] }
        return refreshed
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
        if let candidate = selectedCandidate {
            lines.append("Candidate agency selected by you: \(candidate.name)")
            if let url = candidate.httpsURL { lines.append("Agency page: \(url.absoluteString)") }
            lines.append("Road ownership still requires review.")
        }
        lines.append(handoff.label)
        return lines.joined(separator: "\n")
    }
}
