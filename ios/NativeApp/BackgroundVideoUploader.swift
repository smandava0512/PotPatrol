import Foundation
import PotPatrolCore

extension Notification.Name { static let videoTransferChanged = Notification.Name("PotPatrol.videoTransferChanged") }

/// File-backed background transfers are reattached using the same session identifier on launch.
/// Receipts are persisted before the system's background-event completion handler is released.
final class BackgroundVideoUploader: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    static let identifier = "com.potpatrol.video-uploads"
    private let repository: SavedDriveRepository
    private let lock = NSLock()
    private var continuations: [UUID: CheckedContinuation<Void, Error>] = [:]
    private var completedSuccesses: Set<UUID> = []
    private var pendingWrites = 0
    private var eventsFinished = false
    private var completionHandler: (() -> Void)?
    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.background(withIdentifier: Self.identifier)
        config.isDiscretionary = false
        config.sessionSendsLaunchEvents = true
        config.waitsForConnectivity = true
        let queue = OperationQueue()
        queue.maxConcurrentOperationCount = 1
        return URLSession(configuration: config, delegate: self, delegateQueue: queue)
    }()
    init(repository: SavedDriveRepository) {
        self.repository = repository
        super.init()
        _ = session
    }
    func attachBackgroundEvents(completion: @escaping () -> Void) {
        lock.lock()
        let alreadyFinished = eventsFinished && pendingWrites == 0
        completionHandler = alreadyFinished ? nil : completion
        lock.unlock()
        if alreadyFinished { DispatchQueue.main.async(execute: completion) }
    }
    private func tasks() async -> [URLSessionTask] {
        await withCheckedContinuation { continuation in session.getAllTasks { continuation.resume(returning: $0) } }
    }
    func upload(fileURL: URL, localDriveID: UUID, request: URLRequest) async throws {
        if try await repository.load(localDriveID).videoUploaded { return }
        try await withCheckedThrowingContinuation { continuation in
            lock.lock()
            if completedSuccesses.remove(localDriveID) != nil {
                lock.unlock()
                continuation.resume()
                return
            }
            guard continuations[localDriveID] == nil else {
                lock.unlock()
                continuation.resume(throwing: PotPatrolAPIError.configuration("This drive is already uploading."))
                return
            }
            continuations[localDriveID] = continuation
            eventsFinished = false
            lock.unlock()
            Task {
                let existing = await tasks().first { $0.taskDescription == localDriveID.uuidString && $0.state != .completed }
                beginTransfer(existing: existing, fileURL: fileURL, id: localDriveID, request: request)
            }
        }
    }
    private func beginTransfer(existing: URLSessionTask?, fileURL: URL, id: UUID, request: URLRequest) {
        lock.lock()
        defer { lock.unlock() }
        guard continuations[id] != nil else { return }
        let task = existing ?? session.uploadTask(with: request, fromFile: fileURL)
        task.taskDescription = id.uuidString
        task.resume()
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard let id = task.taskDescription.flatMap(UUID.init(uuidString:)) else { return }
        let status = (task.response as? HTTPURLResponse)?.statusCode
        let result: Result<Void, Error>
        if let error { result = .failure(error) }
        else if let status, (200..<300).contains(status) { result = .success(()) }
        else { result = .failure(PotPatrolAPIError.http(status ?? 0, "Video transfer was not confirmed.")) }
        lock.lock()
        pendingWrites += 1
        lock.unlock()
        Task {
            var deliveredResult = result
            do {
                try await repository.update(id) { drive in
                    switch result {
                    case .success: drive.videoUploaded = true; drive.lastError = nil
                    case .failure(let error): drive.lastError = error.localizedDescription
                    }
                }
            } catch { deliveredResult = .failure(error) }
            finishWrite(id: id, result: deliveredResult)
            await MainActor.run { NotificationCenter.default.post(name: .videoTransferChanged, object: nil) }
        }
    }
    private func finishWrite(id: UUID, result: Result<Void, Error>) {
        lock.lock()
        let continuation = continuations.removeValue(forKey: id)
        if continuation == nil, case .success = result { completedSuccesses.insert(id) }
        pendingWrites -= 1
        let completion = eventsFinished && pendingWrites == 0 ? completionHandler : nil
        if completion != nil { completionHandler = nil }
        lock.unlock()
        continuation?.resume(with: result)
        if let completion { DispatchQueue.main.async(execute: completion) }
    }
    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        lock.lock()
        eventsFinished = true
        let completion = pendingWrites == 0 ? completionHandler : nil
        if completion != nil { completionHandler = nil }
        lock.unlock()
        if let completion { DispatchQueue.main.async(execute: completion) }
    }
}
