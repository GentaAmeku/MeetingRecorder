// Verifies the contract of handing off to an AI agent (Claude Code / Codex) after transcription.

import Foundation
import Testing
@testable import MeetingRecorder

@MainActor
struct AgentHandoffPolicyTests {
    @Test func noProviderNeverRuns() {
        var settings = AgentHandoffSettings.empty
        settings.workingDirectory = "/tmp/work"
        #expect(!AgentHandoffPolicy.shouldRun(settings: settings, meetingTitle: "週次定例"))
    }

    @Test func providerWithoutWorkingDirectoryNeverRuns() {
        var settings = AgentHandoffSettings.empty
        settings.provider = .claudeCode
        #expect(!AgentHandoffPolicy.shouldRun(settings: settings, meetingTitle: "週次定例"))
    }

    @Test func emptyTitleFilterMatchesEveryMeeting() {
        var settings = AgentHandoffSettings.empty
        settings.provider = .codex
        settings.workingDirectory = "/tmp/work"
        #expect(AgentHandoffPolicy.shouldRun(settings: settings, meetingTitle: "週次定例"))
        #expect(AgentHandoffPolicy.shouldRun(settings: settings, meetingTitle: "朝会"))
    }

    @Test func nonEmptyTitleFilterRequiresMatch() {
        var settings = AgentHandoffSettings.empty
        settings.provider = .claudeCode
        settings.workingDirectory = "/tmp/work"
        settings.titleFilter = "朝会"
        #expect(AgentHandoffPolicy.shouldRun(settings: settings, meetingTitle: "開発朝会"))
        #expect(!AgentHandoffPolicy.shouldRun(settings: settings, meetingTitle: "週次定例"))
    }

    @Test func preferencesRoundTripThroughUserDefaults() throws {
        let suite = "AgentHandoffPreferenceTests.\(UUID().uuidString)"
        let defaults = try #require(UserDefaults(suiteName: suite))
        defer {
            defaults.removePersistentDomain(forName: suite)
            let plist = FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Preferences/\(suite).plist")
            try? FileManager.default.removeItem(at: plist)
        }

        let initial = AgentHandoffPreference.settings(in: defaults)
        #expect(initial.provider == nil)
        #expect(initial.launchMethod == .orca)
        #expect(initial.workingDirectory == "")
        #expect(initial.promptTemplate == AgentHandoffSettings.defaultPromptTemplate)
        #expect(initial.titleFilter == "")

        AgentHandoffPreference.setProvider(.codex, in: defaults)
        AgentHandoffPreference.setLaunchMethod(.terminal, in: defaults)
        AgentHandoffPreference.setWorkingDirectory("/tmp/agent-work", in: defaults)
        AgentHandoffPreference.setPromptTemplate("Prompt: {transcript}", in: defaults)
        AgentHandoffPreference.setTitleFilter("朝会", in: defaults)

        let saved = AgentHandoffPreference.settings(in: defaults)
        #expect(saved.provider == .codex)
        #expect(saved.launchMethod == .terminal)
        #expect(saved.workingDirectory == "/tmp/agent-work")
        #expect(saved.promptTemplate == "Prompt: {transcript}")
        #expect(saved.titleFilter == "朝会")

        AgentHandoffPreference.setProvider(nil, in: defaults)
        #expect(AgentHandoffPreference.settings(in: defaults).provider == nil)
    }

    @Test func promptPlaceholdersAreSubstituted() {
        let context = AgentHandoffContext(
            transcriptPath: "/tmp/session/transcript.md",
            sessionDirectory: "/tmp/session",
            meetingTitle: "開発朝会",
            counterpartName: "相手"
        )
        let rendered = AgentHandoffPrompt.render(
            "T:{transcript} S:{session} Ti:{title} C:{counterpart}",
            context: context
        )
        #expect(rendered == "T:/tmp/session/transcript.md S:/tmp/session Ti:開発朝会 C:相手")
    }
}

// MARK: - Dispatcher (Orca path)

