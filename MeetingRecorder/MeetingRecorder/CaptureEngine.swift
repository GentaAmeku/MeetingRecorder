//
//  CaptureEngine.swift
//  MeetingRecorder
//
//  Captures system audio and the microphone simultaneously through a single
//  ScreenCaptureKit stream, routing each output type to the mic.wav /
//  system.wav AudioFileWriter.
//  Video is received at a minimal configuration and discarded (audio only is saved).
//

import ScreenCaptureKit
import AVFoundation

enum CaptureEngineError: LocalizedError {
    case noDisplay

    var errorDescription: String? {
        switch self {
        case .noDisplay: return "Could not find a display to record."
        }
    }
}

nonisolated final class CaptureEngine: NSObject, SCStreamOutput, SCStreamDelegate, @unchecked Sendable {
    private var stream: SCStream?
    private let micWriter: AudioFileWriter
    private let systemWriter: AudioFileWriter
    private let sampleQueue = DispatchQueue(label: "MeetingRecorder.CaptureEngine")
    private let stateLock = NSLock()
    private var systemAudioReceived = false

    // Speech detection for silence auto-stop. mic / system are each analyzed by
    // their own instance (formats differ), and speech on either one resets the
    // timer. This class makes no stop decision itself.
    private let micSpeechMonitor = SpeechActivityMonitor()
    private let systemSpeechMonitor = SpeechActivityMonitor()

    /// Whether at least one system-audio sample has been received (for metadata.systemAudioCaptured).
    var systemAudioCaptured: Bool {
        stateLock.lock(); defer { stateLock.unlock() }
        return systemAudioReceived
    }

    /// The time speech was last detected on either mic or system (nil if never detected).
    /// Used by RecordingController for silence detection.
    var lastSpeechAt: Date? {
        [micSpeechMonitor.lastSpeechAt, systemSpeechMonitor.lastSpeechAt]
            .compactMap { $0 }
            .max()
    }

    /// - Parameters:
    ///   - micURL: Output destination for mic.wav (mono)
    ///   - systemURL: Output destination for system.wav (stereo)
    init(micURL: URL, systemURL: URL) throws {
        self.micWriter = try AudioFileWriter(url: micURL, sampleRate: 48_000, channels: 1)
        self.systemWriter = try AudioFileWriter(url: systemURL, sampleRate: 48_000, channels: 2)
        super.init()
    }

    /// - Parameter microphoneDeviceID: uniqueID of the microphone to use. nil uses SCK's system default.
    func start(microphoneDeviceID: String? = nil) async throws {
        // Capture target (SCK requires a target such as a display). Video is discarded, so the primary display is fine.
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else {
            throw CaptureEngineError.noDisplay
        }
        let filter = SCContentFilter(display: display, excludingWindows: [])

        let config = SCStreamConfiguration()
        config.capturesAudio = true          // system audio
        config.sampleRate = 48_000
        config.channelCount = 2
        config.captureMicrophone = true      // microphone (macOS 15+)
        if let microphoneDeviceID {
            config.microphoneCaptureDeviceID = microphoneDeviceID
        }
        config.excludesCurrentProcessAudio = true  // don't record this app's own audio
        // Video isn't used, so minimize it (frames are received but discarded)
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)

        let stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: sampleQueue)
        try stream.addStreamOutput(self, type: .microphone, sampleHandlerQueue: sampleQueue)
        try await stream.startCapture()
        self.stream = stream
    }

    func stop() async {
        try? await stream?.stopCapture()
        stream = nil
        systemWriter.close()
        micWriter.close()
    }

    // MARK: - SCStreamOutput

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
                of type: SCStreamOutputType) {
        guard sampleBuffer.isValid else { return }
        switch type {
        case .audio:
            if let buffer = Self.makePCMBuffer(from: sampleBuffer) {
                markSystemAudioReceived()
                systemWriter.append(buffer)
                systemSpeechMonitor.analyze(buffer)  // analyze for speech after writing
            }
        case .microphone:
            if let buffer = Self.makePCMBuffer(from: sampleBuffer) {
                micWriter.append(buffer)
                micSpeechMonitor.analyze(buffer)
            }
        case .screen:
            break // video is discarded
        @unknown default:
            break
        }
    }

    private func markSystemAudioReceived() {
        stateLock.lock(); defer { stateLock.unlock() }
        systemAudioReceived = true
    }

    // MARK: - CMSampleBuffer → AVAudioPCMBuffer

    private static func makePCMBuffer(from sampleBuffer: CMSampleBuffer) -> AVAudioPCMBuffer? {
        guard let formatDescription = sampleBuffer.formatDescription,
              var asbd = formatDescription.audioStreamBasicDescription,
              let format = AVAudioFormat(streamDescription: &asbd) else { return nil }

        let frameCount = AVAudioFrameCount(CMSampleBufferGetNumSamples(sampleBuffer))
        guard frameCount > 0,
              let pcmBuffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameCount) else { return nil }
        pcmBuffer.frameLength = frameCount

        let status = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer, at: 0, frameCount: Int32(frameCount),
            into: pcmBuffer.mutableAudioBufferList)
        guard status == noErr else { return nil }
        return pcmBuffer
    }
}
