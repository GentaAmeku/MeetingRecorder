//
//  PostprocessConfigStore.swift
//  MeetingRecorder
//
//  Reads and writes the transcript.language field of postprocess-config.json.
//  Every other key — selfName, otherName, schemaVersion, and any key this
//  app doesn't know about — is round-tripped untouched. The app never owns
//  this file's full schema; the postprocess CLI does.
//

import Foundation

nonisolated enum PostprocessConfigStore {
    static let defaultURL = FileManager.default
        .urls(for: .documentDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("MeetingRecorder/postprocess-config.json")

    /// Reads transcript.language from the config file at `url`. Returns nil
    /// when the file is missing or unreadable, or the value isn't a language
    /// this app's Settings screen offers.
    static func readLanguage(from url: URL = defaultURL) -> TranscriptionLanguage? {
        guard let root = readRoot(from: url),
              let transcript = root["transcript"] as? [String: Any],
              let raw = transcript["language"] as? String
        else { return nil }
        return TranscriptionLanguage(rawValue: raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }

    /// Writes `language` into transcript.language at `url`, creating the
    /// file and its parent directory if needed. Preserves every other key,
    /// including ones this app doesn't understand (e.g. otherName).
    /// Returns false without touching the file when it exists but isn't a JSON
    /// object, or its "transcript" value isn't an object — overwriting it would
    /// silently drop hand-edited keys such as selfName and otherName.
    @discardableResult
    static func writeLanguage(_ language: TranscriptionLanguage, to url: URL = defaultURL) -> Bool {
        let fileExists = FileManager.default.fileExists(atPath: url.path)
        guard var root = readRoot(from: url) ?? (fileExists ? nil : [:]) else { return false }
        if let existing = root["transcript"], !(existing is [String: Any]) { return false }
        var transcript = root["transcript"] as? [String: Any] ?? [:]
        transcript["language"] = language.rawValue
        root["transcript"] = transcript
        if root["schemaVersion"] == nil {
            root["schemaVersion"] = 1
        }
        guard JSONSerialization.isValidJSONObject(root),
              let data = try? JSONSerialization.data(
                  withJSONObject: root, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
        else { return false }
        try? FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        return (try? data.write(to: url, options: .atomic)) != nil
    }

    private static func readRoot(from url: URL) -> [String: Any]? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    }
}
