//
//  AgentHandoffDispatcher.swift
//  MeetingRecorder
//
//  Hands off the post-transcription Transcript location to the configured
//  AI agent (Claude Code / Codex). Opened either as a new Orca terminal, or
//  interactively via Terminal.app. Only the file path is passed in the
//  prompt, never the transcript body itself.
//

import AppKit
import Darwin
import Foundation

struct AgentHandoffCommandResult: Sendable, Equatable {
    let exitCode: Int32
    let standardOutput: String
    let standardError: String
    let timedOut: Bool
}

enum AgentHandoffDispatchError: Error, Equatable, LocalizedError {
    case transcriptMissing(String)
    case orcaNotFound
    case runtimeNotReady
    case terminalNotReady
    case commandTimedOut(step: String)
    case commandFailed(step: String, detail: String)
    case invalidResponse(step: String)
    case launchFailed(String)

    var errorDescription: String? {
        switch self {
        case .transcriptMissing(let path):
            return "Transcript not found: \(path)"
        case .orcaNotFound:
            return "The orca command was not found"
        case .runtimeNotReady:
            return "Orca is not running, or is not ready"
        case .terminalNotReady:
            return "The AI agent did not become ready for input within 60 seconds"
        case .commandTimedOut(let step):
            return "Orca's \(step) did not finish in time"
        case .commandFailed(let step, let detail):
            return "Orca's \(step) failed: \(detail)"
        case .invalidResponse(let step):
            return "Could not read Orca's \(step) response"
        case .launchFailed(let detail):
            return "Failed to launch Terminal: \(detail)"
        }
    }
}

