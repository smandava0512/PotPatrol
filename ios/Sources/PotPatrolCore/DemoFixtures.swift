import Foundation

/// Deterministic backup/demo only. Never represents live inference or an actual submission.
public enum DemoFixtures {
    public static var videoURL: URL { Bundle.module.resourceURL!.appendingPathComponent("Fixtures/sample-drive.mp4") }
    public static var evidenceURL: URL { Bundle.module.resourceURL!.appendingPathComponent("Fixtures/sample-evidence.jpg") }
    private static func examples() throws -> [String: Any] {
        let url = Bundle.module.resourceURL!.appendingPathComponent("Fixtures/api-examples.json")
        guard let object = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any] else {
            throw PotPatrolAPIError.invalidResponse
        }
        return object
    }
    public static func samples() throws -> [GPSSample] {
        let batch = try examples()["locations_request"] as! [String: Any]
        return try PotPatrolJSON.decoder().decode([GPSSample].self, from: JSONSerialization.data(withJSONObject: batch["samples"]!))
    }
    public static func snapshot(for drive: SavedDrive) throws -> DriveSnapshot {
        var object = try examples()["result"] as! [String: Any]
        object["drive_id"] = (drive.serverID ?? drive.id).uuidString
        var hazards = object["hazards"] as! [[String: Any]]
        for index in hazards.indices {
            hazards[index]["hazard_id"] = drive.id.uuidString
            if drive.demoScenario == .noGPS { hazards[index]["location"] = NSNull() }
        }
        object["hazards"] = hazards
        if drive.demoScenario == .noHazards { object["hazards"] = [] }
        if drive.demoScenario == .processingFailure {
            object["status"] = "failed"
            object["stage"] = "failed"
            object["error"] = "Demo processing failure. Your local drive is retained for retry."
            object["hazards"] = []
        }
        return try PotPatrolJSON.decoder().decode(DriveSnapshot.self, from: JSONSerialization.data(withJSONObject: object))
    }
    public static func report(for drive: SavedDrive) throws -> ReportPackage {
        var object = try examples()["report_draft"] as! [String: Any]
        object["report_id"] = drive.id.uuidString
        if drive.demoScenario == .unsupportedDestination {
            object["destination"] = ["status": "unsupported", "url": NSNull()] as [String: Any]
        }
        if drive.demoScenario == .noGPS {
            var fields = object["fields"] as! [String: Any]
            fields["latitude"] = NSNull()
            fields["longitude"] = NSNull()
            object["fields"] = fields
        }
        return try PotPatrolJSON.decoder().decode(ReportPackage.self, from: JSONSerialization.data(withJSONObject: object))
    }
}
