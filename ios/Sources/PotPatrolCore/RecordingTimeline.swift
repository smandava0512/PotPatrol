import Foundation

/// A wall-clock/monotonic-clock correlation measured at one instant, in seconds.
public struct ClockCorrelation: Sendable {
    public let recordedAt: Date
    public let hostTimeSeconds: Double

    public init(recordedAt: Date, hostTimeSeconds: Double) {
        self.recordedAt = recordedAt
        self.hostTimeSeconds = hostTimeSeconds
    }

    public func hostTime(for timestamp: Date) -> Double {
        hostTimeSeconds + timestamp.timeIntervalSince(recordedAt)
    }

    public func date(forHostTime time: Double) -> Date {
        recordedAt.addingTimeInterval(time - hostTimeSeconds)
    }
}

/// Set only after the first video sample has successfully entered the MP4 writer.
/// Host time is meaningful within this device boot; persist finalized GPS offsets, not raw readings.
public struct VideoTimeOrigin: Sendable {
    public let firstFrameHostTimeSeconds: Double
    public let firstFrameRecordedAt: Date

    public init(firstFrameHostTimeSeconds: Double, firstFrameRecordedAt: Date) {
        self.firstFrameHostTimeSeconds = firstFrameHostTimeSeconds
        self.firstFrameRecordedAt = firstFrameRecordedAt
    }
}

public struct GPSReading: Sendable {
    public let recordedAt: Date
    public let measuredHostTimeSeconds: Double
    public let latitude: Double
    public let longitude: Double
    public let horizontalAccuracyMeters: Double
    public let speedMetersPerSecond: Double?
    public let headingDegrees: Double?

    public init(
        recordedAt: Date,
        measuredHostTimeSeconds: Double,
        latitude: Double,
        longitude: Double,
        horizontalAccuracyMeters: Double,
        speedMetersPerSecond: Double? = nil,
        headingDegrees: Double? = nil
    ) {
        self.recordedAt = recordedAt
        self.measuredHostTimeSeconds = measuredHostTimeSeconds
        self.latitude = latitude
        self.longitude = longitude
        self.horizontalAccuracyMeters = horizontalAccuracyMeters
        self.speedMetersPerSecond = speedMetersPerSecond
        self.headingDegrees = headingDegrees
    }
}

/// Sample fields from the plan's initial proposal. No endpoint or batch envelope is assumed.
public struct GPSSample: Encodable, Equatable, Sendable {
    public let offsetMilliseconds: Int64
    public let recordedAt: Date
    public let latitude: Double
    public let longitude: Double
    public let horizontalAccuracyMeters: Double
    public let speedMetersPerSecond: Double?
    public let headingDegrees: Double?

    enum CodingKeys: String, CodingKey {
        case offsetMilliseconds = "offset_ms"
        case recordedAt = "recorded_at"
        case latitude, longitude
        case horizontalAccuracyMeters = "horizontal_accuracy_m"
        case speedMetersPerSecond = "speed_mps"
        case headingDegrees = "heading_deg"
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(offsetMilliseconds, forKey: .offsetMilliseconds)
        let formatter = ISO8601DateFormatter()
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        try container.encode(formatter.string(from: recordedAt), forKey: .recordedAt)
        try container.encode(latitude, forKey: .latitude)
        try container.encode(longitude, forKey: .longitude)
        try container.encode(horizontalAccuracyMeters, forKey: .horizontalAccuracyMeters)
        // Explicit null values distinguish unavailable sensors from measured zero.
        try container.encode(speedMetersPerSecond, forKey: .speedMetersPerSecond)
        try container.encode(headingDegrees, forKey: .headingDegrees)
    }
}

public struct RecordingTimeline: Sendable {
    public let origin: VideoTimeOrigin

    public init(origin: VideoTimeOrigin) {
        self.origin = origin
    }

    public func samples(from readings: [GPSReading], durationMilliseconds: Int64? = nil) -> [GPSSample] {
        readings.compactMap { reading in
            let offset = (reading.measuredHostTimeSeconds - origin.firstFrameHostTimeSeconds) * 1_000
            guard offset.isFinite, offset >= 0, offset < Double(Int64.max),
                  durationMilliseconds.map({ offset <= Double($0) }) ?? true,
                  reading.recordedAt.timeIntervalSince1970.isFinite,
                  GeoCoordinate(latitude: reading.latitude, longitude: reading.longitude) != nil,
                  reading.horizontalAccuracyMeters.isFinite, reading.horizontalAccuracyMeters >= 0 else {
                return nil
            }
            let speed = reading.speedMetersPerSecond.flatMap { $0.isFinite && $0 >= 0 ? $0 : nil }
            let heading = reading.headingDegrees.flatMap { $0.isFinite && (0..<360).contains($0) ? $0 : nil }
            return GPSSample(
                offsetMilliseconds: Int64(offset.rounded()),
                recordedAt: reading.recordedAt,
                latitude: reading.latitude,
                longitude: reading.longitude,
                horizontalAccuracyMeters: reading.horizontalAccuracyMeters,
                speedMetersPerSecond: speed,
                headingDegrees: heading
            )
        }.sorted {
            if $0.offsetMilliseconds != $1.offsetMilliseconds {
                return $0.offsetMilliseconds < $1.offsetMilliseconds
            }
            return $0.recordedAt < $1.recordedAt
        }
    }
}
