//
//  MeetingPreparationCoordinator.swift
//  MeetingRecorder
//
//  Manages whether meeting info received from OnCue can be applied, and shows a notice about it.
//

import Observation

enum MeetingPreparationReception: Equatable {
    case prepared
    case busy
}

@MainActor
@Observable
final class MeetingPreparationCoordinator {
    private(set) var notice: String?

    func prepare(for recordingState: RecordingState) -> MeetingPreparationReception {
        if case .recording = recordingState {
            notice = "Already recording another meeting, so the meeting info was not changed."
            return .busy
        }
        if case .finalizing = recordingState {
            notice = "Currently saving the recording, so the meeting info was not changed."
            return .busy
        }

        notice = "Meeting info filled in. Ready to record."
        return .prepared
    }

    func dismissNotice() {
        notice = nil
    }

    func recordingWillStart() {
        notice = nil
    }

    func rejectInvalidRequest() {
        notice = "Could not verify the meeting info received from OnCue."
    }
}
