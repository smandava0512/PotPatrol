import PotPatrolCore
import SwiftUI
import UIKit

struct SharePayload: Identifiable {
    let id = UUID()
    let items: [Any]
}
struct ActivityShare: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) { }
}

struct ReportEditorView: View {
    @EnvironmentObject private var state: AppState
    @Environment(\.openURL) private var openURL
    let driveID: UUID
    let hazard: APIHazard
    @State private var report: EditableReport?
    @State private var category = ""
    @State private var description = ""
    @State private var latitude = ""
    @State private var longitude = ""
    @State private var receipt = ""
    @State private var error: String?
    @State private var saved = false
    @State private var share: SharePayload?
    @State private var includeFullVideo = false
    @State private var refreshing = false
    @State private var showRefreshConfirmation = false
    @FocusState private var focusedField: String?
    private var currentDraft: EditableReport? { try? editedReport() }
    var body: some View {
        Form {
            if let report {
                if state.drive(driveID)?.usesFixtureAnalysis == true { DemoBanner() }
                Section("Draft") {
                    TextField("Category", text: $category).focused($focusedField, equals: "category")
                    TextEditor(text: $description).frame(minHeight: 120).accessibilityIdentifier("reportDescription").focused($focusedField, equals: "description")
                    TextField("Latitude (optional)", text: $latitude).keyboardType(.numbersAndPunctuation).focused($focusedField, equals: "latitude")
                    TextField("Longitude (optional)", text: $longitude).keyboardType(.numbersAndPunctuation).focused($focusedField, equals: "longitude")
                    Text("Coordinates describe an approximate phone location. Confirm the hazard location before reporting.")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button("Save draft") { Task { await saveDraft() } }.accessibilityIdentifier("saveDraft")
                    if saved { Text("Edits saved on this iPhone").font(.footnote).foregroundStyle(.secondary) }
                    Button("Refresh draft") { focusedField = nil; showRefreshConfirmation = true }
                        .disabled(refreshing).accessibilityIdentifier("refreshDraft")
                    if refreshing { ProgressView("Refreshing draft") }
                }
                Section("Reporting destination") {
                    Text(destinationMessage(currentDraft ?? report)).accessibilityIdentifier("destinationStatus")
                    if let reason = report.package.destination.reason {
                        Text(reason).font(.footnote).accessibilityIdentifier("destinationReason")
                    }
                    if let url = report.package.destination.url { Text(url).font(.footnote).textSelection(.enabled) }
                    ForEach(report.package.destination.candidates ?? []) { candidate in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(candidate.name).font(.headline)
                            if let url = candidate.destinationURL { Text(url).font(.footnote).textSelection(.enabled) }
                            ForEach(candidate.sources ?? []) { source in
                                if let url = source.httpsURL {
                                    Link(source.what ?? "Agency source", destination: url).font(.footnote)
                                    Text(source.url).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                }
                            }
                            Button(currentDraft?.selectedCandidateID == candidate.id ? "Selected by you" : "Choose this agency") {
                                Task { await selectCandidate(candidate.id) }
                            }
                            .disabled(report.package.destination.status != "needs_review" || candidate.httpsURL == nil || currentDraft?.coordinate == nil || currentDraft?.destinationNeedsReview != false)
                            .accessibilityIdentifier("candidate_\(candidate.id)")
                        }.padding(.vertical, 4)
                    }
                    ForEach(report.package.destination.sources ?? []) { source in
                        if let url = source.httpsURL { Link(source.what ?? source.url, destination: url).font(.footnote) }
                    }
                    if let candidate = currentDraft?.selectedCandidate {
                        Text("You selected \(candidate.name). Confirm road ownership on the agency's site; this choice does not verify it.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    Button(currentDraft?.selectedCandidate == nil ? "Open official portal" : "Open selected agency page") { Task { await openPortal() } }
                        .disabled(currentDraft?.portalURL == nil).accessibilityIdentifier("openPortal")
                    Text("Opening the portal is not a submission. Attach the evidence and complete its form manually.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section("Copy or share") {
                    Button("Copy report text") {
                        do { UIPasteboard.general.string = sharedText(try editedReport()) }
                        catch { self.error = error.localizedDescription }
                    }
                    Toggle("Include full drive video", isOn: $includeFullVideo).accessibilityIdentifier("includeFullVideo")
                    Text("The evidence photo is shared by default. Full video may include number plates or people.")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button(includeFullVideo ? "Share text, evidence, and video" : "Share text and evidence") { Task { await prepareShare() } }
                        .accessibilityIdentifier("shareReport")
                }
                Section("Submission") {
                    Text(report.handoff.label).accessibilityIdentifier("handoffState")
                    if report.handoff == .portalOpened {
                        Text("After submitting on the portal, enter the actual confirmation or receipt.").font(.footnote)
                        TextField("Confirmation or receipt", text: $receipt).focused($focusedField, equals: "receipt")
                        Button("Save submission receipt") { Task { await confirmReceipt() } }
                            .disabled(receipt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                    if let receipt = report.receipt { Text("Receipt supplied by you: \(receipt)").textSelection(.enabled) }
                    if let receipts = report.previousReceipts {
                        ForEach(Array(receipts.enumerated()), id: \.offset) { item in
                            Text("Receipt from an earlier draft: \(item.element)").font(.footnote).textSelection(.enabled)
                        }
                    }
                }
            } else if error == nil { ProgressView("Preparing editable draft") }
            if let error { Text(error).foregroundStyle(.red) }
        }
        .navigationTitle("Review report")
        .disabled(refreshing)
        .scrollDismissesKeyboard(.interactively)
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { focusedField = nil }.accessibilityIdentifier("dismissReportKeyboard")
            }
        }
        .sheet(item: $share) { payload in ActivityShare(items: payload.items) }
        .confirmationDialog("Refresh draft from the server?", isPresented: $showRefreshConfirmation, titleVisibility: .visible) {
            Button("Replace local draft", role: .destructive) { Task { await loadDraft(refresh: true) } }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("This replaces your local edits with the latest server draft. Earlier submission receipts remain in history.")
        }
        .task { await loadDraft() }
    }
    private func loadDraft(refresh: Bool = false) async {
        refreshing = true
        defer { refreshing = false }
        do {
            let loaded = try await state.report(driveID, hazardID: hazard.id, refresh: refresh)
            report = loaded
            let serverCategory = loaded.package.fields["category"]?.text ?? ""
            category = serverCategory.isEmpty ? hazard.category : serverCategory
            description = loaded.package.fields["description"]?.text ?? ""
            latitude = loaded.package.fields["latitude"]?.text ?? ""
            longitude = loaded.package.fields["longitude"]?.text ?? ""
            receipt = ""
            saved = false
            error = nil
        } catch { self.error = error.localizedDescription }
    }
    private func selectCandidate(_ id: String) async {
        do {
            var edited = try editedReport()
            guard edited.selectCandidate(id) else {
                throw PotPatrolAPIError.configuration("Review the location and choose an available agency page.")
            }
            try await state.saveReport(edited, id: driveID, hazardID: hazard.id)
            report = edited
            error = nil
        } catch { self.error = error.localizedDescription }
    }
    private func editedReport() throws -> EditableReport {
        guard var report else { throw PotPatrolAPIError.invalidResponse }
        var fields = report.package.fields
        fields["category"] = .string(category.trimmingCharacters(in: .whitespacesAndNewlines))
        fields["description"] = .string(description)
        let lat = latitude.trimmingCharacters(in: .whitespacesAndNewlines)
        let lon = longitude.trimmingCharacters(in: .whitespacesAndNewlines)
        if lat.isEmpty && lon.isEmpty {
            fields["latitude"] = .null
            fields["longitude"] = .null
        } else {
            guard let coordinate = GeoCoordinate(latitude: Double(lat), longitude: Double(lon)) else {
                throw PotPatrolAPIError.configuration("Enter both valid coordinates, or leave both fields empty.")
            }
            fields["latitude"] = .number(coordinate.latitude)
            fields["longitude"] = .number(coordinate.longitude)
        }
        report.edit(fields: fields)
        return report
    }
    private func saveDraft() async {
        do {
            let edited = try editedReport()
            try await state.saveReport(edited, id: driveID, hazardID: hazard.id)
            report = edited
            saved = true
            error = nil
        } catch { self.error = error.localizedDescription }
    }
    private func openPortal() async {
        do {
            let edited = try editedReport()
            guard let url = edited.portalURL else {
                throw PotPatrolAPIError.configuration("The reporting destination needs verification before opening a portal.")
            }
            try await state.saveReport(edited, id: driveID, hazardID: hazard.id)
            report = edited
            openURL(url) { accepted in
                guard accepted else { error = "The portal could not be opened."; return }
                Task {
                    var opened = edited
                    opened.recordPortalOpened()
                    do {
                        try await state.saveReport(opened, id: driveID, hazardID: hazard.id)
                        report = opened
                    } catch { self.error = error.localizedDescription }
                }
            }
        } catch { self.error = error.localizedDescription }
    }
    private func confirmReceipt() async {
        do {
            var edited = try editedReport()
            guard edited.confirmSubmission(receipt: receipt) else {
                throw PotPatrolAPIError.configuration("A portal must have been opened and an actual receipt supplied.")
            }
            try await state.saveReport(edited, id: driveID, hazardID: hazard.id)
            report = edited
        } catch { self.error = error.localizedDescription }
    }
    private func prepareShare() async {
        do {
            let edited = try editedReport()
            try await state.saveReport(edited, id: driveID, hazardID: hazard.id)
            report = edited
            var items: [Any] = [sharedText(edited)]
            if let evidence = try? await state.evidence(driveID, hazard: hazard) { items.append(evidence.1) }
            if includeFullVideo {
                let video = await state.repository.videoURL(driveID)
                if FileManager.default.fileExists(atPath: video.path) { items.append(video) }
            }
            share = SharePayload(items: items)
        } catch { self.error = error.localizedDescription }
    }
    private func sharedText(_ report: EditableReport) -> String {
        let warning = state.drive(driveID)?.usesFixtureAnalysis == true ? "Demo fixture · not real analysis\n\n" : ""
        return warning + report.shareText
    }
    private func destinationMessage(_ report: EditableReport) -> String {
        if report.destinationNeedsReview { return "Location edited. Restore the original coordinates, or refresh the draft after the server updates its location." }
        switch report.package.destination.status {
        case "verified": return report.coordinate == nil ? "Location needs review before reporting." : "Verified destination supplied by the server"
        case "unsupported": return "Reporting is not supported for this location yet. You can save or share this draft."
        case "needs_review", "unverified", "unknown": return "The road owner and reporting destination need verification."
        default: return "The reporting destination needs review."
        }
    }
}
