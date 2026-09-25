//
//  RecordingController.swift
//  MeetingRecorder
//
//  The app's core. Holds the recording state machine and, on UI intents,
//  coordinates PermissionManager / MicRecorder / RecordingSession.
//

import Foundation
import Observation
import AppKit
import AVFoundation
import UserNotifications

enum AudioRetentionPreference {
    private static let key = "keepSourceAudio"

    static func keepsSourceAudio(in defaults: UserDefaults = .standard) -> Bool {
        defaults.object(forKey: key) as? Bool ?? false
    }

    static func setKeepsSourceAudio(
        _ enabled: Bool,
        in defaults: UserDefaults = .standard
    ) {
        defaults.set(enabled, forKey: key)
    }
}

@MainActor
@Observable
final class RecordingController {
    private(set) var state: RecordingState = .idle
    private(set) var elapsed: TimeInterval = 0
    private(set) var lastSessionDirectory: URL?

    /// Manages meeting info received from OnCue and its notice display.
    let meetingPreparation: MeetingPreparationCoordinator

    /// List of available input devices (for UI display).
    private(set) var availableInputDevices: [AudioInputDevice] = []

    /// Currently selected microphone uniqueID. nil is the system default. Changes persist to UserDefaults.
    var selectedMicDeviceID: String? {
        didSet { UserDefaults.standard.set(selectedMicDeviceID, forKey: Self.deviceSelectionKey) }
    }

    private static let deviceSelectionKey = "selectedMicDeviceID"

    /// Whether to keep the original mic.wav / system.wav after transcription. Default OFF (audio is deleted).
    var keepSourceAudio: Bool {
        didSet { AudioRetentionPreference.setKeepsSourceAudio(keepSourceAudio) }
    }

    /// AI agent to hand off to after transcription. nil = none (default).
    var agentHandoffProvider: AgentHandoffProvider? {
        didSet { AgentHandoffPreference.setProvider(agentHandoffProvider) }
    }

    /// How to open the AI agent. Default: Orca.
    var agentHandoffLaunchMethod: AgentHandoffLaunchMethod {
        didSet { AgentHandoffPreference.setLaunchMethod(agentHandoffLaunchMethod) }
    }

    /// Working directory where the AI agent is launched. Empty string means "unset".
    var agentHandoffWorkingDirectory: String {
        didSet { AgentHandoffPreference.setWorkingDirectory(agentHandoffWorkingDirectory) }
    }

    /// Prompt sent to the AI agent (multi-line).
    var agentHandoffPromptTemplate: String {
        didSet { AgentHandoffPreference.setPromptTemplate(agentHandoffPromptTemplate) }
    }

    /// Filter string for the target meeting title. Empty string means "always run".
    var agentHandoffTitleFilter: String {
        didSet { AgentHandoffPreference.setTitleFilter(agentHandoffTitleFilter) }
    }

    /// Whether to auto-stop recording after 2 minutes without speech. Default ON. Persists to UserDefaults.
    var silenceAutoStopEnabled: Bool {
        didSet { UserDefaults.standard.set(silenceAutoStopEnabled, forKey: Self.silenceAutoStopKey) }
    }

    private static let silenceAutoStopKey = "silenceAutoStopEnabled"

    /// Transcription language passed to the postprocess CLI. Default Auto-detect.
    /// Persists to postprocess-config.json's transcript.language (read by the CLI itself).
    var transcriptionLanguage: TranscriptionLanguage {
        didSet {
            transcriptionLanguageSaveError = PostprocessConfigStore.writeLanguage(transcriptionLanguage)
                ? nil
                : "Couldn't save: postprocess-config.json isn't valid JSON. Fix or delete it, then choose again."
        }
    }
    /// Set when the language couldn't be written to postprocess-config.json.
    var transcriptionLanguageSaveError: String?

    /// Launch role for transcription (runs the postprocess CLI as a subprocess).
    let transcription = TranscriptionCoordinator()

    /// Launch role for sending to the AI agent after transcription.
    let agentHandoff = AgentHandoffCoordinator()

    /// Status display and downloads for the models (Whisper / speaker diarization).
    let models = ModelCoordinator()

    /// Meeting name (optional). Reflected into the folder name / metadata.title when recording starts.
    /// Not persisted (entered per meeting).
    var meetingName: String = ""

    /// The counterpart's real name (optional). Reflected into metadata.counterpartName when recording starts.
    /// Setting it implies a 1-on-1 meeting: post-processing turns off diarization and renders "the other
    /// side" as this real name. Not persisted.
    var counterpartName: String = ""

    private let permissions = PermissionManager()
    private var captureEngine: CaptureEngine?
    private var session: RecordingSession?
    private var micDeviceName: String = "Unknown"
    private var timerTask: Task<Void, Never>?

