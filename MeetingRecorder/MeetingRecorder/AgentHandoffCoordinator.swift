//
//  AgentHandoffCoordinator.swift
//  MeetingRecorder
//
//  Manages sending to the AI agent on a serial queue separate from transcription.
//

import Foundation
import Observation
import UserNotifications

enum AgentHandoffState: Equatable {
    case idle
    case running(label: String, provider: AgentHandoffProvider)
    case succeeded(label: String, provider: AgentHandoffProvider, launchMethod: AgentHandoffLaunchMethod)
    case failed(label: String, message: String)
}

private struct AgentHandoffJob {
    let context: AgentHandoffContext
    let provider: AgentHandoffProvider
    let launchMethod: AgentHandoffLaunchMethod
    let workingDirectory: String
    let promptTemplate: String
}

@MainActor
@Observable
final class AgentHandoffCoordinator {
    private(set) var state: AgentHandoffState = .idle

    /// Whether the last failed send can be retried with the same session and settings.
    var canRetry: Bool {
        guard case .failed = state else { return false }
        return failedJob != nil && !isDraining
    }

    private let dispatcher: AgentHandoffDispatcher
    private var queue: [AgentHandoffJob] = []
    private var isDraining = false
    private var failedJob: AgentHandoffJob?

    init(dispatcher: AgentHandoffDispatcher = AgentHandoffDispatcher()) {
        self.dispatcher = dispatcher
    }

    /// Does nothing when the target is "none" (double-guarded together with the caller's AgentHandoffPolicy).
    func enqueue(context: AgentHandoffContext, settings: AgentHandoffSettings) {
        guard let provider = settings.provider else { return }
        queue.append(AgentHandoffJob(
            context: context,
            provider: provider,
            launchMethod: settings.launchMethod,
            workingDirectory: settings.workingDirectory,
            promptTemplate: settings.promptTemplate
        ))
        Task { await drain() }
    }

    /// Re-enqueues the last failed job with the same content.
    func retryFailed() {
        guard !isDraining, let job = failedJob else { return }
        failedJob = nil
        queue.insert(job, at: 0)
        Task { await drain() }
    }

    private func drain() async {
        guard !isDraining else { return }
        isDraining = true
        defer { isDraining = false }

        while !queue.isEmpty {
            let job = queue.removeFirst()
            let label = URL(fileURLWithPath: job.context.sessionDirectory).lastPathComponent
            state = .running(label: label, provider: job.provider)
            do {
                try await dispatcher.dispatch(
                    context: job.context,
                    provider: job.provider,
                    launchMethod: job.launchMethod,
                    workingDirectory: job.workingDirectory,
                    promptTemplate: job.promptTemplate
                )
                state = .succeeded(label: label, provider: job.provider, launchMethod: job.launchMethod)
                notify(title: AgentHandoffState.successText(provider: job.provider, launchMethod: job.launchMethod), body: label)
            } catch {
                failedJob = job
                state = .failed(label: label, message: error.localizedDescription)
                notify(title: "Failed to send to the AI agent", body: error.localizedDescription)
            }
        }
    }

    private func notify(title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )
        UNUserNotificationCenter.current().add(request)
    }
}

extension AgentHandoffState {
    /// Orca confirms the prompt was actually sent. Terminal only confirms it was opened.
    static func successText(provider: AgentHandoffProvider, launchMethod: AgentHandoffLaunchMethod) -> String {
        switch launchMethod {
        case .orca: return "Sent to \(provider.displayName)"
        case .terminal: return "Opened \(provider.displayName) in Terminal"
        }
    }
}
