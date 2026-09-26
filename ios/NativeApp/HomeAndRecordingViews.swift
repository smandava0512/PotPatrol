import AVFoundation
import AVKit
import PotPatrolCore
import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var state: AppState
    @State private var showSettings = false
    @State private var showScenarios = false
    var body: some View {
        NavigationStack(path: $state.path) {
            List {
                Section {
                    VStack(alignment: .leading, spacing: 12) {
                        Image(systemName: "road.lanes").font(.system(size: 40)).foregroundStyle(.tint)
                        Text("Watch the road.\nReview what matters.").font(.largeTitle.bold())
                        Text("Record a drive, review road hazards, and prepare a report with evidence.")
                            .foregroundStyle(.secondary)
                        Text("Set up and start while parked. Keep your phone mounted during the drive.")
                            .font(.footnote).foregroundStyle(.secondary)
                        Button { Task { await state.startRecording() } } label: {
                            Label("Start drive", systemImage: "record.circle").frame(maxWidth: .infinity)
                        }.buttonStyle(.borderedProminent).controlSize(.large).accessibilityIdentifier("recordDrive")
                            .disabled(state.preparingRecording)
                        if state.preparingRecording { ProgressView("Preparing recording") }
                        Button("Prepare camera and location") { Task { await state.preparePermissions() } }
                            .font(.footnote)
                    }.padding(.vertical, 8)
                }
                Section("Try the demo") {
                    Button { Task { await state.startRecording(demo: .pothole) } } label: {
                        Label("Sample drive", systemImage: "play.rectangle")
                    }.accessibilityIdentifier("demoDrive")
                    Button("More sample scenarios") { showScenarios.toggle() }.accessibilityIdentifier("demoScenarios")
                    if showScenarios {
                        Button("Without GPS") { Task { await state.startRecording(demo: .noGPS) } }.accessibilityIdentifier("demoNoGPS")
                        Button("No hazards") { Task { await state.startRecording(demo: .noHazards) } }.accessibilityIdentifier("demoNoHazards")
                        Button("Processing failure") { Task { await state.startRecording(demo: .processingFailure) } }.accessibilityIdentifier("demoFailure")
                        Button("Unsupported destination") { Task { await state.startRecording(demo: .unsupportedDestination) } }.accessibilityIdentifier("demoUnsupported")
                    }
                    Text("Demo fixtures are a backup walkthrough, not real analysis.").font(.footnote).foregroundStyle(.secondary)
                }
                Section("Saved drives") {
                    if state.drives.isEmpty {
                        Text("Your recordings will stay on this iPhone until their uploads are confirmed.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(state.drives) { drive in
                        NavigationLink(value: AppRoute.drive(drive.id)) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(drive.createdAt.formatted(date: .abbreviated, time: .shortened)).font(.headline)
                                Text(drive.usesFixtureAnalysis ? "Demo fixture · \(drive.state.rawValue.capitalized)" : drive.state.rawValue.capitalized)
                                    .font(.subheadline).foregroundStyle(.secondary)
                            }
                        }.accessibilityIdentifier("drive_\(drive.id.uuidString)")
                    }
                }
            }
            .navigationTitle("Pot Patrol")
            .toolbar {
                Button { showSettings = true } label: { Image(systemName: "gearshape") }
                    .accessibilityLabel("Connection settings").accessibilityIdentifier("connectionSettings")
            }
            .navigationDestination(for: AppRoute.self) { route in
                switch route {
                case .drive(let id): DriveStatusView(id: id)
                case .hazard(let drive, let hazard): HazardReviewView(driveID: drive, hazardID: hazard)
                }
            }
            .sheet(isPresented: $showSettings) { SettingsView() }
            .fullScreenCover(isPresented: Binding(get: { state.activeRecordingID != nil }, set: { _ in })) {
                RecordingView().interactiveDismissDisabled()
            }
            .alert("Pot Patrol", isPresented: Binding(get: { state.notice != nil }, set: { if !$0 { state.notice = nil } })) {
                Button("OK") { state.notice = nil }
            } message: { Text(state.notice ?? "") }
        }
    }
}

struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession
    final class Preview: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
    }
    func makeUIView(context: Context) -> Preview {
        let view = Preview()
        view.previewLayer.session = session
        view.previewLayer.videoGravity = .resizeAspectFill
        return view
    }
    func updateUIView(_ uiView: Preview, context: Context) {
        if let connection = uiView.previewLayer.connection, connection.isVideoRotationAngleSupported(90) {
            connection.videoRotationAngle = 90
        }
    }
}

struct RecordingView: View {
    @EnvironmentObject private var state: AppState
    @State private var player = AVPlayer(url: DemoFixtures.videoURL)
    @State private var sampleSeconds = 0
    private var isDemo: Bool { state.activeRecordingID.flatMap(state.drive)?.isDemo == true }
    var body: some View {
        VStack(spacing: 0) {
            ZStack(alignment: .topLeading) {
                if isDemo { VideoPlayer(player: player) }
                else { CameraPreview(session: state.recorder.session) }
                VStack(alignment: .leading, spacing: 8) {
                    Label(isDemo ? "Demo fixture" : "Recording", systemImage: "record.circle.fill")
                        .foregroundStyle(isDemo ? .orange : .red)
                    Text(String(format: "%02d:%02d", (isDemo ? sampleSeconds : state.elapsed) / 60, (isDemo ? sampleSeconds : state.elapsed) % 60))
                        .font(.largeTitle.monospacedDigit().bold()).foregroundStyle(.white)
                    if !isDemo { Text(state.hasGPS ? "GPS available" : "GPS unavailable · video will still be saved").font(.footnote).foregroundStyle(.white) }
                }.padding().background(.black.opacity(0.65)).clipShape(RoundedRectangle(cornerRadius: 16)).padding()
            }
            .background(.black)
            VStack(spacing: 16) {
                Text(isDemo ? "Sample playback, not live recording." : "Keep the phone mounted. Stop when parked.")
                    .font(.footnote).foregroundStyle(.secondary)
                if state.savingRecording { ProgressView("Saving drive") }
                Button { Task { await state.stopRecording() } } label: {
                    Label("Stop and save", systemImage: "stop.circle.fill").frame(maxWidth: .infinity)
                }.buttonStyle(.borderedProminent).tint(.red).controlSize(.large)
                    .disabled(state.savingRecording).accessibilityIdentifier("stopRecording")
            }.padding(24)
        }
        .task(id: isDemo) {
            guard isDemo else { return }
            player.play()
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(1)) } catch { return }
                sampleSeconds += 1
            }
        }
        .onDisappear { player.pause() }
    }
}

struct SettingsView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.dismiss) private var dismiss
    @State private var baseURL = ""
    @State private var token = ""
    @State private var developmentHTTP = false
    @State private var error: String?
    @State private var saving = false
    var body: some View {
        NavigationStack {
            Form {
                Section("Analysis server") {
                    TextField("https://your-server.example", text: $baseURL)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    SecureField("Device token", text: $token).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Text("Ask Developer 2 for the server URL and device token. The token is stored in Keychain.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                #if DEBUG
                Section("Local development") {
                    Toggle("Allow HTTP for the local server", isOn: $developmentHTTP)
                    Text("On a real phone, use the server computer's LAN address, not 127.0.0.1. HTTP is available only in development builds.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                #endif
                if let error { Text(error).foregroundStyle(.red) }
                Button(saving ? "Saving…" : "Save connection") {
                    saving = true
                    Task {
                        do {
                            try await state.saveConnection(baseURL: baseURL, token: token, developmentHTTP: developmentHTTP)
                            dismiss()
                        } catch { self.error = error.localizedDescription; saving = false }
                    }
                }.disabled(saving)
                Section("Permissions") {
                    Button("Open iPhone Settings") {
                        if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                    }
                }
            }
            .navigationTitle("Connection")
            .toolbar { Button("Done") { dismiss() } }
            .onAppear { baseURL = state.settings.baseURL; developmentHTTP = state.settings.developmentHTTP; token = DeviceTokenStore.read() }
        }
    }
}
