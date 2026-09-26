import SwiftUI
import UIKit

final class PotPatrolAppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, handleEventsForBackgroundURLSession identifier: String, completionHandler: @escaping () -> Void) {
        guard identifier == BackgroundVideoUploader.identifier else { completionHandler(); return }
        AppState.shared.videoUploader.attachBackgroundEvents(completion: completionHandler)
    }
}

@main
struct PotPatrolApp: App {
    @UIApplicationDelegateAdaptor(PotPatrolAppDelegate.self) private var delegate
    @StateObject private var state = AppState.shared
    @Environment(\.scenePhase) private var scenePhase
    var body: some Scene {
        WindowGroup {
            HomeView().environmentObject(state).tint(Color(red: 0.16, green: 0.48, blue: 0.35))
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active { Task { await state.reload(); await state.resumeSavedDrives() } }
                    else if phase == .background { state.enteredBackground() }
                }
                .onReceive(NotificationCenter.default.publisher(for: .videoTransferChanged)) { _ in
                    Task { await state.reload(); await state.resumeSavedDrives() }
                }
        }
    }
}
