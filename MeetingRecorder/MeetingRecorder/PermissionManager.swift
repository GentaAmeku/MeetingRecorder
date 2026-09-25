//
//  PermissionManager.swift
//  MeetingRecorder
//
//  Checks and requests permissions. Handles both the microphone and screen recording.
//

import AVFoundation
import CoreGraphics

@MainActor
final class PermissionManager {
    func microphoneStatus() -> AVAuthorizationStatus {
        AVCaptureDevice.authorizationStatus(for: .audio)
    }

    /// Requests microphone access and returns whether it ended up granted.
    func requestMicrophoneAccess() async -> Bool {
        switch microphoneStatus() {
        case .authorized:
            return true
        case .notDetermined:
            return await AVCaptureDevice.requestAccess(for: .audio)
        default: // denied, restricted
            return false
        }
    }

    /// Whether screen recording access is already granted (checks without prompting).
    func hasScreenRecordingAccess() -> Bool {
        CGPreflightScreenCaptureAccess()
    }

    /// Requests screen recording access, showing the system prompt if not yet granted.
    /// Returns false on first grant, since macOS typically requires an app restart for it to take effect.
    func requestScreenRecordingAccess() -> Bool {
        if CGPreflightScreenCaptureAccess() { return true }
        return CGRequestScreenCaptureAccess()
    }
}
