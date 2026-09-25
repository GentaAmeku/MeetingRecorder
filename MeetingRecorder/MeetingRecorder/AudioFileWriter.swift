//
//  AudioFileWriter.swift
//  MeetingRecorder
//
//  Converts an input PCM buffer to the target format (48kHz / 16-bit PCM /
//  given channel count) with AVAudioConverter and appends it to the WAV file.
//  nonisolated because append is called from the audio thread; serialized with NSLock.
//

import AVFoundation

nonisolated final class AudioFileWriter: @unchecked Sendable {
    private var file: AVAudioFile?
    private let targetFormat: AVAudioFormat
    private var converter: AVAudioConverter?
    private var converterInputFormat: AVAudioFormat?
    private var pendingInput: AVAudioPCMBuffer?
    private let lock = NSLock()

    /// - Parameters:
    ///   - url: Output destination (.wav). AVAudioFile infers WAV from the extension.
    ///   - sampleRate: 48000
    ///   - channels: mic=1 / system=2
    init(url: URL, sampleRate: Double = 48_000, channels: AVAudioChannelCount = 1) throws {
        // On disk: 16-bit integer PCM. Processing (write) buffer: Float32.
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: sampleRate,
            AVNumberOfChannelsKey: channels,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false
        ]
        let file = try AVAudioFile(forWriting: url, settings: settings,
                                   commonFormat: .pcmFormatFloat32, interleaved: false)
        self.file = file
        self.targetFormat = file.processingFormat
    }

    /// Converts the input buffer to the target format and writes it. Expected to be called from the audio thread.
    func append(_ inputBuffer: AVAudioPCMBuffer) {
        lock.lock(); defer { lock.unlock() }
        guard let file else { return }

        let inFormat = inputBuffer.format
        if inFormat == targetFormat {
            try? file.write(from: inputBuffer)
            return
        }

        if converter == nil || converterInputFormat != inFormat {
            converter = AVAudioConverter(from: inFormat, to: targetFormat)
            converterInputFormat = inFormat
        }
        guard let converter else { return }

        let ratio = targetFormat.sampleRate / inFormat.sampleRate
        let capacity = AVAudioFrameCount(Double(inputBuffer.frameLength) * ratio) + 1_024
        guard let outBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: capacity) else { return }

        // The input block runs synchronously inside convert(...). Instead of a mutable
        // flag, "supply exactly once" is expressed via this lock-protected property.
        pendingInput = inputBuffer
        let inputBlock: AVAudioConverterInputBlock = { [self] _, outStatus in
            if let buffer = pendingInput {
                pendingInput = nil
                outStatus.pointee = .haveData
                return buffer
            }
            outStatus.pointee = .noDataNow
            return nil
        }

        var convError: NSError?
        let status = converter.convert(to: outBuffer, error: &convError, withInputFrom: inputBlock)
        if (status == .haveData || status == .inputRanDry), outBuffer.frameLength > 0 {
            try? file.write(from: outBuffer)
        }
    }

    /// Finishes writing and finalizes the WAV header (finalized by releasing `file`). Ignores any further append calls.
    func close() {
        lock.lock(); defer { lock.unlock() }
        file = nil
    }
}
