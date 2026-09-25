//
//  SpeechActivityMonitor.swift
//  MeetingRecorder
//
//  A wrapper around SoundAnalysis (SNAudioStreamAnalyzer + the built-in
//  SNClassifySoundRequest classifier). Analyzes each PCM buffer CaptureEngine
//  receives for the speech class, and simply updates the "last speech time"
//  when confidence is above the threshold.
//  Does not use volume (RMS) as a signal (empirically, typing is louder than voice).
//
//  The only side effect is updating the last-speech time (thread-safe). Stop
//  decisions belong to SilenceWatchdog / RecordingController.
//  1 stream (either mic or system) = 1 instance. The format is lazily fixed
//  from the first buffer.
//

import Foundation
import AVFoundation
import SoundAnalysis

nonisolated final class SpeechActivityMonitor: NSObject, SNResultsObserving, @unchecked Sendable {
    /// Minimum classification confidence to count as speech. An empirical constant (tuned in practice).
    static let speechConfidenceThreshold: Double = 0.5

    /// The built-in classifier's speech class identifier.
    private static let speechIdentifier = "speech"

    private let lock = NSLock()
    private var _lastSpeechAt: Date?

    /// Time speech was most recently detected (nil if never). Readable from any thread.
    var lastSpeechAt: Date? {
        lock.lock(); defer { lock.unlock() }
        return _lastSpeechAt
    }

    private var analyzer: SNAudioStreamAnalyzer?
    private var request: SNClassifySoundRequest?
    private var sampleCursor: AVAudioFramePosition = 0

    /// Feeds one PCM buffer to the analyzer. Expected to be called on CaptureEngine's sampleQueue.
    /// Builds the analyzer/request from the input format on first call (reused after that).
    /// Fails silently so a failure never blocks the recording write path (detection is best-effort).
    func analyze(_ buffer: AVAudioPCMBuffer) {
        guard let analyzer = ensureAnalyzer(format: buffer.format) else { return }
        analyzer.analyze(buffer, atAudioFramePosition: sampleCursor)
        sampleCursor += AVAudioFramePosition(buffer.frameLength)
    }

    private func ensureAnalyzer(format: AVAudioFormat) -> SNAudioStreamAnalyzer? {
        if let analyzer { return analyzer }
        let newAnalyzer = SNAudioStreamAnalyzer(format: format)
        guard let classifyRequest = try? SNClassifySoundRequest(classifierIdentifier: .version1) else {
            return nil
        }
        // The built-in classifier's window is about 0.975s. The default overlap is fine
        // (second-level granularity is enough for speech detection).
        guard (try? newAnalyzer.add(classifyRequest, withObserver: self)) != nil else { return nil }
        analyzer = newAnalyzer
        request = classifyRequest
        return newAnalyzer
    }

    // MARK: - SNResultsObserving

    func request(_ request: SNRequest, didProduce result: SNResult) {
        guard let classification = result as? SNClassificationResult else { return }
        guard let speech = classification.classification(forIdentifier: Self.speechIdentifier) else { return }
        guard speech.confidence >= Self.speechConfidenceThreshold else { return }
        lock.lock(); _lastSpeechAt = Date(); lock.unlock()
    }

    func request(_ request: SNRequest, didFailWithError error: Error) {
        // Treat an analysis failure as no detection (recording itself continues).
    }

    func requestDidComplete(_ request: SNRequest) {}
}
