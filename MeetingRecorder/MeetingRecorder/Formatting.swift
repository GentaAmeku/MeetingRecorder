//
//  Formatting.swift
//  MeetingRecorder
//
//  Formats elapsed time for display (shared by the window and the menubar).
//

import Foundation

/// Formats elapsed seconds as `HH:MM:SS`.
func elapsedTimeString(_ interval: TimeInterval) -> String {
    let total = Int(interval)
    return String(format: "%02d:%02d:%02d", total / 3600, (total % 3600) / 60, total % 60)
}
