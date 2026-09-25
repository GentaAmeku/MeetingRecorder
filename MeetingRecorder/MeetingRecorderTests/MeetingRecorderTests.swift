//
//  MeetingRecorderTests.swift
//  MeetingRecorderTests
//
//  Pure-logic unit tests (session folder name / metadata JSON).
//

import Testing
import Foundation
@testable import MeetingRecorder

struct AudioRetentionPreferenceTests {
    @Test func defaultsToDeletingSourceAudioAndPersistsOptIn() throws {
        let suiteName = "AudioRetentionPreferenceTests-\(UUID().uuidString)"
        let defaults = try #require(UserDefaults(suiteName: suiteName))
        defer {
            defaults.removePersistentDomain(forName: suiteName)
            let plist = FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Preferences/\(suiteName).plist")
            try? FileManager.default.removeItem(at: plist)
        }

        #expect(!AudioRetentionPreference.keepsSourceAudio(in: defaults))

        AudioRetentionPreference.setKeepsSourceAudio(true, in: defaults)

        #expect(AudioRetentionPreference.keepsSourceAudio(in: defaults))
    }

    @Test func transcriptionArgumentsOnlyOptInToKeepingAudio() {
        #expect(
            TranscriptionArguments.session("/tmp/session", keepSourceAudio: false)
                == ["/tmp/session"]
        )
        #expect(
            TranscriptionArguments.session("/tmp/session", keepSourceAudio: true)
                == ["/tmp/session", "--keep-source-audio"]
        )
        #expect(
            TranscriptionArguments.allPending(keepSourceAudio: true)
                == ["--all-pending", "--keep-source-audio"]
        )
    }
}

@MainActor
struct RecordingSessionTests {

    /// 2026-06-30 15:30:00 → "2026-06-30_1530_meeting"
    @Test func folderNameFollowsSpecFormat() {
        let date = Self.makeDate(y: 2026, mo: 6, d: 30, h: 15, mi: 30, s: 0)
        #expect(RecordingSession.folderName(for: date) == "2026-06-30_1530")
        #expect(RecordingSession.folderName(for: date, includeSeconds: true) == "2026-06-30_1530-00")
    }

    /// Creating twice within the same minute never collides on the folder name; appending seconds makes separate directories.
    @Test func collisionInSameMinuteGetsSecondsSuffix() throws {
        let root = Self.tempRoot()
        defer { try? FileManager.default.removeItem(at: root) }

        let date = Self.makeDate(y: 2026, mo: 6, d: 30, h: 15, mi: 30, s: 45)
        let first = try RecordingSession.create(at: date, in: root)
        let second = try RecordingSession.create(at: date, in: root)

        #expect(first.directory != second.directory)
        #expect(first.directory.lastPathComponent == "2026-06-30_1530_meeting")
        #expect(second.directory.lastPathComponent == "2026-06-30_1530-45_meeting")
        #expect(FileManager.default.fileExists(atPath: first.directory.path))
        #expect(FileManager.default.fileExists(atPath: second.directory.path))
    }

    @Test func folderNameUsesMeetingNameWhenProvided() throws {
        let root = Self.tempRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let date = Self.makeDate(y: 2026, mo: 7, d: 2, h: 9, mi: 30, s: 0)
        let s = try RecordingSession.create(at: date, name: "週次定例", in: root)
        #expect(s.directory.lastPathComponent == "2026-07-02_0930_週次定例")
        #expect(s.title == "週次定例")
    }

    @Test func emptyNameFallsBackToMeeting() throws {
        let root = Self.tempRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let date = Self.makeDate(y: 2026, mo: 7, d: 2, h: 9, mi: 30, s: 0)
        let s = try RecordingSession.create(at: date, name: "   ", in: root)
        #expect(s.directory.lastPathComponent == "2026-07-02_0930_meeting")
        #expect(s.title == "meeting")
    }

    @Test func titleNormalizationAndFolderSafety() {
        #expect(RecordingSession.normalizedTitle("   ") == "meeting")
        #expect(RecordingSession.normalizedTitle("  打合せ  ") == "打合せ")
        #expect(RecordingSession.folderSafe("a/b:c") == "a-b-c")
    }

