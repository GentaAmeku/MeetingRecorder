//
//  TranscriptionCoordinator.swift
//  MeetingRecorder
//
//  A launch role that shells out to the postprocess CLI as a subprocess,
//  under the recording app's umbrella, to perform auto-transcription. The
//  child process inherits the FDA (Full Disk Access) grant given to the
//  recording app, so it can read ~/Documents's recordings/venv (avoiding TCC).
//  Runs one job at a time on a serial queue, and reports status and
//  notifications. Never summarizes.
//

import Foundation
import Observation
import UserNotifications

/// Transcription state, tracked separately from the recording state machine.
enum TranscriptionState: Equatable {
    case idle
    case running(label: String)
    case done(label: String, sourceAudioRetained: Bool)
    case failed(message: String)
    /// Transcription was guarded because the required model (Whisper) isn't downloaded. Routes to the model sheet.
    case needsModel(message: String)
}

enum TranscriptionArguments {
    static func session(_ path: String, keepSourceAudio: Bool) -> [String] {
        [path] + keepSourceAudioFlag(keepSourceAudio)
    }

    static func allPending(keepSourceAudio: Bool) -> [String] {
        ["--all-pending"] + keepSourceAudioFlag(keepSourceAudio)
    }

    private static func keepSourceAudioFlag(_ enabled: Bool) -> [String] {
        enabled ? ["--keep-source-audio"] : []
    }
}

@MainActor
@Observable
final class TranscriptionCoordinator {
    private(set) var state: TranscriptionState = .idle

    private struct Job {
        let label: String
        let arguments: [String]
        let sourceAudioRetained: Bool
        let sessionDirectory: URL?
        let onSuccess: ((URL) -> Void)?
    }

    private var queue: [Job] = []
    private var isDraining = false

    init() {
        // Don't request notification authorization while running tests (XCTest host), to avoid
        // hanging on the permission dialog with nobody there to dismiss it.
        guard !RuntimeEnvironment.isRunningTests else { return }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    // MARK: - Enqueue (intents)

    /// Transcribes a given session (the automatic trigger uses this).
    func enqueue(
        session directory: URL,
        keepSourceAudio: Bool = false,
        onSuccess: ((URL) -> Void)? = nil
    ) {
        enqueue(Job(
            label: directory.lastPathComponent,
            arguments: TranscriptionArguments.session(
                directory.path,
                keepSourceAudio: keepSourceAudio
            ),
            sourceAudioRetained: keepSourceAudio,
            sessionDirectory: directory,
            onSuccess: onSuccess
        ))
    }

    /// Batch-processes anything pending (no transcript.md yet); the manual "Transcribe Now" uses this.
    func enqueueAllPending(keepSourceAudio: Bool = false) {
        enqueue(Job(
            label: "Pending batch",
            arguments: TranscriptionArguments.allPending(
                keepSourceAudio: keepSourceAudio
            ),
            sourceAudioRetained: keepSourceAudio,
            sessionDirectory: nil,
            onSuccess: nil
        ))
    }

    /// Reports in the state that transcription was guarded because the required model isn't downloaded.
    func reportNeedsModel(_ message: String) {
        state = .needsModel(message: message)
        notify(title: "Cannot transcribe", body: message)
    }

    private func enqueue(_ job: Job) {
        queue.append(job)
        Task { await drain() }
    }

    // MARK: - Serial execution

    private func drain() async {
        guard !isDraining else { return }   // serial: one at a time
        isDraining = true
        defer { isDraining = false }

        while !queue.isEmpty {
            let job = queue.removeFirst()
            state = .running(label: job.label)
            switch await run(job) {
            case .success:
                state = .done(
                    label: job.label,
                    sourceAudioRetained: job.sourceAudioRetained
                )
                let title = job.sourceAudioRetained
                    ? "Transcription done, audio kept"
                    : "Transcription done, audio deleted"
                notify(title: title, body: job.label)
                if let directory = job.sessionDirectory {
                    job.onSuccess?(directory)
                }
            case .toolMissing:
                let msg = "The transcription tool was not found. Please reinstall with scripts/install_app.sh."
                state = .failed(message: msg)
                notify(title: "Transcription failed", body: "Tool not found")
            case .permissionDenied:
                let msg = "Full Disk Access is required. Please grant it to MeetingRecorder in System Settings > Privacy & Security > Full Disk Access."
                state = .failed(message: msg)
                notify(title: "Transcription failed", body: "Full Disk Access is required")
            case .failed(let detail):
                state = .failed(message: "Post-processing failed: \(detail)")
                notify(title: "Post-processing failed", body: detail)
            }
        }
    }

    private enum RunResult {
        case success
        case toolMissing
        case permissionDenied
        case failed(String)
    }

    private func run(_ job: Job) async -> RunResult {
        let tool = CLILocator.resolvedURL
        guard CLILocator.isAvailable else {
            return .toolMissing
        }
        return await withCheckedContinuation { (continuation: CheckedContinuation<RunResult, Never>) in
            DispatchQueue.global(qos: .utility).async {
                let process = Process()
                process.executableURL = tool
                process.arguments = job.arguments
                let errPipe = Pipe()
                process.standardError = errPipe
                process.standardOutput = Pipe()
                do {
                    try process.run()
                } catch {
                    continuation.resume(returning: .failed(error.localizedDescription))
                    return
                }
                let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                let err = String(data: errData, encoding: .utf8) ?? ""

                if process.terminationStatus == 0 {
                    continuation.resume(returning: .success)
                } else if process.terminationStatus == 3 {
                    let tail = err.split(separator: "\n").last.map(String.init)
                        ?? "Failed to delete the audio file(s)"
                    continuation.resume(returning: .failed(tail))
                } else if err.contains("Operation not permitted") {
                    continuation.resume(returning: .permissionDenied)
                } else {
                    let tail = err.split(separator: "\n").last.map(String.init)
                        ?? "exit \(process.terminationStatus)"
                    continuation.resume(returning: .failed(tail))
                }
            }
        }
    }

    private func notify(title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}