    /// Pure decision logic for silence auto-stop. Rebuilt with the current toggle value each time recording starts.
    private var silenceWatchdog = SilenceWatchdog()

    var isRecording: Bool {
        if case .recording = state { return true }
        return false
    }

    /// Time speech was last detected on either mic or system during recording.
    /// nil if no speech has occurred yet (unarmed).
    var lastSpeechDetectedAt: Date? {
        captureEngine?.lastSpeechAt
    }

    init(meetingPreparation: MeetingPreparationCoordinator? = nil) {
        self.meetingPreparation = meetingPreparation ?? MeetingPreparationCoordinator()
        selectedMicDeviceID = UserDefaults.standard.string(forKey: Self.deviceSelectionKey)
        keepSourceAudio = AudioRetentionPreference.keepsSourceAudio()
        let handoffSettings = AgentHandoffPreference.settings()
        agentHandoffProvider = handoffSettings.provider
        agentHandoffLaunchMethod = handoffSettings.launchMethod
        agentHandoffWorkingDirectory = handoffSettings.workingDirectory
        agentHandoffPromptTemplate = handoffSettings.promptTemplate
        agentHandoffTitleFilter = handoffSettings.titleFilter
        silenceAutoStopEnabled = UserDefaults.standard.object(forKey: Self.silenceAutoStopKey) as? Bool ?? true
        transcriptionLanguage = PostprocessConfigStore.readLanguage() ?? .auto
        refreshInputDevices()
        Task { await models.refreshStatus() }
    }

    /// Refreshes the input device list, falling back to the default if the selection is no longer present.
    func refreshInputDevices() {
        availableInputDevices = AudioDeviceProvider.availableInputDevices()
        selectedMicDeviceID = AudioDeviceProvider.resolveSelection(
            savedID: selectedMicDeviceID, available: availableInputDevices)
    }

    // MARK: - UI intents

    func startTapped() {
        meetingPreparation.recordingWillStart()
        Task { await start() }
    }

    /// Validates OnCue's custom URL and applies the meeting info only when not currently recording.
    func receiveMeetingLaunchURL(_ url: URL) {
        do {
            let request = try MeetingLaunchRequest(url: url)
            guard meetingPreparation.prepare(for: state) == .prepared else {
                return
            }
            meetingName = request.title
            counterpartName = request.counterpartName
        } catch {
            meetingPreparation.rejectInvalidRequest()
        }
    }

    func stopTapped() {
        Task { await stop() }
    }

    func dismissError() {
        if case .idle = state { return }
        state = .idle
    }

    /// Opens the save location in Finder. Highlights the most recent session if one exists;
    /// otherwise opens the recordings root (creating it if needed). Always selectable, even before recording.
    func revealRecordingsLocation() {
        if let dir = lastSessionDirectory {
            NSWorkspace.shared.activateFileViewerSelecting([dir])
            return
        }
        let root = RecordingSession.recordingsRoot
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        NSWorkspace.shared.open(root)
    }

    /// Manual "Transcribe Now": batch-processes anything pending (no transcript.md yet).
    /// Guards against implicitly downloading the required model (Whisper) when it's missing.
    func transcribeAllPendingTapped() {
        Task {
            guard CLILocator.isAvailable else {
                transcription.reportNeedsModel("The transcription tool was not found. Please reinstall with scripts/install_app.sh.")
                return
            }
            await models.refreshStatus()
            if models.isWhisperReady {
                transcription.enqueueAllPending(keepSourceAudio: keepSourceAudio)
            } else {
                transcription.reportNeedsModel("Whisper has not been downloaded. Please download the model.")
            }
        }
    }

    func openSettings(for kind: PermissionKind) {
        if let url = URL(string: kind.settingsURLString) {
            NSWorkspace.shared.open(url)
        }
    }

