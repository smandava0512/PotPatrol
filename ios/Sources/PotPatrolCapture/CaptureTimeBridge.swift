import AVFoundation
import CoreLocation
import PotPatrolCore

public enum CaptureTimeBridge {
    /// Use the host clock for both video and GPS. Midpoint sampling reduces clock-read skew.
    public static func clockCorrelation() -> ClockCorrelation {
        let clock = CMClockGetHostTimeClock()
        let before = CMClockGetTime(clock).seconds
        let wallTime = Date()
        let after = CMClockGetTime(clock).seconds
        return ClockCorrelation(recordedAt: wallTime, hostTimeSeconds: before + (after - before) / 2)
    }

    /// Call in didUpdateLocations. Uses CLLocation.timestamp, not the callback arrival time.
    /// Collect readings during capture; finalize offsets when the writer's origin is available.
    public static func reading(
        from location: CLLocation,
        correlation: ClockCorrelation? = nil
    ) -> GPSReading? {
        guard location.horizontalAccuracy.isFinite, location.horizontalAccuracy >= 0,
              CLLocationCoordinate2DIsValid(location.coordinate) else { return nil }
        let correlation = correlation ?? clockCorrelation()
        return GPSReading(
            recordedAt: location.timestamp,
            measuredHostTimeSeconds: correlation.hostTime(for: location.timestamp),
            latitude: location.coordinate.latitude,
            longitude: location.coordinate.longitude,
            horizontalAccuracyMeters: location.horizontalAccuracy,
            speedMetersPerSecond: location.speed >= 0 && location.speedAccuracy >= 0 ? location.speed : nil,
            headingDegrees: location.course >= 0 && location.courseAccuracy >= 0 ? location.course : nil
        )
    }
}

public enum FirstVideoFrameError: Error {
    case writerAlreadyStarted
    case invalidVideoFrame
    case invalidCaptureClock
    case writerFailed
    case firstFrameNotWritten
}

/// Call once on the recorder's serial video queue with its first candidate video frame.
/// Create the writer with .mp4 and add the video input before calling this helper.
public enum FirstVideoFrameWriter {
    public static func append(
        _ sampleBuffer: CMSampleBuffer,
        to writer: AVAssetWriter,
        input: AVAssetWriterInput,
        captureClock: CMClock
    ) throws -> VideoTimeOrigin {
        guard writer.status == .unknown else { throw FirstVideoFrameError.writerAlreadyStarted }
        guard input.mediaType == .video,
              CMSampleBufferDataIsReady(sampleBuffer),
              let format = CMSampleBufferGetFormatDescription(sampleBuffer),
              CMFormatDescriptionGetMediaType(format) == kCMMediaType_Video else {
            throw FirstVideoFrameError.invalidVideoFrame
        }
        let presentationTime = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        guard presentationTime.isValid, presentationTime.isNumeric else {
            throw FirstVideoFrameError.invalidVideoFrame
        }
        // Pass captureSession.masterClock (or synchronizationClock on newer SDKs), not callback time.
        let hostTime = CMSyncConvertTime(presentationTime, from: captureClock, to: CMClockGetHostTimeClock())
        guard hostTime.isValid, hostTime.isNumeric, hostTime.seconds.isFinite else {
            throw FirstVideoFrameError.invalidCaptureClock
        }
        let correlation = CaptureTimeBridge.clockCorrelation()
        guard writer.startWriting() else { throw writer.error ?? FirstVideoFrameError.writerFailed }
        writer.startSession(atSourceTime: presentationTime)
        guard input.isReadyForMoreMediaData, input.append(sampleBuffer) else {
            let error = writer.error ?? FirstVideoFrameError.firstFrameNotWritten
            // Never retain a time origin for a frame that was dropped or rejected.
            writer.cancelWriting()
            throw error
        }
        return VideoTimeOrigin(
            firstFrameHostTimeSeconds: hostTime.seconds,
            firstFrameRecordedAt: correlation.date(forHostTime: hostTime.seconds)
        )
    }
}
