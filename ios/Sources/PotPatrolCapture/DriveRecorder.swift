#if os(iOS)
import AVFoundation
import CoreLocation
import PotPatrolCore
import UIKit

public struct RecordedDrive: Sendable {
    public let videoURL: URL
    public let samples: [GPSSample]
    public let videoStartedAt: Date
    public let durationMilliseconds: Int64
}

public enum RecorderError: LocalizedError {
    case cameraDenied, noCamera, lowStorage, noFrames, unavailable(String)
    public var errorDescription: String? {
        switch self {
        case .cameraDenied: return "Camera access is off. Enable it in Settings while parked."
        case .noCamera: return "This device has no available back camera. Use the sample drive in the simulator."
        case .lowStorage: return "There is not enough storage to record. Free at least 150 MB and try again."
        case .noFrames: return "No video frames were recorded. Your local files have been retained."
        case .unavailable(let text): return text
        }
    }
}

/// Capture and writer state live exclusively on videoQueue. CLLocation timestamps are correlated
/// before dispatching, so neither video nor GPS callback latency changes the synchronized origin.
public final class DriveRecorder: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate, CLLocationManagerDelegate {
    public let session = AVCaptureSession()
    private let videoQueue = DispatchQueue(label: "PotPatrol.video-capture")
    private let output = AVCaptureVideoDataOutput()
    private let locationManager = CLLocationManager()
    private var configured = false
    private var writer: AVAssetWriter?
    private var input: AVAssetWriterInput?
    private var destination: URL?
    private var sidecarURL: URL?
    private var origin: VideoTimeOrigin?
    private var readings: [GPSReading] = []
    private var lastDisplayedSecond = -1
    private var captureError: Error?
    private var finishing = false
    private var authorizationContinuation: CheckedContinuation<Bool, Never>?
    public var onElapsed: (@Sendable (Int) -> Void)?
    public var onGPSAvailability: (@Sendable (Bool) -> Void)?
    public var onStopRequested: (@Sendable (String) -> Void)?
    private var observers: [NSObjectProtocol] = []

