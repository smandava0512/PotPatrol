import AVKit
import MapKit
import PotPatrolCore
import SwiftUI

struct DriveStatusView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.scenePhase) private var phase
    let id: UUID
    @State private var videoURL: URL?
    @State private var sampleCount: Int?
    @State private var showVideo = false
    private var drive: SavedDrive? { state.drive(id) }
    var body: some View {
        List {
            if let drive {
                if drive.usesFixtureAnalysis { DemoBanner() }
                Section {
                    if let duration = drive.durationMilliseconds { Label("\(duration / 1_000) seconds recorded", systemImage: "video") }
                    if let sampleCount { Label(sampleCount == 0 ? "No GPS samples · approximate location unavailable" : "\(sampleCount) GPS samples saved", systemImage: sampleCount == 0 ? "location.slash" : "location") }
                    if drive.interrupted { Text("This recording was interrupted. Review the clip before retrying.").foregroundStyle(.orange) }
                    if videoURL != nil { Button("Review saved video") { showVideo = true } }
                }
                if drive.state == .complete {
                    Section("Road hazards") {
                        let hazards = drive.snapshot?.hazards ?? []
                        if hazards.isEmpty { ContentUnavailableView("0 hazards", systemImage: "checkmark.shield", description: Text("The server reported no meaningful road hazards in this drive.")) }
                        ForEach(hazards) { hazard in
                            NavigationLink(value: AppRoute.hazard(id, hazard.id)) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(hazard.category.capitalized).font(.headline)
                                    Text("\(hazard.videoOffsetMilliseconds / 1_000) seconds · \(hazard.locationLabel)")
                                        .font(.subheadline).foregroundStyle(.secondary)
                                }
                            }.accessibilityIdentifier("hazard_\(hazard.id.uuidString)")
                        }
                    }
                } else if drive.state == .failed {
                    Section("Processing failed") {
                        Text(drive.snapshot?.error ?? drive.lastError ?? "The drive could not be processed.")
                        Text("Your local files are retained.").foregroundStyle(.secondary)
                        if drive.serverID != nil || drive.isDemo {
                            Button("Retry") { Task { await state.retry(id) } }
                        }
                    }
                } else if drive.state == .saved {
                    Section("Saved on this iPhone") {
                        Text("Review the saved video first. Sending transmits the MP4 and any GPS samples to the configured analysis server; until then, they stay on this iPhone.")
                        Button("Send video and GPS for analysis") { Task { await state.approveUpload(id) } }
                            .accessibilityIdentifier("approveDriveUpload")
                    }
                } else {
                    Section {
                        ProgressView(statusText(drive))
                        Text("You can leave this screen. Pot Patrol will recover the saved drive status when reopened.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
                if let error = drive.lastError, drive.state != .failed {
                    Section("Needs attention") {
                        Text(error).foregroundStyle(.orange)
                        Button("Retry connection or upload") { Task { await state.retry(id) } }
                    }
                }
            } else { ProgressView("Loading drive") }
        }
        .navigationTitle(drive?.state == .complete ? "Results" : "Drive status")
        .sheet(isPresented: $showVideo) {
            if let videoURL { VideoPlayer(player: AVPlayer(url: videoURL)).ignoresSafeArea() }
        }
        .task {
            videoURL = await state.repository.videoURL(id)
            sampleCount = try? await state.repository.samples(id).count
            while !Task.isCancelled {
                guard phase == .active, let drive, [.queued, .processing].contains(drive.state) else {
                    do { try await Task.sleep(for: .milliseconds(500)) } catch { return }
                    continue
                }
                await state.refresh(id)
                do { try await Task.sleep(for: .seconds(2)) } catch { return }
            }
        }
    }
    private func statusText(_ drive: SavedDrive) -> String {
        switch drive.state {
        case .uploading: return drive.videoUploaded ? "Sending GPS samples" : "Uploading video"
        case .queued: return "Waiting for analysis"
        case .processing: return drive.snapshot?.stage == "analyzing" ? "Finding road hazards" : "Processing drive"
        default: return drive.state.rawValue.capitalized
        }
    }
}