nonisolated struct AgentHandoffDispatcher {
    typealias FileExists = (URL) -> Bool
    typealias OrcaCommandRunner = (URL, [String], TimeInterval) async -> AgentHandoffCommandResult
    typealias OrcaResolver = () -> URL?
    typealias TerminalOpener = (URL) async -> Bool
    typealias DirectoryCreator = (URL) throws -> Void
    typealias FileWriter = (String, URL) throws -> Void
    typealias PermissionSetter = (URL) throws -> Void

    /// An app launched from Finder has a minimal PATH, so check known locations in order.
    private static let orcaSearchPaths = [
        "/usr/local/bin/orca",
        "/opt/homebrew/bin/orca",
        "/Applications/Orca.app/Contents/Resources/bin/orca",
    ]

    private let fileExists: FileExists
    private let runOrca: OrcaCommandRunner
    private let resolveOrca: OrcaResolver
    private let openTerminal: TerminalOpener
    private let createDirectory: DirectoryCreator
    private let writeFile: FileWriter
    private let makeExecutable: PermissionSetter
    private let temporaryDirectory: () -> URL

    init(
        fileExists: @escaping FileExists = { FileManager.default.fileExists(atPath: $0.path) },
        runOrca: @escaping OrcaCommandRunner = Self.runProcess,
        resolveOrca: @escaping OrcaResolver = { AgentHandoffDispatcher.resolveOrcaURL() },
        openTerminal: @escaping TerminalOpener = Self.openInTerminal,
        createDirectory: @escaping DirectoryCreator = {
            try FileManager.default.createDirectory(at: $0, withIntermediateDirectories: true)
        },
        writeFile: @escaping FileWriter = { text, url in
            try text.write(to: url, atomically: true, encoding: .utf8)
        },
        makeExecutable: @escaping PermissionSetter = { url in
            try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: url.path)
        },
        temporaryDirectory: @escaping () -> URL = { FileManager.default.temporaryDirectory }
    ) {
        self.fileExists = fileExists
        self.runOrca = runOrca
        self.resolveOrca = resolveOrca
        self.openTerminal = openTerminal
        self.createDirectory = createDirectory
        self.writeFile = writeFile
        self.makeExecutable = makeExecutable
        self.temporaryDirectory = temporaryDirectory
    }

    /// Checks the known locations in order and returns the first executable found.
    static func resolveOrcaURL(
        isExecutable: (URL) -> Bool = { FileManager.default.isExecutableFile(atPath: $0.path) }
    ) -> URL? {
        for path in orcaSearchPaths {
            let url = URL(fileURLWithPath: path)
            if isExecutable(url) { return url }
        }
        return nil
    }

    /// Hands off the transcript to the AI agent.
    func dispatch(
        context: AgentHandoffContext,
        provider: AgentHandoffProvider,
        launchMethod: AgentHandoffLaunchMethod,
        workingDirectory: String,
        promptTemplate: String
    ) async throws {
        guard fileExists(URL(fileURLWithPath: context.transcriptPath)) else {
            throw AgentHandoffDispatchError.transcriptMissing(context.transcriptPath)
        }
        let prompt = AgentHandoffPrompt.render(promptTemplate, context: context)
        switch launchMethod {
        case .orca:
            try await dispatchViaOrca(
                context: context, provider: provider, workingDirectory: workingDirectory, prompt: prompt)
        case .terminal:
            try await dispatchViaTerminal(provider: provider, workingDirectory: workingDirectory, prompt: prompt)
        }
    }

    // MARK: - Orca

    private func dispatchViaOrca(
        context: AgentHandoffContext,
        provider: AgentHandoffProvider,
        workingDirectory: String,
        prompt: String
    ) async throws {
        guard let orcaURL = resolveOrca() else { throw AgentHandoffDispatchError.orcaNotFound }

        let status = try await command(orcaURL, ["status", "--json"], step: "status check")
        guard string(in: status, path: ["result", "runtime", "state"]) == "ready" else {
            throw AgentHandoffDispatchError.runtimeNotReady
        }

        let created = try await command(orcaURL, [
            "terminal", "create",
            "--worktree", "path:\(workingDirectory)",
            "--title", "\(context.meetingTitle) · \(provider.displayName)",
            "--command", provider.commandName,
            "--json",
        ], step: "AI agent launch")
        guard let handle = string(in: created, path: ["result", "terminal", "handle"]) else {
            throw AgentHandoffDispatchError.invalidResponse(step: "AI agent launch")
        }

        do {
            let waited = try await command(orcaURL, [
                "terminal", "wait",
                "--terminal", handle,
                "--for", "tui-idle",
                "--timeout-ms", "60000",
                "--json",
            ], step: "AI agent wait", timeout: 65)
            guard bool(in: waited, path: ["result", "wait", "satisfied"]) == true else {
                throw AgentHandoffDispatchError.terminalNotReady
            }

            _ = try await command(orcaURL, [
                "terminal", "send",
                "--terminal", handle,
                "--text", prompt,
                "--enter",
                "--json",
            ], step: "prompt send")
        } catch {
            await closeOrcaTerminal(orcaURL, handle: handle)
            throw error
        }
    }

    // Only called after a failure post-launch. A cleanup failure must not mask the original cause.
    private func closeOrcaTerminal(_ orcaURL: URL, handle: String) async {
        _ = try? await command(orcaURL, [
            "terminal", "close",
            "--terminal", handle,
            "--json",
        ], step: "terminal cleanup")
    }

    private func command(
        _ orcaURL: URL, _ arguments: [String], step: String, timeout: TimeInterval = 15
    ) async throws -> [String: Any] {
        let result = await runOrca(orcaURL, arguments, timeout)
        if result.timedOut {
            throw AgentHandoffDispatchError.commandTimedOut(step: step)
        }
        guard result.exitCode == 0 else {
            let detail = result.standardError.isEmpty
                ? "exit \(result.exitCode)"
                : result.standardError.trimmingCharacters(in: .whitespacesAndNewlines)
            throw AgentHandoffDispatchError.commandFailed(step: step, detail: detail)
        }
        guard
            let data = result.standardOutput.data(using: .utf8),
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            json["ok"] as? Bool == true
        else {
            throw AgentHandoffDispatchError.invalidResponse(step: step)
        }
        return json
    }

    private func value(in root: [String: Any], path: [String]) -> Any? {
        path.reduce(root as Any?) { current, key in (current as? [String: Any])?[key] }
    }

    private func string(in root: [String: Any], path: [String]) -> String? {
        value(in: root, path: path) as? String
    }

    private func bool(in root: [String: Any], path: [String]) -> Bool? {
        value(in: root, path: path) as? Bool
    }

    // MARK: - Terminal

    /// Creates and opens a `.command` file that launches Terminal.app
    /// interactively with the prompt. Uses NSWorkspace.open(url) so no
    /// AppleScript automation permission is needed (the same path as
    /// double-clicking the file in Finder).
    /// The prompt is written to a separate file rather than relying on any
    /// shell quoting; at run time the `.command` file reads it whole and
    /// passes it as a single argument (the result of command substitution is
    /// never re-interpreted, so any content in the prompt is safe).
    private func dispatchViaTerminal(
        provider: AgentHandoffProvider,
        workingDirectory: String,
        prompt: String
    ) async throws {
        let workDir = temporaryDirectory()
            .appendingPathComponent("MeetingRecorder-agent-\(UUID().uuidString)", isDirectory: true)
        try createDirectory(workDir)
        let promptURL = workDir.appendingPathComponent("prompt.txt")
        let scriptURL = workDir.appendingPathComponent("launch.command")
        // If the prompt starts with a hyphen, claude / codex would read it as an option, so prefix a space.
        try writeFile(prompt.hasPrefix("-") ? " " + prompt : prompt, promptURL)

        let script = """
            #!/bin/sh
            cd \(Self.shellQuote(workingDirectory)) || exit 1
            PROMPT="$(cat \(Self.shellQuote(promptURL.path)))"
            rm -rf \(Self.shellQuote(workDir.path))
            exec \(provider.commandName) "$PROMPT"
            """
        try writeFile(script, scriptURL)
        try makeExecutable(scriptURL)

        guard await openTerminal(scriptURL) else {
            throw AgentHandoffDispatchError.launchFailed("Could not open Terminal")
        }
    }

    /// Shell single-quoting. Safe even when the value itself contains quotes.
    private static func shellQuote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    static func openInTerminal(_ scriptURL: URL) async -> Bool {
        guard let terminalURL = NSWorkspace.shared.urlForApplication(
            withBundleIdentifier: "com.apple.Terminal"
        ) else {
            return false
        }
        let configuration = NSWorkspace.OpenConfiguration()
        return await withCheckedContinuation { continuation in
            NSWorkspace.shared.open([scriptURL], withApplicationAt: terminalURL, configuration: configuration) { _, error in
                continuation.resume(returning: error == nil)
            }
        }
    }

    static func runProcess(
        executable: URL,
        arguments: [String],
        timeout: TimeInterval
    ) async -> AgentHandoffCommandResult {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .utility).async {
                let process = Process()
                let outputPipe = Pipe()
                let errorPipe = Pipe()
                let termination = DispatchSemaphore(value: 0)
                process.executableURL = executable
                process.arguments = arguments
                process.standardOutput = outputPipe
                process.standardError = errorPipe
                process.terminationHandler = { _ in termination.signal() }

                do {
                    try process.run()
                } catch {
                    continuation.resume(returning: AgentHandoffCommandResult(
                        exitCode: -1,
                        standardOutput: "",
                        standardError: error.localizedDescription,
                        timedOut: false
                    ))
                    return
                }

                let output = AgentHandoffOutputBox()
                let error = AgentHandoffOutputBox()
                let readers = DispatchGroup()
                readers.enter()
                DispatchQueue.global(qos: .utility).async {
                    output.data = outputPipe.fileHandleForReading.readDataToEndOfFile()
                    readers.leave()
                }
                readers.enter()
                DispatchQueue.global(qos: .utility).async {
                    error.data = errorPipe.fileHandleForReading.readDataToEndOfFile()
                    readers.leave()
                }

                let timedOut = termination.wait(timeout: .now() + timeout) == .timedOut
                if timedOut {
                    process.terminate()
                    if termination.wait(timeout: .now() + 2) == .timedOut {
                        kill(process.processIdentifier, SIGKILL)
                    }
                }
                process.waitUntilExit()
                readers.wait()
                continuation.resume(returning: AgentHandoffCommandResult(
                    exitCode: process.terminationStatus,
                    standardOutput: String(data: output.data, encoding: .utf8) ?? "",
                    standardError: String(data: error.data, encoding: .utf8) ?? "",
                    timedOut: timedOut
                ))
            }
        }
    }
}

private final class AgentHandoffOutputBox: @unchecked Sendable {
    var data = Data()
}
