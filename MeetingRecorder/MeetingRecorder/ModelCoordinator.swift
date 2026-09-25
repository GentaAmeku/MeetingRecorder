//
//  ModelCoordinator.swift
//  MeetingRecorder
//
//  Owns status display and downloads for the transcription models (Whisper /
//  speaker diarization). The source of truth is the postprocess CLI
//  (--model-status / --download-models / --delete-models); this is a launch
//  role that shells out to it via Process and exposes status/progress to the
//  UI. Downloads run serially and keep going even if the sheet is closed
//  (state is observable from anywhere thanks to @Observable).
//

import Foundation
import Observation
import UserNotifications

@MainActor
@Observable
final class ModelCoordinator {
    enum ModelState: Equatable {
        case unknown            // not yet queried
        case missing            // not downloaded
        case ready              // downloaded
        case downloading(Int)   // downloading (%)
        case error(String)      // failed/incomplete
    }

    struct Model: Identifiable, Equatable {
        let id: String          // "whisper" | "diarization"
        let name: String
        let sizeLabel: String
        var state: ModelState
    }

    /// Whisper = required, speaker diarization = optional. Starts as unknown.
    private(set) var models: [Model] = [
        Model(id: "whisper", name: "Whisper (large-v3-turbo)", sizeLabel: "~1.5GB", state: .unknown),
        Model(id: "diarization", name: "Speaker diarization (sherpa-onnx)", sizeLabel: "~45MB", state: .unknown),
    ]

    /// Whether the CLI (external venv) can be found. Shows setup guidance when false.
    private(set) var cliAvailable = true

    var isWhisperReady: Bool { self[ "whisper" ]?.state == .ready }
    var anyMissing: Bool { models.contains { $0.state == .missing || $0.state == .unknown } }

    private var downloadQueue: [String] = []
    private var isDownloading = false