struct DemoBanner: View {
    var body: some View {
        Label("Demo fixture · not real analysis", systemImage: "play.rectangle")
            .font(.footnote.bold()).foregroundStyle(.orange).accessibilityIdentifier("demoBanner")
    }
}

struct HazardReviewView: View {
    @EnvironmentObject private var state: AppState
    let driveID: UUID
    let hazardID: UUID
    @State private var evidenceData: Data?
    @State private var evidenceError: String?
    @State private var loading = false
    private var drive: SavedDrive? { state.drive(driveID) }
    private var hazard: APIHazard? { drive?.snapshot?.hazards.first { $0.id == hazardID } }
    var body: some View {
        List {
            if let hazard {
                if drive?.usesFixtureAnalysis == true { DemoBanner() }
                Section("Evidence") {
                    if let data = evidenceData, let image = UIImage(data: data) {
                        Image(uiImage: image).resizable().scaledToFit().accessibilityLabel("Hazard evidence image")
                    } else if loading { ProgressView("Loading private evidence") }
                    else {
                        Text(evidenceError ?? "Evidence unavailable").foregroundStyle(.secondary)
                        Button("Reload evidence") { Task { await loadEvidence() } }
                    }
                    Text("\(hazard.category.capitalized) · \(hazard.videoOffsetMilliseconds / 1_000) seconds into drive").font(.headline)
                    if let confidence = hazard.confidence, confidence.isFinite, (0...1).contains(confidence) {
                        Text("Confidence: \((confidence * 100).formatted(.number.precision(.fractionLength(0))))%")
                    }
                    if let severity = hazard.severity { Text("Severity: \(severity)") }
                    if let review = hazard.reviewState {
                        Label(review == "confirmed" ? "Detector confirmed" : review == "needs_review" ? "Needs review" : "Review status: \(review)",
                              systemImage: review == "confirmed" ? "checkmark.circle" : "eye")
                            .font(.footnote).foregroundStyle(review == "confirmed" ? .green : .orange)
                    }
                    if let basis = hazard.severityBasis { Text(basis).font(.footnote).foregroundStyle(.secondary) }
                    if let started = drive?.videoStartedAt {
                        Text("Recorded observation: \(started.addingTimeInterval(Double(hazard.videoOffsetMilliseconds) / 1_000).formatted(date: .abbreviated, time: .standard))")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
                Section(hazard.locationLabel) {
                    if let coordinate = hazard.location?.coordinate {
                        Map(initialPosition: .region(MKCoordinateRegion(
                            center: CLLocationCoordinate2D(latitude: coordinate.latitude, longitude: coordinate.longitude),
                            span: MKCoordinateSpan(latitudeDelta: 0.005, longitudeDelta: 0.005)
                        ))) {
                            Marker("Approximate hazard location", coordinate: CLLocationCoordinate2D(latitude: coordinate.latitude, longitude: coordinate.longitude))
                        }.frame(height: 200)
                        Text("The phone may reach the hazard after the camera sees it. This pin is approximate.").font(.footnote).foregroundStyle(.secondary)
                        if let accuracy = hazard.location?.horizontalAccuracyMeters {
                            Text("GPS accuracy: ±\(accuracy.formatted(.number.precision(.fractionLength(0)))) m")
                        }
                    } else {
                        Text("Location unavailable").accessibilityIdentifier("locationUnavailable")
                        Text("Review or enter a location in the report. Pot Patrol has not invented coordinates.")
                            .foregroundStyle(.secondary)
                    }
                }
                Section {
                    NavigationLink { ReportEditorView(driveID: driveID, hazard: hazard) } label: {
                        Label("Review report", systemImage: "doc.text")
                    }.accessibilityIdentifier("reviewReport")
                }
            } else { ContentUnavailableView("Hazard unavailable", systemImage: "exclamationmark.triangle") }
        }
        .navigationTitle("Hazard details")
        .task { await loadEvidence() }
    }
    private func loadEvidence() async {
        guard let hazard else { return }
        loading = true
        defer { loading = false }
        do { evidenceData = try await state.evidence(driveID, hazard: hazard).0; evidenceError = nil }
        catch { evidenceError = error.localizedDescription }
    }
}