@MainActor
struct AgentHandoffDispatcherOrcaTests {
    private static let context = AgentHandoffContext(
        transcriptPath: "/tmp/2026-09-25_1000_朝会/transcript.md",
        sessionDirectory: "/tmp/2026-09-25_1000_朝会",
        meetingTitle: "朝会",
        counterpartName: ""
    )

    private static func okResult(_ json: String) -> AgentHandoffCommandResult {
        AgentHandoffCommandResult(exitCode: 0, standardOutput: json, standardError: "", timedOut: false)
    }

    @Test func missingTranscriptNeverCallsOrca() async {
        let dispatcher = AgentHandoffDispatcher(
            fileExists: { _ in false },
            runOrca: { _, _, _ in
                Issue.record("must not call orca when the Transcript is missing")
                return AgentHandoffCommandResult(exitCode: 0, standardOutput: "", standardError: "", timedOut: false)
            },
            resolveOrca: { URL(fileURLWithPath: "/usr/local/bin/orca") }
        )

        await #expect(throws: AgentHandoffDispatchError.transcriptMissing(Self.context.transcriptPath)) {
            try await dispatcher.dispatch(
                context: Self.context, provider: .claudeCode, launchMethod: .orca,
                workingDirectory: "/tmp/work", promptTemplate: "Prompt"
            )
        }
    }

    @Test func orcaNotFoundIsRejectedBeforeRunning() async {
        let dispatcher = AgentHandoffDispatcher(
            fileExists: { _ in true },
            runOrca: { _, _, _ in
                Issue.record("must not call orca when it cannot be found")
                return AgentHandoffCommandResult(exitCode: 0, standardOutput: "", standardError: "", timedOut: false)
            },
            resolveOrca: { nil }
        )

        await #expect(throws: AgentHandoffDispatchError.orcaNotFound) {
            try await dispatcher.dispatch(
                context: Self.context, provider: .claudeCode, launchMethod: .orca,
                workingDirectory: "/tmp/work", promptTemplate: "Prompt"
            )
        }
    }

    @Test func successfulRunSendsPromptAfterTerminalIsIdle() async throws {
        actor Capture {
            private(set) var calls: [[String]] = []
            func record(_ arguments: [String]) { calls.append(arguments) }
        }
        let capture = Capture()

        let dispatcher = AgentHandoffDispatcher(
            fileExists: { _ in true },
            runOrca: { _, arguments, _ in
                await capture.record(arguments)
                switch arguments.first {
                case "status":
                    return Self.okResult(#"{"ok":true,"result":{"runtime":{"state":"ready"}}}"#)
                case "terminal" where arguments[1] == "create":
                    return Self.okResult(#"{"ok":true,"result":{"terminal":{"handle":"h1"}}}"#)
                case "terminal" where arguments[1] == "wait":
                    return Self.okResult(#"{"ok":true,"result":{"wait":{"satisfied":true}}}"#)
                case "terminal" where arguments[1] == "send":
                    return Self.okResult(#"{"ok":true}"#)
                default:
                    Issue.record("unexpected orca call: \(arguments)")
                    return Self.okResult(#"{"ok":false}"#)
                }
            },
            resolveOrca: { URL(fileURLWithPath: "/usr/local/bin/orca") }
        )

        try await dispatcher.dispatch(
            context: Self.context, provider: .codex, launchMethod: .orca,
            workingDirectory: "/tmp/work", promptTemplate: "Transcript: {transcript}"
        )

        let calls = await capture.calls
        #expect(calls.count == 4)
        #expect(calls[0] == ["status", "--json"])
        #expect(calls[1].contains("--worktree"))
        #expect(calls[1].contains("path:/tmp/work"))
        #expect(calls[1].contains("--command"))
        #expect(calls[1].contains("codex"))
        #expect(calls[2][0...1] == ["terminal", "wait"])
        #expect(calls[3][0...1] == ["terminal", "send"])
        #expect(calls[3].contains("Transcript: /tmp/2026-09-25_1000_朝会/transcript.md"))
    }

    @Test func terminalNotIdleClosesTheTerminalAndFails() async throws {
        actor Capture {
            private(set) var closedHandles: [String] = []
            func recordClose(_ handle: String) { closedHandles.append(handle) }
        }
        let capture = Capture()

        let dispatcher = AgentHandoffDispatcher(
            fileExists: { _ in true },
            runOrca: { _, arguments, _ in
                switch arguments.first {
                case "status":
                    return Self.okResult(#"{"ok":true,"result":{"runtime":{"state":"ready"}}}"#)
                case "terminal" where arguments[1] == "create":
                    return Self.okResult(#"{"ok":true,"result":{"terminal":{"handle":"h1"}}}"#)
                case "terminal" where arguments[1] == "wait":
                    return Self.okResult(#"{"ok":true,"result":{"wait":{"satisfied":false}}}"#)
                case "terminal" where arguments[1] == "close":
                    await capture.recordClose(arguments[3])
                    return Self.okResult(#"{"ok":true}"#)
                default:
                    Issue.record("must not proceed as far as sending: \(arguments)")
                    return Self.okResult(#"{"ok":false}"#)
                }
            },
            resolveOrca: { URL(fileURLWithPath: "/usr/local/bin/orca") }
        )

        await #expect(throws: AgentHandoffDispatchError.terminalNotReady) {
            try await dispatcher.dispatch(
                context: Self.context, provider: .claudeCode, launchMethod: .orca,
                workingDirectory: "/tmp/work", promptTemplate: "Prompt"
            )
        }
        #expect(await capture.closedHandles == ["h1"])
    }
}

// MARK: - Dispatcher (Terminal path)

/// A simple recorder for tests, written to directly from synchronous
/// closures (writeFile / makeExecutable / openTerminal). No need to make
/// this an actor since it's only ever called in order within a single task.
private final class RecordingBox: @unchecked Sendable {
    private(set) var writes: [(text: String, path: String)] = []
    private(set) var madeExecutable: [String] = []
    private(set) var opened: [String] = []

    func recordWrite(_ text: String, _ path: String) { writes.append((text, path)) }
    func recordExecutable(_ path: String) { madeExecutable.append(path) }
    func recordOpen(_ path: String) { opened.append(path) }
}

@MainActor
struct AgentHandoffDispatcherTerminalTests {
    private static let context = AgentHandoffContext(
        transcriptPath: "/tmp/session/transcript.md",
        sessionDirectory: "/tmp/session",
        meetingTitle: "朝会",
        counterpartName: ""
    )

    @Test func writesPromptAndScriptThenOpensTerminal() async throws {
        let capture = RecordingBox()
        let workDir = URL(fileURLWithPath: "/tmp/AgentHandoffDispatcherTerminalTests-fixed")

        let dispatcher = AgentHandoffDispatcher(
            fileExists: { _ in true },
            openTerminal: { url in
                capture.recordOpen(url.path)
                return true
            },
            createDirectory: { _ in },
            writeFile: { text, url in capture.recordWrite(text, url.path) },
            makeExecutable: { url in capture.recordExecutable(url.path) },
            temporaryDirectory: { workDir }
        )

        try await dispatcher.dispatch(
            context: Self.context, provider: .claudeCode, launchMethod: .terminal,
            workingDirectory: "/tmp/it's a folder", promptTemplate: "本文には{transcript}を渡す"
        )

        let promptWrite = capture.writes.first { $0.path.hasSuffix("prompt.txt") }
        #expect(promptWrite?.text == "本文には/tmp/session/transcript.mdを渡す")

        let scriptWrite = capture.writes.first { $0.path.hasSuffix("launch.command") }
        #expect(scriptWrite != nil)
        #expect(scriptWrite?.text.contains("exec claude") == true)
        #expect(scriptWrite?.text.contains("cd '/tmp/it'\\''s a folder'") == true)
        #expect(scriptWrite?.text.contains("cat") == true)

        #expect(capture.madeExecutable.first?.hasSuffix("launch.command") == true)
        #expect(capture.opened.first?.hasSuffix("launch.command") == true)
    }

    @Test func terminalOpenFailureIsSurfacedAsLaunchFailed() async {
        let dispatcher = AgentHandoffDispatcher(
            fileExists: { _ in true },
            openTerminal: { _ in false },
            createDirectory: { _ in },
            writeFile: { _, _ in },
            makeExecutable: { _ in },
            temporaryDirectory: { FileManager.default.temporaryDirectory }
        )

        await #expect(throws: AgentHandoffDispatchError.launchFailed("Could not open Terminal")) {
            try await dispatcher.dispatch(
                context: Self.context, provider: .codex, launchMethod: .terminal,
                workingDirectory: "/tmp/work", promptTemplate: "Prompt"
            )
        }
    }
}

// MARK: - Coordinator

/// A simple counter for tests, letting success/failure be switched based on the call count.
private final class AttemptCounter: @unchecked Sendable {
    private(set) var value = 0
    func increment() -> Int {
        value += 1
        return value
    }
}

@MainActor
struct AgentHandoffCoordinatorTests {
    private static func terminalDispatcher(
        makeExecutable: @escaping (URL) throws -> Void = { _ in }
    ) -> AgentHandoffDispatcher {
        AgentHandoffDispatcher(
            fileExists: { _ in true },
            openTerminal: { _ in true },
            createDirectory: { _ in },
            writeFile: { _, _ in },
            makeExecutable: makeExecutable
        )
    }

    @Test func enqueueWithoutProviderDoesNothing() async throws {
        let coordinator = AgentHandoffCoordinator(dispatcher: AgentHandoffDispatcher())
        coordinator.enqueue(
            context: AgentHandoffContext(
                transcriptPath: "/tmp/session/transcript.md",
                sessionDirectory: "/tmp/session",
                meetingTitle: "朝会",
                counterpartName: ""
            ),
            settings: .empty
        )
        try await Task.sleep(for: .milliseconds(50))
        #expect(coordinator.state == .idle)
    }

    @Test func coordinatorRunsThenReportsSuccess() async throws {
        let coordinator = AgentHandoffCoordinator(dispatcher: Self.terminalDispatcher())
        var settings = AgentHandoffSettings.empty
        settings.provider = .claudeCode
        settings.launchMethod = .terminal
        settings.workingDirectory = "/tmp/work"

        coordinator.enqueue(
            context: AgentHandoffContext(
                transcriptPath: "/tmp/2026-09-25_1000_朝会/transcript.md",
                sessionDirectory: "/tmp/2026-09-25_1000_朝会",
                meetingTitle: "朝会",
                counterpartName: ""
            ),
            settings: settings
        )

        try await waitUntil {
            coordinator.state == .succeeded(label: "2026-09-25_1000_朝会", provider: .claudeCode, launchMethod: .terminal)
        }
        #expect(!coordinator.canRetry)
    }

    @Test func coordinatorCanRetryAfterFailure() async throws {
        let attempts = AttemptCounter()
        let dispatcher = Self.terminalDispatcher(makeExecutable: { _ in
            if attempts.increment() == 1 {
                throw NSError(domain: "test", code: 1)
            }
        })
        let coordinator = AgentHandoffCoordinator(dispatcher: dispatcher)
        var settings = AgentHandoffSettings.empty
        settings.provider = .codex
        settings.launchMethod = .terminal
        settings.workingDirectory = "/tmp/retry-work"
        let context = AgentHandoffContext(
            transcriptPath: "/tmp/retry-session/transcript.md",
            sessionDirectory: "/tmp/retry-session",
            meetingTitle: "朝会",
            counterpartName: ""
        )

        coordinator.enqueue(context: context, settings: settings)
        try await waitUntil { coordinator.canRetry }

        coordinator.retryFailed()
        try await waitUntil {
            coordinator.state == .succeeded(label: "retry-session", provider: .codex, launchMethod: .terminal)
        }
    }
}

@MainActor
private func waitUntil(
    timeout: Duration = .seconds(2),
    condition: () -> Bool
) async throws {
    let clock = ContinuousClock()
    let deadline = clock.now.advanced(by: timeout)
    while !condition() {
        guard clock.now < deadline else {
            throw AgentHandoffTestWaitError.timedOut
        }
        try await Task.sleep(for: .milliseconds(10))
    }
}

private enum AgentHandoffTestWaitError: Error {
    case timedOut
}
