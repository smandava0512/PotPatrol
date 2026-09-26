import AVFoundation
import CoreLocation
import XCTest
import RoadWatchCore
@testable import RoadWatchCapture

final class CaptureTimeBridgeTests: XCTestCase {
    func testCoreLocationUsesMeasurementTimestampDespiteDelayedDelivery() throws {
        let date = Date(timeIntervalSince1970: 1_700_000_000)
        let location = CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: 25.75, longitude: -80.25),
            altitude: 0, horizontalAccuracy: 5, verticalAccuracy: -1,
            course: -1, courseAccuracy: -1, speed: -1, speedAccuracy: -1,
            timestamp: date.addingTimeInterval(2)
        )
        let reading = try XCTUnwrap(CaptureTimeBridge.reading(
            from: location,
            correlation: ClockCorrelation(recordedAt: date.addingTimeInterval(7), hostTimeSeconds: 107)
        ))
        XCTAssertEqual(reading.measuredHostTimeSeconds, 102)
        XCTAssertEqual(reading.recordedAt, location.timestamp)
        XCTAssertNil(reading.speedMetersPerSecond)
        XCTAssertNil(reading.headingDegrees)
    }

    func testInvalidCoreLocationFixIsNotInvented() {
        let location = CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: 25.75, longitude: -80.25),
            altitude: 0, horizontalAccuracy: -1, verticalAccuracy: -1, timestamp: Date()
        )
        XCTAssertNil(CaptureTimeBridge.reading(from: location))
    }

    func testFirstWrittenFrameDefinesZeroInPlayableMP4() async throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID()).mp4")
        defer { try? FileManager.default.removeItem(at: url) }
        let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: 64,
            AVVideoHeightKey: 64,
            AVVideoCompressionPropertiesKey: [AVVideoAllowFrameReorderingKey: false]
        ])
        input.expectsMediaDataInRealTime = true
        XCTAssertTrue(writer.canAdd(input))
        writer.add(input)
        // Simulate a frame delivered late; callback time must not become the recording origin.
        let pts = CMTimeSubtract(CMClockGetTime(CMClockGetHostTimeClock()), CMTime(value: 1, timescale: 5))
        let buffer = try videoBuffer(presentationTime: pts)
        let origin = try FirstVideoFrameWriter.append(
            buffer, to: writer, input: input, captureClock: CMClockGetHostTimeClock()
        )
        XCTAssertEqual(origin.firstFrameHostTimeSeconds, pts.seconds, accuracy: 0.000_001)
        XCTAssertGreaterThan(Date().timeIntervalSince(origin.firstFrameRecordedAt), 0.15)
        input.markAsFinished()
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            writer.finishWriting { continuation.resume() }
        }
        XCTAssertEqual(writer.status, .completed, "\(String(describing: writer.error))")
        let asset = AVURLAsset(url: url)
        let tracks = try await asset.loadTracks(withMediaType: .video)
        let track = try XCTUnwrap(tracks.first)
        let reader = try AVAssetReader(asset: asset)
        let output = AVAssetReaderTrackOutput(track: track, outputSettings: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
        ])
        reader.add(output)
        XCTAssertTrue(reader.startReading())
        let decodedFirstFrame = try XCTUnwrap(output.copyNextSampleBuffer())
        XCTAssertEqual(CMSampleBufferGetPresentationTimeStamp(decodedFirstFrame).seconds, 0, accuracy: 0.001)
        XCTAssertNotNil(CMSampleBufferGetImageBuffer(decodedFirstFrame))
    }

    private func videoBuffer(presentationTime: CMTime) throws -> CMSampleBuffer {
        var pixelBuffer: CVPixelBuffer?
        XCTAssertEqual(CVPixelBufferCreate(
            kCFAllocatorDefault, 64, 64, kCVPixelFormatType_32BGRA, nil, &pixelBuffer
        ), kCVReturnSuccess)
        let pixels = try XCTUnwrap(pixelBuffer)
        CVPixelBufferLockBaseAddress(pixels, [])
        let address = try XCTUnwrap(CVPixelBufferGetBaseAddress(pixels))
        address.initializeMemory(as: UInt8.self, repeating: 0, count: CVPixelBufferGetDataSize(pixels))
        CVPixelBufferUnlockBaseAddress(pixels, [])
        var format: CMVideoFormatDescription?
        XCTAssertEqual(CMVideoFormatDescriptionCreateForImageBuffer(
            allocator: kCFAllocatorDefault, imageBuffer: pixels, formatDescriptionOut: &format
        ), noErr)
        var timing = CMSampleTimingInfo(
            duration: CMTime(value: 1, timescale: 30), presentationTimeStamp: presentationTime,
            decodeTimeStamp: .invalid
        )
        var buffer: CMSampleBuffer?
        XCTAssertEqual(CMSampleBufferCreateReadyWithImageBuffer(
            allocator: kCFAllocatorDefault, imageBuffer: pixels,
            formatDescription: try XCTUnwrap(format), sampleTiming: &timing, sampleBufferOut: &buffer
        ), noErr)
        return try XCTUnwrap(buffer)
    }
}
