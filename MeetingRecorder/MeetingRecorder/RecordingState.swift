//
//  RecordingState.swift
//  MeetingRecorder
//
//  Recording state machine (held by RecordingController)
//

import Foundation

/// Recording state. Possible transitions:
/// idle -> (permission check) -> needsPermission / recording -> finalizing -> idle, or error on failure.
enum RecordingState: Equatable {
    case idle
    case needsPermission(missing: Set<PermissionKind>)
    case recording
    case finalizing
    case error(String)
}

/// The kinds of permission recording requires.
enum PermissionKind: String, CaseIterable, Sendable {
    case microphone
    case screenRecording

    var displayName: String {
        switch self {
        case .microphone: return "Microphone"
        case .screenRecording: return "Screen & System Audio Recording"
        }
    }

    /// Guidance shown to the user when a permission is missing.
    var settingsHint: String {
        switch self {
        case .microphone:
            return "Please grant it in System Settings > Privacy & Security > Microphone."
        case .screenRecording:
            return "Please grant it in System Settings > Privacy & Security > Screen & System Audio Recording. An app restart may be required after granting it."
        }
    }

    /// URL that opens the matching System Settings pane directly.
    var settingsURLString: String {
        switch self {
        case .microphone:
            return "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
        case .screenRecording:
            return "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        }
    }
}
