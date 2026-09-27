import MapKit
import PotPatrolCore
import SwiftUI

public struct HazardDetailView: View {
    public let hazard: Hazard

    public init(hazard: Hazard) {
        self.hazard = hazard
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(hazard.category.capitalized).font(.title2.bold())
                Text("\(hazard.videoOffsetMilliseconds / 1_000) seconds into drive")
                    .foregroundStyle(.secondary)
                if let url = hazard.evidenceURL {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .empty: ProgressView("Loading evidence")
                        case .success(let image): image.resizable().scaledToFit()
                        case .failure: Text("Evidence could not be loaded. Try again when connected.")
                        @unknown default: Text("Evidence unavailable")
                        }
                    }
                } else {
                    Text("Evidence unavailable").foregroundStyle(.secondary)
                }
                Label(hazard.locationLabel, systemImage: hazard.requiresLocationReview ? "location.slash" : "location")
                    .font(.headline)
                if let coordinate = hazard.coordinate {
                    Map(initialPosition: .region(MKCoordinateRegion(
                        center: CLLocationCoordinate2D(latitude: coordinate.latitude, longitude: coordinate.longitude),
                        span: MKCoordinateSpan(latitudeDelta: 0.005, longitudeDelta: 0.005)
                    ))) {
                        Marker("Approximate hazard location", coordinate: CLLocationCoordinate2D(
                            latitude: coordinate.latitude, longitude: coordinate.longitude
                        ))
                    }
                    .frame(height: 220)
                    if let accuracy = hazard.horizontalAccuracyMeters {
                        Text("GPS accuracy: ±\(accuracy.formatted(.number.precision(.fractionLength(0)))) m")
                            .foregroundStyle(.secondary)
                    }
                } else {
                    Text("Review the location before choosing a reporting destination.")
                }
            }
            .padding()
        }
        .navigationTitle("Hazard details")
    }
}