    /// Opens the Full Disk Access settings pane (the fallback path when transcription fails on permissions).
    func openFullDiskAccessSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles") {
            NSWorkspace.shared.open(url)
        }
    }

    // MARK: - State machine

    private func start() async {
        switch state {
        case .recording, .finalizing:
            return
        default:
            break
        }

        // Both microphone and screen recording permissions are required (a single stream means
        // screen recording is a prerequisite for the whole recording).
        let micOK = await permissions.requestMicrophoneAccess()
        let screenOK = permissions.requestScreenRecordingAccess()
        var missing: Set<PermissionKind> = []
        if !micOK { missing.insert(.microphone) }
        if !screenOK { missing.insert(.screenRecording) }
        guard missing.isEmpty else {
            state = .needsPermission(missing: missing)
            return
        }

        do {
            refreshInputDevices()
            let deviceID = AudioDeviceProvider.resolveSelection(
                savedID: selectedMicDeviceID, available: availableInputDevices)

            let session = try RecordingSession.create(name: meetingName, counterpart: counterpartName)
            let engine = try CaptureEngine(micURL: session.micFileURL, systemURL: session.systemFileURL)
            try await engine.start(microphoneDeviceID: deviceID)
            self.session = session
            self.captureEngine = engine
            self.micDeviceName = AudioDeviceProvider.deviceName(for: deviceID, available: availableInputDevices)
            self.lastSessionDirectory = session.directory
            self.elapsed = 0
            // Silence monitoring resets on every recording start (unarmed: doesn't fire until the
            // first speech). Reflects the current toggle value.
            self.silenceWatchdog = SilenceWatchdog(isEnabled: silenceAutoStopEnabled)
            self.state = .recording
            startTimer(from: session.startedAt)
        } catch {
            state = .error("Failed to start recording: \(error.localizedDescription)")
        }
    }

    private func stop(auto: Bool = false) async {
        guard case .recording = state else { return }
        state = .finalizing
        stopTimer()
        if auto { notifyAutoStopped() }

        let systemCaptured = captureEngine?.systemAudioCaptured ?? false
        await captureEngine?.stop()   // stop the stream -> finalizes both WAV headers
        captureEngine = nil

        // Write out metadata.json once both files are finalized.
        if let session {
            let metadata = MetadataBuilder.build(
                session: session,
                endedAt: Date(),
                micDeviceName: micDeviceName,
                systemAudioCaptured: systemCaptured
            )
            do {
                try MetadataBuilder.write(metadata, to: session.metadataURL)
            } catch {
                // The audio files themselves are already saved; only report the metadata write failure.
                self.session = nil
                state = .error("Failed to write metadata (audio was already saved): \(error.localizedDescription)")
                return
            }
        }

        let finishedSession = session
        session = nil
        state = .idle

        // Always transcribe once recording stops (recording state is already idle; post-processing
        // runs on the Coordinator's serial queue, so it never blocks recording).
        // Guards against implicitly downloading the required model (Whisper) when it's missing.
        if let finishedSession {
            guard CLILocator.isAvailable else {
                transcription.reportNeedsModel("The transcription tool was not found. Please reinstall with scripts/install_app.sh.")
                return
            }
            await models.refreshStatus()
            if models.isWhisperReady {
                transcription.enqueue(
                    session: finishedSession.directory,
                    keepSourceAudio: keepSourceAudio
                ) { [weak self] directory in
                    guard let self else { return }
                    let handoffSettings = AgentHandoffSettings(
                        provider: self.agentHandoffProvider,
                        launchMethod: self.agentHandoffLaunchMethod,
                        workingDirectory: self.agentHandoffWorkingDirectory,
                        promptTemplate: self.agentHandoffPromptTemplate,
                        titleFilter: self.agentHandoffTitleFilter
                    )
                    guard AgentHandoffPolicy.shouldRun(
                        settings: handoffSettings,
                        meetingTitle: finishedSession.title
                    ) else { return }
                    self.agentHandoff.enqueue(
                        context: AgentHandoffContext(
                            transcriptPath: directory.appendingPathComponent("transcript.md").path,
                            sessionDirectory: directory.path,
                            meetingTitle: finishedSession.title,
                            counterpartName: finishedSession.counterpartName
                        ),
                        settings: handoffSettings
                    )
                }
            } else {
                transcription.reportNeedsModel("Whisper has not been downloaded. Please download the model.")
            }
        }
    }

    // MARK: - Timer

    private func startTimer(from start: Date) {
        // A Task created in a @MainActor context inherits MainActor, so updating `elapsed` here is safe.
        timerTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard let self else { return }
                let now = Date()
                self.elapsed = now.timeIntervalSince(start)
                // Feed the last-speech time to the watchdog every second; auto-stop after 2 minutes of silence.
                if let speechAt = self.captureEngine?.lastSpeechAt {
                    self.silenceWatchdog.noteSpeech(at: speechAt)
                }
                if self.silenceWatchdog.shouldAutoStop(now: now) {
                    await self.stop(auto: true)   // reuses the normal stop path (metadata / auto-transcription follow)
                    return
                }
            }
        }
    }

    private func stopTimer() {
        timerTask?.cancel()
        timerTask = nil
    }

    // MARK: - Notification

    /// Lets the user know recording was auto-stopped (so an overly eager stop doesn't go unnoticed).
    /// Not shown for a manual stop. Shares the same permission request as the existing
    /// post-processing/model notifications (does not call requestAuthorization separately).
    private func notifyAutoStopped() {
        let content = UNMutableNotificationContent()
        content.title = "Recording auto-stopped"
        content.body = "No speech was detected for 2 minutes. You can turn this off in Settings."
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}
