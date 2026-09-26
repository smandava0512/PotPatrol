import Foundation

public enum LocalDriveState: String, Codable, Sendable {
    case recording, saved, uploading, queued, processing, complete, failed
}

public enum DemoScenario: String, CaseIterable, Codable, Sendable {
    case pothole, noGPS, noHazards, processingFailure, unsupportedDestination
    public var label: String {
        switch self {
        case .pothole: return "Pothole with GPS"
        case .noGPS: return "Pothole without GPS"
        case .noHazards: return "No hazards"
        case .processingFailure: return "Processing failure"
        case .unsupportedDestination: return "Unsupported destination"
        }
    }
}

public struct SavedDrive: Codable, Identifiable, Sendable {
    public let id: UUID
    public let createdAt: Date
    public var state: LocalDriveState
    public var videoStartedAt: Date?
    public var durationMilliseconds: Int64?
    public var serverID: UUID?
    public var serverBaseURL: String?
    public var videoUploaded = false
    public var nextGPSIndex = 0
    public var completionAcknowledged = false
    public var snapshot: DriveSnapshot?
    public var lastError: String?
    public var interrupted = false
    public var demoScenario: DemoScenario?
    public var queuedAt: Date?
    public var reports: [String: EditableReport] = [:]
    public init(id: UUID = UUID(), createdAt: Date = Date(), demoScenario: DemoScenario? = nil) {
        self.id = id
        self.createdAt = createdAt
        self.state = .recording
        self.demoScenario = demoScenario
    }
    public var isDemo: Bool { demoScenario != nil }
    public var usesFixtureAnalysis: Bool { isDemo || snapshot?.analysisMode == "fixture" }
}

public struct DriveLibrary: Sendable {
    public let drives: [SavedDrive]
    public let unreadableDriveIDs: [UUID]
}

/// Each drive owns its MP4, GPS sidecar, receipts and edited reports. No token is persisted here.
public actor SavedDriveRepository {
    public let root: URL
    public init(root: URL) { self.root = root }
    public func directory(_ id: UUID) -> URL { root.appendingPathComponent(id.uuidString, isDirectory: true) }
    public func videoURL(_ id: UUID) -> URL { directory(id).appendingPathComponent("drive.mp4") }
    public func locationsURL(_ id: UUID) -> URL { directory(id).appendingPathComponent("locations.json") }
    public func evidenceURL(_ id: UUID, hazardID: UUID) -> URL {
        directory(id).appendingPathComponent("\(hazardID.uuidString).jpg")
    }
    public func save(_ drive: SavedDrive) throws {
        let folder = directory(drive.id)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try PotPatrolJSON.encoder().encode(drive).write(to: folder.appendingPathComponent("drive.json"), options: .atomic)
    }
    public func load(_ id: UUID) throws -> SavedDrive {
        try PotPatrolJSON.decoder().decode(SavedDrive.self, from: Data(contentsOf: directory(id).appendingPathComponent("drive.json")))
    }
    @discardableResult
    public func update(_ id: UUID, change: @Sendable (inout SavedDrive) -> Void) throws -> SavedDrive {
        var drive = try load(id)
        change(&drive)
        try save(drive)
        return drive
    }
    public func library() throws -> DriveLibrary {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let folders = try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)
        var drives: [SavedDrive] = []
        var unreadable: [UUID] = []
        for folder in folders {
            guard let id = UUID(uuidString: folder.lastPathComponent) else { continue }
            do { drives.append(try load(id)) } catch { unreadable.append(id) }
        }
        return DriveLibrary(drives: drives.sorted { $0.createdAt > $1.createdAt }, unreadableDriveIDs: unreadable)
    }
    public func saveSamples(_ samples: [GPSSample], id: UUID) throws {
        try FileManager.default.createDirectory(at: directory(id), withIntermediateDirectories: true)
        let canonical = PotPatrolAPIClient.canonicalSamples(samples)
        try PotPatrolJSON.encoder().encode(canonical).write(to: locationsURL(id), options: .atomic)
    }
    public func samples(_ id: UUID) throws -> [GPSSample] {
        try PotPatrolJSON.decoder().decode([GPSSample].self, from: Data(contentsOf: locationsURL(id)))
    }
    public func saveEvidence(_ data: Data, id: UUID, hazardID: UUID) throws -> URL {
        let url = evidenceURL(id, hazardID: hazardID)
        try data.write(to: url, options: .atomic)
        return url
    }
}
