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
    @FocusState private var focusedField: String?
    var body: some View {
        Form {
            if let report {
                if state.drive(driveID)?.isDemo == true { DemoBanner() }
                Section("Draft") {
                    TextField("Category", text: $category).focused($focusedField, equals: "category")
                    TextEditor(text: $description).frame(minHeight: 120).accessibilityIdentifier("reportDescription").focused($focusedField, equals: "description")
                    TextField("Latitude (optional)", text: $latitude).keyboardType(.numbersAndPunctuation).focused($focusedField, equals: "latitude")
                    TextField("Longitude (optional)", text: $longitude).keyboardType(.numbersAndPunctuation).focused($focusedField, equals: "longitude")
                    Text("Coordinates describe an approximate phone location. Confirm the hazard location before reporting.")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button("Save draft") { Task { await saveDraft() } }.accessibilityIdentifier("saveDraft")
                    if saved { Text("Edits saved on this iPhone").font(.footnote).foregroundStyle(.secondary) }
                }
                Section("Reporting destination") {
                    Text(destinationMessage(report)).accessibilityIdentifier("destinationStatus")
                    if let url = report.package.destination.url { Text(url).font(.footnote).textSelection(.enabled) }
                    Button("Open official portal") { Task { await openPortal() } }
                        .disabled(report.portalURL == nil).accessibilityIdentifier("openPortal")
                    Text("Opening the portal is not a submission. Attach the evidence and complete its form manually.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section("Copy or share") {
                    Button("Copy report text") {
                        do { UIPasteboard.general.string = try editedReport().shareText }
                        catch { self.error = error.localizedDescription }
                    }
                    Button("Share text, evidence, and saved video") { Task { await prepareShare() } }
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
                }
            } else if error == nil { ProgressView("Preparing editable draft") }
            if let error { Text(error).foregroundStyle(.red) }
        }
        .navigationTitle("Review report")
        .scrollDismissesKeyboard(.interactively)
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { focusedField = nil }.accessibilityIdentifier("dismissReportKeyboard")
            }
        }
        .sheet(item: $share) { payload in ActivityShare(items: payload.items) }
        .task {
            do {
                let report = try await state.report(driveID, hazardID: hazard.id)
                self.report = report
                category = report.package.fields["category"]?.text ?? hazard.category
                description = report.package.fields["description"]?.text ?? ""
                latitude = report.package.fields["latitude"]?.text ?? ""
                longitude = report.package.fields["longitude"]?.text ?? ""
            } catch { self.error = error.localizedDescription }
        }
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
            var items: [Any] = [edited.shareText]
            if let evidence = try? await state.evidence(driveID, hazard: hazard) { items.append(evidence.1) }
            let video = await state.repository.videoURL(driveID)
            if FileManager.default.fileExists(atPath: video.path) { items.append(video) }
            share = SharePayload(items: items)
        } catch { self.error = error.localizedDescription }
    }
    private func destinationMessage(_ report: EditableReport) -> String {
        if report.destinationNeedsReview { return "Location edited. Verify the destination for the revised location." }
        switch report.package.destination.status {
        case "verified": return report.coordinate == nil ? "Location needs review before reporting." : "Verified destination supplied by the server"
        case "unsupported": return "Reporting is not supported for this location yet. You can save or share this draft."
        case "needs_review", "unverified", "unknown": return "The road owner and reporting destination need verification."
        default: return "The reporting destination needs review."
        }
    }
}
