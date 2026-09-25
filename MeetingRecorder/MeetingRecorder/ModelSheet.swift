//
//  ModelSheet.swift
//  MeetingRecorder
//
//  A dedicated sheet for the transcription models' status, download, delete
//  and re-download. A setup summary (CLI / whether each model is present) at
//  the top, then each model listed with its status, a % bar, and controls.
//  Downloads are owned by ModelCoordinator, so they keep running after the
//  sheet is closed.
//

import SwiftUI

struct ModelSheet: View {
    let coordinator: ModelCoordinator
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Models").font(.title2).bold()
                Spacer()
                Button("Close") { dismiss() }
            }

            setupSummary

            if !coordinator.cliAvailable {
                cliMissingNote
            }

            Divider()

            ForEach(coordinator.models) { model in
                modelRow(model)
                if model.id != coordinator.models.last?.id { Divider() }
            }

            Spacer(minLength: 0)
        }
        .padding(20)
        .frame(width: 420, height: 340)
        .task { await coordinator.refreshStatus() }
    }

    // MARK: - Setup summary

    private var setupSummary: some View {
        HStack(spacing: 14) {
            summaryChip("CLI", ok: coordinator.cliAvailable)
            ForEach(coordinator.models) { m in
                summaryChip(shortName(m.id), ok: m.state == .ready)
            }
        }
        .font(.caption)
    }

    private func summaryChip(_ label: String, ok: Bool) -> some View {
        HStack(spacing: 4) {
            Image(systemName: ok ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(ok ? .green : .secondary)
            Text(label)
        }
    }

    private func shortName(_ id: String) -> String {
        id == "whisper" ? "Whisper" : "Diarization"
    }

    private var cliMissingNote: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("postprocess CLI not found", systemImage: "exclamationmark.triangle.fill")
                .font(.callout).foregroundStyle(.orange)
            Text("Please reinstall with scripts/install_app.sh.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Model row

    @ViewBuilder
    private func modelRow(_ model: ModelCoordinator.Model) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(model.name).font(.callout)
                    Text(model.sizeLabel).font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                stateControl(model)
            }
            if case .downloading(let pct) = model.state {
                ProgressView(value: Double(pct), total: 100)
                    .progressViewStyle(.linear)
                Text("\(pct)%").font(.caption2).foregroundStyle(.secondary)
            }
            if case .error(let msg) = model.state {
                Text(msg).font(.caption2).foregroundStyle(.orange).lineLimit(2)
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func stateControl(_ model: ModelCoordinator.Model) -> some View {
        switch model.state {
        case .unknown:
            Text("Checking…").font(.caption).foregroundStyle(.secondary)
        case .missing:
            Button("Download") { coordinator.download(model.id) }
                .disabled(!coordinator.cliAvailable)
        case .downloading:
            Text("Downloading…").font(.caption).foregroundStyle(.blue)
        case .ready:
            HStack(spacing: 8) {
                Label("Downloaded", systemImage: "checkmark.circle.fill")
                    .font(.caption).foregroundStyle(.green)
                Button("Delete") { Task { await coordinator.delete(model.id) } }
                    .controlSize(.small)
            }
        case .error:
            Button("Retry Download") { coordinator.retry(model.id) }
                .disabled(!coordinator.cliAvailable)
        }
    }
}
