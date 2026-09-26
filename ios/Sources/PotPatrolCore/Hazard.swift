import Foundation

public struct GeoCoordinate: Equatable, Sendable {
    public let latitude: Double
    public let longitude: Double

    public init?(latitude: Double?, longitude: Double?) {
        guard let latitude, let longitude,
              latitude.isFinite, longitude.isFinite,
              (-90...90).contains(latitude), (-180...180).contains(longitude) else {
            return nil
        }
        self.latitude = latitude
        self.longitude = longitude
    }
}

/// Domain model only; backend JSON mapping belongs in the adapter once its contract is published.
public struct Hazard: Identifiable, Sendable {
    public let id: UUID
    public let category: String
    public let videoOffsetMilliseconds: Int64
    public let evidenceURL: URL?
    public let coordinate: GeoCoordinate?
    public let horizontalAccuracyMeters: Double?

    public init(
        id: UUID,
        category: String,
        videoOffsetMilliseconds: Int64,
        evidenceURL: URL?,
        coordinate: GeoCoordinate?,
        horizontalAccuracyMeters: Double? = nil
    ) {
        self.id = id
        self.category = category
        self.videoOffsetMilliseconds = max(0, videoOffsetMilliseconds)
        self.evidenceURL = evidenceURL
        self.coordinate = coordinate
        self.horizontalAccuracyMeters = horizontalAccuracyMeters.flatMap {
            $0.isFinite && $0 >= 0 ? $0 : nil
        }
    }

    public var requiresLocationReview: Bool { coordinate == nil }
    public var locationLabel: String { coordinate == nil ? "Location unavailable" : "Approximate location" }
}
