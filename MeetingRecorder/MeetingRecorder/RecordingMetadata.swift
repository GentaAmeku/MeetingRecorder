//
//  RecordingMetadata.swift
//  MeetingRecorder
//
//  Model and generation for metadata.json (schemaVersion: 1).
//  Carries per-track audio parameters so downstream processing can judge the
//  source material without opening the files.
//

import Foundation

struct RecordingMetadata: Codable, Equatable {
    var schemaVersion: Int
    var appVersion: String
    /// Meeting title (default "meeting"). Added in schemaVersion 2.
    var title: String
    /// The counterpart's real name (empty = no name). Added in schemaVersion 3.
    var counterpartName: String
    var startedAt: String
    var endedAt: String
    var durationSec: Int
    var sampleRate: Int
    var files: Files
    var devices: Devices

    struct Files: Codable, Equatable {
        var mic: TrackFile
        var system: TrackFile
    }

    struct TrackFile: Codable, Equatable {
        var path: String
        var channels: Int
        var bitDepth: Int
        var format: String
    }

    struct Devices: Codable, Equatable {
        var micDeviceName: String
        var systemAudioCaptured: Bool
    }
}

enum MetadataBuilder {
    /// Builds metadata from a recording session.
    static func build(session: RecordingSession,
                      endedAt: Date,
                      micDeviceName: String,
                      systemAudioCaptured: Bool,
                      appVersion: String = Bundle.main.appVersionString) -> RecordingMetadata {
        let duration = max(0, Int(endedAt.timeIntervalSince(session.startedAt).rounded()))
        return RecordingMetadata(
            schemaVersion: 3,
            appVersion: appVersion,
            title: session.title,
            counterpartName: session.counterpartName,
            startedAt: iso8601(session.startedAt),
            endedAt: iso8601(endedAt),
            durationSec: duration,
            sampleRate: 48_000,
            files: .init(
                mic: .init(path: "mic.wav", channels: 1, bitDepth: 16, format: "wav_pcm_s16le"),
                system: .init(path: "system.wav", channels: 2, bitDepth: 16, format: "wav_pcm_s16le")
            ),
            devices: .init(micDeviceName: micDeviceName, systemAudioCaptured: systemAudioCaptured)
        )
    }

    /// Writes out as metadata.json.
    static func write(_ metadata: RecordingMetadata, to url: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .withoutEscapingSlashes]
        let data = try encoder.encode(metadata)
        try data.write(to: url, options: .atomic)
    }

    /// ISO 8601 with the local timezone offset (e.g. 2026-06-30T15:30:00+09:00).
    static func iso8601(_ date: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ssXXXXX"
        return f.string(from: date)
    }
}

extension Bundle {
    var appVersionString: String {
        (infoDictionary?["CFBundleShortVersionString"] as? String) ?? "0.0.0"
    }
}
