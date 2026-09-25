//
//  SilenceWatchdogTests.swift
//  MeetingRecorderTests
//
//  Unit tests for the silence auto-stop pure-logic state machine.
//  The seam is "(last-speech time, current time, armed state) -> fire decision".
//

import Testing
import Foundation
@testable import MeetingRecorder

struct SilenceWatchdogTests {

    /// Reference time (a fixed point for computing `now` relatively within tests).
    private static let t0 = Date(timeIntervalSinceReferenceDate: 0)

    /// While unarmed (no speech ever detected), it never fires no matter how much time passes.
    /// This is what prevents a false stop from silence before recording starts (never arms until the first speech).
    @Test func doesNotFireWhileUnarmed() {
        let watchdog = SilenceWatchdog(isEnabled: true)
        #expect(watchdog.isArmed == false)
        #expect(watchdog.shouldAutoStop(now: Self.t0.addingTimeInterval(10_000)) == false)
    }

    /// Arms on the first detected speech.
    @Test func armsOnFirstSpeech() {
        var watchdog = SilenceWatchdog(isEnabled: true)
        watchdog.noteSpeech(at: Self.t0)
        #expect(watchdog.isArmed)
    }

    /// Fires exactly 120 seconds after the last speech.
    @Test func firesAfterThreshold() {
        var watchdog = SilenceWatchdog(isEnabled: true)
        watchdog.noteSpeech(at: Self.t0)
        let now = Self.t0.addingTimeInterval(SilenceWatchdog.silenceThreshold)
        #expect(watchdog.shouldAutoStop(now: now))
    }

    /// Doesn't fire yet below the threshold (119 seconds) — a boundary check.
    @Test func doesNotFireBeforeThreshold() {
        var watchdog = SilenceWatchdog(isEnabled: true)
        watchdog.noteSpeech(at: Self.t0)
        let now = Self.t0.addingTimeInterval(SilenceWatchdog.silenceThreshold - 1)
        #expect(watchdog.shouldAutoStop(now: now) == false)
    }

    /// New speech resets the count, as if the prior silence never happened.
    @Test func resetsOnSpeech() {
        var watchdog = SilenceWatchdog(isEnabled: true)
        watchdog.noteSpeech(at: Self.t0)
        // Speaks again after 119 seconds -> this becomes the new starting point.
        watchdog.noteSpeech(at: Self.t0.addingTimeInterval(SilenceWatchdog.silenceThreshold - 1))
        // At 120 seconds from the first speech, only 1 second has passed since the reset, so it doesn't fire yet.
        #expect(watchdog.shouldAutoStop(now: Self.t0.addingTimeInterval(SilenceWatchdog.silenceThreshold)) == false)
        // Finally fires 120 seconds after the second speech.
        let fireAt = Self.t0.addingTimeInterval(SilenceWatchdog.silenceThreshold - 1 + SilenceWatchdog.silenceThreshold)
        #expect(watchdog.shouldAutoStop(now: fireAt))
    }

    /// While disabled (feature toggle OFF), it never fires even once armed and past the threshold.
    @Test func neverFiresWhenDisabled() {
        var watchdog = SilenceWatchdog(isEnabled: false)
        watchdog.noteSpeech(at: Self.t0)
        #expect(watchdog.isArmed)
        #expect(watchdog.shouldAutoStop(now: Self.t0.addingTimeInterval(SilenceWatchdog.silenceThreshold * 10)) == false)
    }
}
