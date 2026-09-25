//
//  SilenceWatchdog.swift
//  MeetingRecorder
//
//  Pure-logic state machine for silence auto-stop. A value type with no side
//  effects or I/O, whose only job is deciding "has it been 2 minutes without
//  anyone speaking?". Actual speech detection is done by SpeechActivityMonitor
//  (SoundAnalysis); RecordingController carries out the stop itself.
//
//  Unarmed -> armed on first speech (holds the last-speech time) -> fires
//  once 120 seconds have passed since the last speech.
//  Each new speech event updates the last-speech time (= resets the count).
//

import Foundation

struct SilenceWatchdog {
    /// Grace period before silence triggers auto-stop. An empirical constant
    /// (trade-off between stopping too eagerly and letting it run too long).
    static let silenceThreshold: TimeInterval = 120

    /// Feature toggle (default ON). Never fires while OFF.
    var isEnabled: Bool

    /// Time of the last detected speech. nil means "no speech detected yet" = unarmed.
    private(set) var lastSpeechAt: Date?

    /// Armed once any speech has been detected (silence monitoring is active from then on).
    var isArmed: Bool { lastSpeechAt != nil }

    init(isEnabled: Bool = true) {
        self.isEnabled = isEnabled
        self.lastSpeechAt = nil
    }

    /// Records that speech was detected. Arms on the first call; resets the silence count thereafter.
    mutating func noteSpeech(at time: Date) {
        lastSpeechAt = time
    }

    /// Pure decision: given the current time, whether auto-stop should fire.
    /// Always false when disabled or unarmed. Once armed, true once the time since the last speech reaches the threshold.
    func shouldAutoStop(now: Date) -> Bool {
        guard isEnabled, let lastSpeechAt else { return false }
        return now.timeIntervalSince(lastSpeechAt) >= Self.silenceThreshold
    }
}
