import AVFoundation
import Combine
import PotPatrolCapture
import PotPatrolCore
import UIKit

enum AppRoute: Hashable { case drive(UUID), hazard(UUID, UUID) }

@MainActor
final class AppState: ObservableObject {
    static let shared = AppState()
    @Published var drives: [SavedDrive] = []
    @Published var path: [AppRoute] = []
    @Published var activeRecordingID: UUID?
    @Published var elapsed = 0
    @Published var hasGPS = false
    @Published var savingRecording = false
    @Published var preparingRecording = false
    @Published var notice: String?
    @Published var settings = ConnectionSettings()
    let repository: SavedDriveRepository
    let recorder = DriveRecorder()
    let videoUploader: BackgroundVideoUploader
    private var busy: Set<UUID> = []
    private var preparingDriveID: UUID?
    private var backgroundSavingTask: UIBackgroundTaskIdentifier = .invalid

    init() {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let testID = ProcessInfo.processInfo.environment["POTPATROL_UI_TEST_ID"]
        let root = support.appendingPathComponent(testID.map { "PotPatrol-UI-\($0)" } ?? "PotPatrol", isDirectory: true)
            .appendingPathComponent("drives", isDirectory: true)
        repository = SavedDriveRepository(root: root)
        videoUploader = BackgroundVideoUploader(repository: repository)
        recorder.onElapsed = { [weak self] elapsed in Task { @MainActor in self?.elapsed = elapsed } }
        recorder.onGPSAvailability = { [weak self] value in Task { @MainActor in self?.hasGPS = value } }
        recorder.onStopRequested = { [weak self] reason in
            Task { @MainActor in
                guard let self, let id = self.activeRecordingID, self.drive(id)?.isDemo == false else { return }
                await self.stopRecording(reason: reason)
            }
        }
        Task { await reload(); await recoverInterruptedCaptures(); await resumeSavedDrives() }
    }
    func reload() async {
        do {
            let library = try await repository.library()
            drives = library.drives
            if !library.unreadableDriveIDs.isEmpty {
                notice = "Some saved drive metadata could not be read. The original files are still on this iPhone."
            }
        } catch { notice = error.localizedDescription }
    }
    func drive(_ id: UUID) -> SavedDrive? { drives.first { $0.id == id } }
    private func client(for drive: SavedDrive) throws -> PotPatrolAPIClient {
        let client = try settings.client()
        if let original = drive.serverBaseURL, original != client.connection.baseURL.absoluteString {
            throw PotPatrolAPIError.configuration("This drive belongs to another server. Restore its original connection before retrying.")
        }
        return client
    }
    func saveConnection(baseURL: String, token: String, developmentHTTP: Bool) async throws {
        guard let url = URL(string: baseURL.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            throw PotPatrolAPIError.configuration("Enter a valid server URL.")
        }
        _ = try APIConnection(baseURL: url, deviceToken: token, allowDevelopmentHTTP: developmentHTTP)
        try DeviceTokenStore.save(token.trimmingCharacters(in: .whitespacesAndNewlines))
        settings.baseURL = url.absoluteString
        settings.developmentHTTP = developmentHTTP
        settings.save()
        await resumeSavedDrives()
    }
    func preparePermissions() async {
        do {
            hasGPS = try await recorder.preparePermissions()
            notice = hasGPS ? "Camera and location are ready." : "Camera is ready. Recording will work without GPS."
        } catch { notice = error.localizedDescription }
    }
    func startRecording(demo: DemoScenario? = nil) async {
        guard activeRecordingID == nil, !preparingRecording else { return }
        preparingRecording = true
        defer { preparingRecording = false; preparingDriveID = nil }
        let drive = SavedDrive(demoScenario: demo)
        preparingDriveID = drive.id
        do {
            try await repository.save(drive)
            try await repository.saveSamples([], id: drive.id)
            if demo == nil {
                _ = try await recorder.preparePermissions()
                guard UIApplication.shared.applicationState == .active else {
                    throw RecorderError.unavailable("Return to Pot Patrol and start again while parked.")
                }
            }
            elapsed = 0
            hasGPS = false
            savingRecording = false
            await reload()
            activeRecordingID = drive.id
            if demo == nil {
                try await recorder.start(videoURL: repository.videoURL(drive.id), sidecarURL: repository.locationsURL(drive.id))
            }
        } catch {
            try? await repository.update(drive.id) { $0.state = .failed; $0.lastError = error.localizedDescription }
            activeRecordingID = nil
            notice = error.localizedDescription
            await reload()
        }
    }
    func stopRecording(reason: String? = nil) async {
        guard let id = activeRecordingID, !savingRecording, let drive = drive(id) else { return }
        savingRecording = true
        if !drive.isDemo {
            backgroundSavingTask = UIApplication.shared.beginBackgroundTask(withName: "Save Pot Patrol drive") { }
        }
        defer {
            activeRecordingID = nil
            savingRecording = false
            if backgroundSavingTask != .invalid {
                UIApplication.shared.endBackgroundTask(backgroundSavingTask)
                backgroundSavingTask = .invalid
            }
        }
        do {
            let started: Date
            let duration: Int64
            if drive.isDemo {
                let target = await repository.videoURL(id)
                try FileManager.default.copyItem(at: DemoFixtures.videoURL, to: target)
                let seconds = try await AVURLAsset(url: target).load(.duration).seconds
                duration = Int64((seconds * 1_000).rounded())
                let samples = drive.demoScenario == .noGPS ? [] : try DemoFixtures.samples().filter { $0.offsetMilliseconds <= duration }
                try await repository.saveSamples(samples, id: id)
                started = samples.first?.recordedAt ?? Date()
            } else {
                let result = try await recorder.stop()
                duration = result.durationMilliseconds
                started = result.videoStartedAt
                try await repository.saveSamples(result.samples, id: id)
            }
            try await repository.update(id) {
                $0.state = .saved
                $0.videoStartedAt = started
                $0.durationMilliseconds = duration
                $0.interrupted = reason != nil
                $0.lastError = reason
            }
            await reload()
            path = [.drive(id)]
            if drive.isDemo { Task { await upload(id) } }
        } catch {
            try? await repository.update(id) { $0.state = .failed; $0.lastError = error.localizedDescription; $0.interrupted = true }
            notice = error.localizedDescription
            await reload()
        }
    }
    private func recoverInterruptedCaptures() async {
        for drive in drives where drive.state == .recording && drive.id != activeRecordingID && drive.id != preparingDriveID {
            do {
                let url = await repository.videoURL(drive.id)
                let duration = try await AVURLAsset(url: url).load(.duration).seconds
                guard duration.isFinite, duration > 0, duration <= 600 else { throw RecorderError.noFrames }
                if (try? await repository.samples(drive.id)) == nil { try await repository.saveSamples([], id: drive.id) }
                let originURL = url.deletingLastPathComponent().appendingPathComponent("capture-origin.json")
                let recoveredOrigin = (try? Data(contentsOf: originURL)).flatMap { try? PotPatrolJSON.decoder().decode(Date.self, from: $0) }
                try await repository.update(drive.id) {
                    $0.state = .saved; $0.interrupted = true; $0.durationMilliseconds = Int64((duration * 1_000).rounded())
                    $0.videoStartedAt = recoveredOrigin
                    $0.lastError = "Recording was interrupted. Review the saved clip before uploading."
                }
            } catch {
                try? await repository.update(drive.id) { $0.state = .failed; $0.interrupted = true; $0.lastError = "The interrupted clip could not be finalized. Local files are retained." }
            }
        }
        await reload()
    }
    func resumeSavedDrives() async {
        for drive in drives where drive.state == .saved || drive.state == .uploading {
            // Resume only uploads previously approved for this exact server.
            if drive.isDemo { Task { await upload(drive.id) } }
            else if !drive.interrupted, let client = try? client(for: drive),
                    drive.mayUpload(to: client.connection.baseURL) {
                Task { await upload(drive.id) }
            }
        }
        for drive in drives where drive.state == .queued || drive.state == .processing {
            await refresh(drive.id)
        }
    }
    private func withRetry<T>(_ operation: () async throws -> T) async throws -> T {
        for attempt in 0..<3 {
            do { return try await operation() }
            catch {
                let transient = (error as? PotPatrolAPIError)?.canRetry == true
                    || [.timedOut, .networkConnectionLost, .cannotConnectToHost, .notConnectedToInternet].contains((error as? URLError)?.code ?? .unknown)
                guard transient, attempt < 2 else { throw error }
                try await Task.sleep(for: .seconds(attempt + 1))
            }
        }
        throw PotPatrolAPIError.invalidResponse
    }
    func approveUpload(_ id: UUID) async {
        guard let saved = drive(id), saved.state == .saved, !saved.isDemo else { return }
        do {
            let client = try client(for: saved)
            try await repository.update(id) { $0.approvedUploadBaseURL = client.connection.baseURL.absoluteString }
            await reload()
            await upload(id)
        } catch { notice = error.localizedDescription }
    }
    func upload(_ id: UUID) async {
        guard !busy.contains(id), let saved = drive(id), saved.state != .recording else { return }
        busy.insert(id)
        defer { busy.remove(id) }
        do {
            if saved.isDemo {
                try await repository.update(id) { $0.state = .uploading; $0.lastError = nil }
                await reload()
                try await Task.sleep(for: .milliseconds(400))
                try await repository.update(id) { $0.state = .queued; $0.queuedAt = Date() }
                await reload()
                return
            }
            let client = try client(for: saved)
            guard saved.mayUpload(to: client.connection.baseURL) else {
                throw PotPatrolAPIError.configuration("Review the saved clip and choose Send video and GPS for analysis before uploading.")
            }
            if let serverID = saved.serverID {
                let snapshot = try await withRetry { try await client.drive(driveID: serverID) }
                if !["created", "uploading"].contains(snapshot.status) {
                    try await persist(snapshot, id: id)
                    await reload()
                    return
                }
            }
            if saved.serverID == nil {
                let response = try await client.createDrive()
                try await repository.update(id) { $0.serverID = response.driveID; $0.serverBaseURL = client.connection.baseURL.absoluteString }
            }
            var drive = try await repository.load(id)
            guard let serverID = drive.serverID else { throw PotPatrolAPIError.invalidResponse }
            try await repository.update(id) { $0.state = .uploading; $0.lastError = nil }
            await reload()
            if !drive.videoUploaded {
                try await withRetry {
                    let ticket = try await client.initializeUpload(driveID: serverID)
                    let request = try client.uploadRequest(ticket: ticket)
                    try await self.videoUploader.upload(fileURL: self.repository.videoURL(id), localDriveID: id, request: request)
                }
            }
            drive = try await repository.load(id)
            let samples = try await repository.samples(id)
            guard drive.nextGPSIndex <= samples.count else { throw PotPatrolAPIError.configuration("The saved GPS upload checkpoint is invalid.") }
            // Empty tracks still send the documented envelope, so no-GPS handling is explicit.
            if samples.isEmpty { _ = try await withRetry { try await client.sendLocations(driveID: serverID, samples: []) } }
            while drive.nextGPSIndex < samples.count {
                let end = min(drive.nextGPSIndex + 2_000, samples.count)
                let batch = Array(samples[drive.nextGPSIndex..<end])
                _ = try await withRetry { try await client.sendLocations(driveID: serverID, samples: batch) }
                drive = try await repository.update(id) { $0.nextGPSIndex = end }
            }
            _ = try await withRetry { try await client.completeDrive(driveID: serverID, videoStartedAt: drive.videoStartedAt) }
            try await repository.update(id) { $0.state = .queued; $0.completionAcknowledged = true; $0.lastError = nil }
            await reload()
        } catch {
            try? await repository.update(id) { $0.lastError = error.localizedDescription }
            await reload()
        }
    }
    private func persist(_ snapshot: DriveSnapshot, id: UUID) async throws {
        try await repository.update(id) {
            $0.snapshot = snapshot
            $0.state = LocalDriveState(rawValue: snapshot.status) ?? .processing
            $0.lastError = snapshot.error
            if ["queued", "processing", "complete", "failed"].contains(snapshot.status) { $0.completionAcknowledged = true }
        }
    }
    func refresh(_ id: UUID) async {
        guard let drive = drive(id) else { return }
        do {
            if drive.isDemo {
                guard let queuedAt = drive.queuedAt else { return }
                if Date().timeIntervalSince(queuedAt) < 2 {
                    try await repository.update(id) { $0.state = .processing }
                } else { try await persist(DemoFixtures.snapshot(for: drive), id: id) }
            } else if let serverID = drive.serverID {
                try await persist(client(for: drive).drive(driveID: serverID), id: id)
            }
            await reload()
        } catch {
            if error is CancellationError { return }
            try? await repository.update(id) { $0.lastError = error.localizedDescription }
            await reload()
        }
    }
    func retry(_ id: UUID) async {
        guard let drive = drive(id) else { return }
        do {
            if drive.snapshot?.status == "failed", !drive.isDemo, let serverID = drive.serverID {
                _ = try await client(for: drive).retryAnalysis(driveID: serverID)
                try await repository.update(id) { $0.state = .queued; $0.lastError = nil }
            } else { await upload(id) }
            await reload()
        } catch { notice = error.localizedDescription }
    }
    func report(_ id: UUID, hazardID: UUID, refresh: Bool = false) async throws -> EditableReport {
        let drive = try await repository.load(id)
        let cached = drive.reports[hazardID.uuidString]
        if let cached, !refresh { return cached }
        let package = drive.isDemo ? try DemoFixtures.report(for: drive) : try await client(for: drive).reportDraft(hazardID: hazardID)
        let report = cached?.refreshed(with: package) ?? EditableReport(package: package)
        try await saveReport(report, id: id, hazardID: hazardID)
        return report
    }
    func saveReport(_ report: EditableReport, id: UUID, hazardID: UUID) async throws {
        try await repository.update(id) { $0.reports[hazardID.uuidString] = report }
        await reload()
    }
    func evidence(_ id: UUID, hazard: APIHazard) async throws -> (Data, URL) {
        let drive = try await repository.load(id)
        let cached = await repository.evidenceURL(id, hazardID: hazard.id)
        if let data = try? Data(contentsOf: cached) { return (data, cached) }
        let data: Data
        if drive.isDemo { data = try Data(contentsOf: DemoFixtures.evidenceURL) }
        else {
            guard let path = hazard.evidenceURL else { throw PotPatrolAPIError.invalidResponse }
            data = try await client(for: drive).evidence(path: path)
        }
        return (data, try await repository.saveEvidence(data, id: id, hazardID: hazard.id))
    }
    func enteredBackground() {
        if let id = activeRecordingID, drive(id)?.isDemo == false {
            Task { await stopRecording(reason: "Recording stopped when Pot Patrol left the foreground.") }
        }
    }
}
