//
//  MeetingRecorderMenuBar.swift
//  MeetingRecorder
//
//  Menubar control menu that coexists with the window.
//  Start/stop, status, elapsed time, open window, open in Finder.
//  Guidance for missing permissions/errors is not built out here; it's delegated to the window.
//

import SwiftUI
import AppKit

struct MenuBarContent: View {
    @Environment(\.openWindow) private var openWindow
    let controller: RecordingController

    var body: some View {
        // AI agent send in-progress/done/failed is shown ahead of the latest transcription result.
        if !isAgentHandoffIdle {
            Text(agentHandoffStatusLine)
            if case .failed = controller.agentHandoff.state {
                Button("Retry sending to the AI agent") {
                    controller.agentHandoff.retryFailed()
                }
                .disabled(!controller.agentHandoff.canRetry)
            }
            Divider()
        }

        // Transcription in-progress/done/failed is shown prominently at the top (hidden when idle).
        if !isTranscriptionIdle {
            Text(transcriptionStatusLine)
            Divider()
        }

        controlItem
        Divider()
        Text(statusLine)  // becomes a disabled label item in .menu style
        Button("Open Main Window") {
            openWindow(id: MeetingRecorderApp.mainWindowID)
            NSApp.activate(ignoringOtherApps: true)
        }
        Button("Show in Finder") {
            controller.revealRecordingsLocation()
        }

        Divider()
        Button("Transcribe Now (Pending)") {
            controller.transcribeAllPendingTapped()
        }

        Divider()
        Button("Quit MeetingRecorder") {
            NSApplication.shared.terminate(nil)
        }
    }

    private var isTranscriptionIdle: Bool {
        if case .idle = controller.transcription.state { return true }
        return false
    }

    private var isAgentHandoffIdle: Bool {
        if case .idle = controller.agentHandoff.state { return true }
        return false
    }

    /// AI agent send status line.
    private var agentHandoffStatusLine: String {
        switch controller.agentHandoff.state {
        case .idle:
            return "AI agent send: idle"
        case .running(let label, let provider):
            return "⏳ Sending to \(provider.displayName)… (\(label))"
        case .succeeded(let label, let provider, let launchMethod):
            return "✓ \(AgentHandoffState.successText(provider: provider, launchMethod: launchMethod)) (\(label))"
        case .failed(let label, let message):
            return "⚠︎ Send failed (\(label)): \(message)"
        }
    }

    /// Transcription (post-processing) status line.
    private var transcriptionStatusLine: String {
        switch controller.transcription.state {
        case .idle:                 return "Transcription: idle"
        case .running(let label):   return "⏳ Transcribing… (\(label))"
        case .done(let label, let sourceAudioRetained):
            return sourceAudioRetained
                ? "✓ Transcription done, audio kept (\(label))"
                : "✓ Transcription done, audio deleted (\(label))"
        case .failed(let message):  return "⚠︎ \(message)"
        case .needsModel(let message): return "⚠︎ \(message)"
        }
    }

    @ViewBuilder
    private var controlItem: some View {
        switch controller.state {
        case .recording:
            Button("Stop Recording") { controller.stopTapped() }
        case .finalizing:
            Button("Saving…") {}.disabled(true)
        default:
            Button("Start Recording") { controller.startTapped() }
        }
    }

    /// Status text. Missing permissions and errors aren't detailed in the menubar; they route to the window.
    private var statusLine: String {
        switch controller.state {
        case .idle:            return "Idle"
        case .needsPermission: return "Permission needed (grant it in the window)"
        case .recording:       return "● Recording  \(elapsedTimeString(controller.elapsed))"
        case .finalizing:      return "Saving…"
        case .error:           return "Error (check the window)"
        }
    }
}