    @Test func counterpartNormalizationAndCarryThrough() throws {
        // Trims, and turns newlines into spaces. Empty stays "" (unlike the meeting name, never falls back to "meeting").
        #expect(RecordingSession.normalizedCounterpart("  田中  ") == "田中")
        #expect(RecordingSession.normalizedCounterpart("田\n中") == "田 中")
        #expect(RecordingSession.normalizedCounterpart("   ") == "")

        // create() carries the counterpart through, but never puts it in the folder name.
        let root = Self.tempRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let date = Self.makeDate(y: 2026, mo: 7, d: 2, h: 9, mi: 30, s: 0)
        let s = try RecordingSession.create(at: date, name: "定例", counterpart: "田中", in: root)
        #expect(s.counterpartName == "田中")
        #expect(s.directory.lastPathComponent == "2026-07-02_0930_定例")  // the counterpart name isn't included in the folder name
    }

    @Test func fileURLsSitInsideSessionDirectory() throws {
        let root = Self.tempRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let session = try RecordingSession.create(at: Date(), in: root)

        #expect(session.micFileURL.lastPathComponent == "mic.wav")
        #expect(session.systemFileURL.lastPathComponent == "system.wav")
        #expect(session.metadataURL.lastPathComponent == "metadata.json")
        #expect(session.micFileURL.deletingLastPathComponent() == session.directory)
    }

    // MARK: - helpers

    static func makeDate(y: Int, mo: Int, d: Int, h: Int, mi: Int, s: Int) -> Date {
        var c = DateComponents()
        c.year = y; c.month = mo; c.day = d; c.hour = h; c.minute = mi; c.second = s
        return Calendar.current.date(from: c)!
    }

    static func tempRoot() -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("MeetingRecorderTests-\(UUID().uuidString)", isDirectory: true)
    }
}

@MainActor
struct AudioDeviceSelectionTests {

    private static let devices = [
        AudioInputDevice(id: "builtin-1", name: "MacBook Pro Microphone"),
        AudioInputDevice(id: "earpods-2", name: "EarPods"),
    ]

    @Test func savedSelectionPresentInListIsKept() {
        #expect(AudioDeviceProvider.resolveSelection(savedID: "earpods-2", available: Self.devices) == "earpods-2")
    }

    @Test func savedSelectionMissingFallsBackToDefault() {
        // When the saved device has been unplugged (absent from the list), returns nil (= system default).
        #expect(AudioDeviceProvider.resolveSelection(savedID: "unplugged-9", available: Self.devices) == nil)
    }

    @Test func nilSelectionStaysNil() {
        #expect(AudioDeviceProvider.resolveSelection(savedID: nil, available: Self.devices) == nil)
    }
}

@MainActor
struct MetadataTests {

    @Test func buildProducesExpectedTrackParametersAndDuration() {
        let start = RecordingSessionTests.makeDate(y: 2026, mo: 6, d: 30, h: 15, mi: 30, s: 0)
        let end = start.addingTimeInterval(2_400) // 40 minutes
        let session = RecordingSession(directory: URL(fileURLWithPath: "/tmp/x"), startedAt: start, title: "meeting", counterpartName: "")

        let meta = MetadataBuilder.build(
            session: session, endedAt: end,
            micDeviceName: "Built-in Microphone",
            systemAudioCaptured: true,
            appVersion: "0.1.0"
        )

        #expect(meta.schemaVersion == 3)
        #expect(meta.title == "meeting")
        #expect(meta.counterpartName == "")
        #expect(meta.durationSec == 2_400)
        #expect(meta.sampleRate == 48_000)
        #expect(meta.files.mic.channels == 1)
        #expect(meta.files.mic.format == "wav_pcm_s16le")
        #expect(meta.files.system.channels == 2)
        #expect(meta.devices.micDeviceName == "Built-in Microphone")
        #expect(meta.devices.systemAudioCaptured == true)
    }

    @Test func jsonEncodesAndDecodesRoundTrip() throws {
        let start = RecordingSessionTests.makeDate(y: 2026, mo: 6, d: 30, h: 15, mi: 30, s: 0)
        let session = RecordingSession(directory: URL(fileURLWithPath: "/tmp/x"), startedAt: start, title: "週次定例", counterpartName: "田中")
        let meta = MetadataBuilder.build(
            session: session, endedAt: start.addingTimeInterval(60),
            micDeviceName: "EarPods", systemAudioCaptured: false, appVersion: "0.1.0"
        )

        #expect(meta.title == "週次定例")
        #expect(meta.counterpartName == "田中")

        let encoder = JSONEncoder()
        let data = try encoder.encode(meta)
        let decoded = try JSONDecoder().decode(RecordingMetadata.self, from: data)
        #expect(decoded == meta)

        // Confirms the key fields are present in the JSON
        let json = String(data: data, encoding: .utf8)!
        for key in ["schemaVersion", "title", "counterpartName", "startedAt", "durationSec", "systemAudioCaptured", "wav_pcm_s16le"] {
            #expect(json.contains(key))
        }
    }
}
