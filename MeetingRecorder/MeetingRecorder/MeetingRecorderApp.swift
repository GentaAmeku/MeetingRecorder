//
//  MeetingRecorderApp.swift
//  MeetingRecorder
//

import SwiftUI
import AppKit

@main
struct MeetingRecorderApp: App {
    /// The App owns a single instance of the recording controller, shared by the window and the menubar.
    /// This keeps recording running when the window is closed (including recording started from the menubar).
    @State private var controller = RecordingController()

    /// The main window's identifier (used to reopen it from the menubar).
    static let mainWindowID = "main"

    /// MenuBarExtra uses NSImage's native size, so render the app icon at the display size before passing it in.
    private static let menuBarIcon = NSImage(
        size: NSSize(width: 18, height: 18),
        flipped: false
    ) { rect in
        NSApplication.shared.applicationIconImage.draw(in: rect)
        return true
    }

    var body: some Scene {
        // A single window (Window, not WindowGroup: unique, and recoverable via openWindow after closing).
        Window("Meeting Recorder", id: Self.mainWindowID) {
            MeetingRecorderRootView(controller: controller)
        }
        .handlesExternalEvents(matching: ["prepare"])
        .windowResizability(.contentSize)

        // Menubar control that coexists with the window. Injects the same controller.
        MenuBarExtra {
            MenuBarContent(controller: controller)
        } label: {
            Image(nsImage: Self.menuBarIcon)
                .renderingMode(.original)
                .accessibilityLabel("Meeting Recorder")
        }
        .menuBarExtraStyle(.menu)
    }
}

/// Receives meetingrecorder://prepare from OnCue and brings the window to the front.
private struct MeetingRecorderRootView: View {
    @Environment(\.openWindow) private var openWindow
    let controller: RecordingController

    var body: some View {
        RecordingView(controller: controller)
            .onOpenURL { url in
                controller.receiveMeetingLaunchURL(url)
                openWindow(id: MeetingRecorderApp.mainWindowID)
                NSApp.activate(ignoringOtherApps: true)
            }
    }
}
