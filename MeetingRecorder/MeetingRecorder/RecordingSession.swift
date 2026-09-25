//
//  RecordingSession.swift
//  MeetingRecorder
//
//  1 recording session = 1 output directory.
//  The save location is fixed at ~/Documents/MeetingRecorder/recordings/.
//

import Foundation

struct RecordingSession {
    let directory: URL
    let startedAt: Date
    /// Meeting title (for metadata.title). "meeting" when the input is empty.
    let title: String
    /// The counterpart's real name (for metadata.counterpartName). Empty = no name (formerly "the other side").
    let counterpartName: String

    var micFileURL: URL { directory.appendingPathComponent("mic.wav") }
    var systemFileURL: URL { directory.appendingPathComponent("system.wav") }
    var metadataURL: URL { directory.appendingPathComponent("metadata.json") }

    /// Recording base folder: ~/Documents/MeetingRecorder/recordings/
    static var recordingsRoot: URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return docs.appendingPathComponent("MeetingRecorder/recordings", isDirectory: true)
    }

    /// Creates and returns a new session directory.
    /// The folder name is `YYYY-MM-DD_HHmm_<title>` (title defaults to "meeting").
    /// If one already exists within the same minute, seconds are appended to avoid a collision.
    /// - Parameters:
    ///   - name: Meeting title (optional). Trimmed; falls back to "meeting" when empty.
    ///   - root: Base folder to create in (swappable for tests).
    static func create(at date: Date = Date(),
                       name: String = "",
                       counterpart: String = "",
                       in root: URL = recordingsRoot) throws -> RecordingSession {
        let fm = FileManager.default
        try fm.createDirectory(at: root, withIntermediateDirectories: true)

        let title = normalizedTitle(name)
        let component = folderSafe(title)
        var dir = root.appendingPathComponent("\(folderName(for: date))_\(component)", isDirectory: true)
        if fm.fileExists(atPath: dir.path) {
            dir = root.appendingPathComponent("\(folderName(for: date, includeSeconds: true))_\(component)",
                                              isDirectory: true)
        }
        try fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return RecordingSession(directory: dir, startedAt: date,
                                title: title, counterpartName: normalizedCounterpart(counterpart))
    }

    static func folderName(for date: Date, includeSeconds: Bool = false) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = includeSeconds ? "yyyy-MM-dd_HHmm-ss" : "yyyy-MM-dd_HHmm"
        return f.string(from: date)
    }

    /// Normalizes the meeting title: trim, fall back to "meeting" when empty, cap length at 50.
    static func normalizedTitle(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return "meeting" }
        return String(trimmed.prefix(50))
    }

    /// Normalizes the counterpart name: trim, strip newlines, cap length at 50. Empty stays "" (no name).
    static func normalizedCounterpart(_ raw: String) -> String {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        for ch in ["\n", "\r", "\t"] { s = s.replacingOccurrences(of: ch, with: " ") }
        return String(s.prefix(50))
    }

    /// Sanitizes characters that aren't safe in a folder name (non-ASCII scripts and spaces are
    /// fine; `/`, `:`, newlines, etc. become `-`).
    static func folderSafe(_ title: String) -> String {
        var s = title
        for ch in ["/", ":", "\n", "\r", "\t"] {
            s = s.replacingOccurrences(of: ch, with: "-")
        }
        return s
    }
}