    public override init() {
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyBest
        locationManager.distanceFilter = kCLDistanceFilterNone
        locationManager.activityType = .automotiveNavigation
        for name in [AVCaptureSession.wasInterruptedNotification, AVCaptureSession.runtimeErrorNotification] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: session, queue: nil) { [weak self] _ in
                self?.onStopRequested?("Camera recording was interrupted. The drive is being saved.")
            })
        }
    }
    deinit { observers.forEach { NotificationCenter.default.removeObserver($0) } }

    @MainActor
    public func preparePermissions() async throws -> Bool {
        let allowed: Bool
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: allowed = true
        case .notDetermined: allowed = await AVCaptureDevice.requestAccess(for: .video)
        default: allowed = false
        }
        guard allowed else { throw RecorderError.cameraDenied }
        if locationManager.authorizationStatus == .notDetermined {
            return await withCheckedContinuation { continuation in
                authorizationContinuation = continuation
                locationManager.requestWhenInUseAuthorization()
            }
        }
        return locationAllowed
    }
    private var locationAllowed: Bool {
        [.authorizedWhenInUse, .authorizedAlways].contains(locationManager.authorizationStatus)
    }
    public func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        guard manager.authorizationStatus != .notDetermined else { return }
        authorizationContinuation?.resume(returning: locationAllowed)
        authorizationContinuation = nil
        onGPSAvailability?(locationAllowed)
    }
    public func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        let correlation = CaptureTimeBridge.clockCorrelation()
        let valid = locations.compactMap { CaptureTimeBridge.reading(from: $0, correlation: correlation) }
        onGPSAvailability?(!valid.isEmpty)
        videoQueue.async { [weak self] in
            guard let self, self.destination != nil, !self.finishing else { return }
            self.readings.append(contentsOf: valid)
            self.persistSidecar()
        }
    }
    public func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        onGPSAvailability?(false)
    }

    @MainActor
    public func start(videoURL: URL, sidecarURL: URL) async throws {
        let hasGPS = try await preparePermissions()
        let volume = try videoURL.deletingLastPathComponent().resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
        guard (volume.volumeAvailableCapacityForImportantUsage ?? 0) > 150_000_000 else { throw RecorderError.lowStorage }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            videoQueue.async {
                do {
                    guard self.destination == nil, !self.finishing else { throw RecorderError.unavailable("A recording is already active.") }
                    if !self.configured { try self.configureSession() }
                    self.destination = videoURL
                    self.sidecarURL = sidecarURL
                    self.readings = []
                    self.origin = nil
                    self.writer = nil
                    self.input = nil
                    self.captureError = nil
                    self.lastDisplayedSecond = -1
                    self.session.startRunning()
                    continuation.resume()
                } catch { continuation.resume(throwing: error) }
            }
        }
        UIApplication.shared.isIdleTimerDisabled = true
        if hasGPS { locationManager.startUpdatingLocation() }
        onGPSAvailability?(hasGPS)
    }
    private func configureSession() throws {
        session.beginConfiguration()
        defer { session.commitConfiguration() }
        session.sessionPreset = .hd1280x720
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) else { throw RecorderError.noCamera }
        let camera = try AVCaptureDeviceInput(device: device)
        guard session.canAddInput(camera), session.canAddOutput(output) else { throw RecorderError.noCamera }
        session.addInput(camera)
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: videoQueue)
        session.addOutput(output)
        if let connection = output.connection(with: .video), connection.isVideoRotationAngleSupported(90) {
            connection.videoRotationAngle = 90
        }
        configured = true
    }
    public func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let destination, !finishing, captureError == nil, CMSampleBufferDataIsReady(sampleBuffer) else { return }
        do {
            if writer == nil {
                guard let format = CMSampleBufferGetFormatDescription(sampleBuffer), let clock = session.masterClock else { return }
                let dimensions = CMVideoFormatDescriptionGetDimensions(format)
                let writer = try AVAssetWriter(outputURL: destination, fileType: .mp4)
                let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
                    AVVideoCodecKey: AVVideoCodecType.h264,
                    AVVideoWidthKey: dimensions.width, AVVideoHeightKey: dimensions.height,
                    AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 1_000_000, AVVideoAllowFrameReorderingKey: false]
                ])
                input.expectsMediaDataInRealTime = true
                guard writer.canAdd(input) else { throw RecorderError.unavailable("The camera format could not be recorded.") }
                writer.add(input)
                self.origin = try FirstVideoFrameWriter.append(sampleBuffer, to: writer, input: input, captureClock: clock)
                self.writer = writer
                self.input = input
                if let origin = self.origin {
                    let originURL = destination.deletingLastPathComponent().appendingPathComponent("capture-origin.json")
                    try PotPatrolJSON.encoder().encode(origin.firstFrameRecordedAt).write(to: originURL, options: .atomic)
                }
                persistSidecar()
            } else if let input, input.isReadyForMoreMediaData, !input.append(sampleBuffer) {
                throw writer?.error ?? RecorderError.unavailable("The video writer stopped accepting frames.")
            }
            if let origin, let clock = session.masterClock {
                let pts = CMSyncConvertTime(CMSampleBufferGetPresentationTimeStamp(sampleBuffer), from: clock, to: CMClockGetHostTimeClock())
                guard pts.isNumeric, pts.seconds.isFinite else { return }
                let elapsed = max(0, Int(pts.seconds - origin.firstFrameHostTimeSeconds))
                if elapsed != lastDisplayedSecond {
                    lastDisplayedSecond = elapsed
                    onElapsed?(elapsed)
                    let size = (try? destination.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
                    if elapsed >= 599 || size > 95 * 1_024 * 1_024 {
                        onStopRequested?("The recording limit was reached. The drive is being saved.")
                    }
                }
            }
        } catch {
            captureError = error
            onStopRequested?(error.localizedDescription)
        }
    }
    private func persistSidecar() {
        guard let origin, let sidecarURL else { return }
        do {
            let samples = PotPatrolAPIClient.canonicalSamples(RecordingTimeline(origin: origin).samples(from: readings))
            try PotPatrolJSON.encoder().encode(samples).write(to: sidecarURL, options: .atomic)
        } catch {
            captureError = error
            onStopRequested?("The GPS sidecar could not be saved. The recording is being stopped.")
        }
    }
    @MainActor
    public func stop() async throws -> RecordedDrive {
        locationManager.stopUpdatingLocation()
        UIApplication.shared.isIdleTimerDisabled = false
        return try await withCheckedThrowingContinuation { continuation in
            videoQueue.async {
                guard !self.finishing else { continuation.resume(throwing: RecorderError.unavailable("The drive is already being saved.")); return }
                self.finishing = true
                self.session.stopRunning()
                guard let writer = self.writer, let input = self.input, let origin = self.origin, let url = self.destination else {
                    self.destination = nil
                    self.finishing = false
                    continuation.resume(throwing: self.captureError ?? RecorderError.noFrames)
                    return
                }
                let readings = self.readings
                let sidecar = self.sidecarURL
                guard writer.status == .writing else {
                    self.destination = nil
                    self.finishing = false
                    continuation.resume(throwing: writer.error ?? RecorderError.noFrames)
                    return
                }
                input.markAsFinished()
                writer.finishWriting {
                    Task {
                        do {
                            guard writer.status == .completed else { throw writer.error ?? RecorderError.noFrames }
                            let duration = try await AVURLAsset(url: url).load(.duration).seconds
                            guard duration.isFinite, duration > 0, duration <= 600 else { throw RecorderError.noFrames }
                            let milliseconds = Int64((duration * 1_000).rounded())
                            let samples = PotPatrolAPIClient.canonicalSamples(RecordingTimeline(origin: origin).samples(from: readings, durationMilliseconds: milliseconds))
                            if let sidecar { try PotPatrolJSON.encoder().encode(samples).write(to: sidecar, options: .atomic) }
                            self.videoQueue.async {
                                self.destination = nil
                                self.writer = nil
                                self.input = nil
                                self.finishing = false
                                continuation.resume(returning: RecordedDrive(videoURL: url, samples: samples,
                                    videoStartedAt: origin.firstFrameRecordedAt, durationMilliseconds: milliseconds))
                            }
                        } catch {
                            self.videoQueue.async {
                                self.destination = nil
                                self.finishing = false
                                continuation.resume(throwing: error)
                            }
                        }
                    }
                }
            }
        }
    }
}
#endif