    init() {
        // Don't request notification authorization while running tests (XCTest host), to avoid
        // hanging on the permission dialog with nobody there to dismiss it.
        guard !RuntimeEnvironment.isRunningTests else { return }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    private subscript(_ id: String) -> Model? {
        models.first { $0.id == id }
    }

    private func stateOf(_ id: String) -> ModelState {
        self[id]?.state ?? .unknown
    }

    private func setState(_ id: String, _ state: ModelState) {
        guard let idx = models.firstIndex(where: { $0.id == id }) else { return }
        models[idx].state = state
    }

    // MARK: - Status query

    /// Runs `--model-status --json` and updates each model's state.
    func refreshStatus() async {
        guard CLILocator.isAvailable else {
            cliAvailable = false
            for m in models { setState(m.id, .unknown) }
            return
        }
        cliAvailable = true
        guard let out = await runCapturingStdout(["--model-status", "--json"]) else { return }
        struct Entry: Decodable { let id: String; let state: String }
        guard let data = out.data(using: .utf8),
              let entries = try? JSONDecoder().decode([Entry].self, from: data) else { return }
        for e in entries {
            switch e.state {
            case "ready":       setState(e.id, .ready)
            case "downloading": setState(e.id, .downloading(0))
            case "error":       setState(e.id, .error("Incomplete download"))
            default:            setState(e.id, .missing)
            }
        }
    }

    // MARK: - Download (serial, with progress)

    func download(_ id: String) {
        downloadQueue.append(id)
        Task { await drainDownloads() }
    }

    /// Re-download after an error/incomplete state (same as download, in practice).
    func retry(_ id: String) { download(id) }

    private func drainDownloads() async {
        guard !isDownloading else { return }   // serial: one at a time
        isDownloading = true
        defer { isDownloading = false }

        while !downloadQueue.isEmpty {
            let id = downloadQueue.removeFirst()
            guard CLILocator.isAvailable else {
                cliAvailable = false
                setState(id, .error("CLI not found"))
                continue
            }
            setState(id, .downloading(0))
            let name = self[id]?.name ?? id
            let ok = await runDownload(id)
            if ok {
                setState(id, .ready)
                notify(title: "Model download complete", body: name)
            } else {
                // Keep the message already set by a progress error line, if any.
                if case .error = stateOf(id) {} else {
                    setState(id, .error("Download failed"))
                }
                notify(title: "Model download failed", body: name)
            }
            await refreshStatus()
        }
    }

    /// Delete (the CLI removes the exact paths), then re-fetch status.
    func delete(_ id: String) async {
        guard CLILocator.isAvailable else { cliAvailable = false; return }
        _ = await runCapturingStdout(["--delete-models", "--only", id])
        await refreshStatus()
    }

    // MARK: - Process execution

    /// Reads stdout to completion and returns it as a string (for status query / delete).
    private func runCapturingStdout(_ arguments: [String]) async -> String? {
        await withCheckedContinuation { (cont: CheckedContinuation<String?, Never>) in
            DispatchQueue.global(qos: .utility).async {
                let p = Process()
                p.executableURL = CLILocator.resolvedURL
                p.arguments = arguments
                let outPipe = Pipe()
                p.standardOutput = outPipe
                p.standardError = Pipe()
                do { try p.run() } catch { cont.resume(returning: nil); return }
                let data = outPipe.fileHandleForReading.readDataToEndOfFile()
                p.waitUntilExit()
                cont.resume(returning: String(data: data, encoding: .utf8))
            }
        }
    }

    /// Runs `--download-models --only <id>` and reads stdout's JSON Lines progress to update the percentage.
    /// Returns true on success. Progress/errors are reflected into the model's state.
    private func runDownload(_ id: String) async -> Bool {
        await withCheckedContinuation { (cont: CheckedContinuation<Bool, Never>) in
            DispatchQueue.global(qos: .utility).async {
                let p = Process()
                p.executableURL = CLILocator.resolvedURL
                p.arguments = ["--download-models", "--only", id]
                let outPipe = Pipe()
                p.standardOutput = outPipe
                p.standardError = Pipe()

                let handle = outPipe.fileHandleForReading
                var buffer = Data()
                handle.readabilityHandler = { h in
                    buffer.append(h.availableData)
                    while let nl = buffer.firstIndex(of: 0x0A) {
                        let lineData = buffer.subdata(in: buffer.startIndex..<nl)
                        buffer.removeSubrange(buffer.startIndex...nl)
                        Self.handleProgressLine(lineData, id: id, coordinator: self)
                    }
                }

                do { try p.run() } catch {
                    Task { @MainActor in self.setState(id, .error(error.localizedDescription)) }
                    cont.resume(returning: false)
                    return
                }
                p.waitUntilExit()
                handle.readabilityHandler = nil
                cont.resume(returning: p.terminationStatus == 0)
            }
        }
    }

    private nonisolated static func handleProgressLine(_ data: Data, id: String, coordinator: ModelCoordinator) {
        guard !data.isEmpty,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let state = obj["state"] as? String else { return }
        let pct = (obj["pct"] as? Int) ?? 0
        Task { @MainActor in
            switch state {
            case "downloading": coordinator.setState(id, .downloading(max(0, min(99, pct))))
            case "error":       coordinator.setState(id, .error((obj["message"] as? String) ?? "Failed"))
            case "ready":       coordinator.setState(id, .ready)
            default:            break
            }
        }
    }

    // MARK: - First-run flow

    private static let firstRunKey = "modelSheetFirstRunShown"

    /// Whether the sheet should auto-open on first launch because Whisper isn't downloaded yet.
    func shouldPromptFirstRun() -> Bool {
        !UserDefaults.standard.bool(forKey: Self.firstRunKey) && !isWhisperReady
    }

    func markFirstRunPrompted() {
        UserDefaults.standard.set(true, forKey: Self.firstRunKey)
    }

    private func notify(title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}
