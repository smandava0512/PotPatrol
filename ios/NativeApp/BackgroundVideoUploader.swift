import Foundation
import PotPatrolCore

extension Notification.Name { static let videoTransferChanged = Notification.Name("PotPatrol.videoTransferChanged") }

/// File-backed uploads use a default session so redirects can be refused before the
/// private video is sent elsewhere. Interrupted transfers retry from the retained file.
final class BackgroundVideoUploader: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    private static let legacyIdentifier = "com.potpatrol.video-uploads"
    private let repository: SavedDriveRepository
    private let lock = NSLock()
    private var continuations: [UUID: CheckedContinuation<Void, Error>] = [:]
    private lazy var session: URLSession = {
        let queue = OperationQueue()
        queue.maxConcurrentOperationCount = 1
        return URLSession(configuration: UploadSessionSafety.configuration(), delegate: self, delegateQueue: queue)
    }()
    init(repository: SavedDriveRepository) {
        self.repository = repository
        super.init()
        _ = session
    }
    /// Previous releases handed uploads to iOS without a review checkpoint. Reattach
    /// on first launch after upgrade and cancel any remaining OS-owned transfers.
    func cancelLegacyTransfers() async {
        let configuration = URLSessionConfiguration.background(withIdentifier: Self.legacyIdentifier)
        let legacy = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        let tasks = await withCheckedContinuation { continuation in
            legacy.getAllTasks { continuation.resume(returning: $0) }
        }
        for task in tasks { task.cancel() }
        legacy.invalidateAndCancel()
    }
    func upload(fileURL: URL, localDriveID: UUID, request: URLRequest) async throws {
        if try await repository.load(localDriveID).videoUploaded { return }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            lock.lock()
            guard continuations[localDriveID] == nil else {
                lock.unlock()
                continuation.resume(throwing: PotPatrolAPIError.configuration("This drive is already uploading."))
                return
            }
            continuations[localDriveID] = continuation
            lock.unlock()
            let task = session.uploadTask(with: request, fromFile: fileURL)
            task.taskDescription = localDriveID.uuidString
            task.resume()
        }
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(UploadSessionSafety.redirect(request))
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if session.configuration.identifier == Self.legacyIdentifier { return }
        guard let id = task.taskDescription.flatMap(UUID.init(uuidString:)) else { return }
        let status = (task.response as? HTTPURLResponse)?.statusCode
        let result: Result<Void, Error>
        if let error { result = .failure(error) }
        else if let status, (200..<300).contains(status) { result = .success(()) }
        else { result = .failure(PotPatrolAPIError.http(status ?? 0, "Video transfer was not confirmed.")) }
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
        lock.unlock()
        continuation?.resume(with: result)
    }
}
