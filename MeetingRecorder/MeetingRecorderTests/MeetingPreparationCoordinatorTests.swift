import Testing
@testable import MeetingRecorder

struct MeetingPreparationCoordinatorTests {
    @Test @MainActor func idleReceptionPreparesMeetingContextWithoutOwningJoin() {
        let coordinator = MeetingPreparationCoordinator()

        let reception = coordinator.prepare(for: .idle)

        #expect(reception == .prepared)
        #expect(coordinator.notice == "Meeting info filled in. Ready to record.")
    }

    @Test @MainActor func busyRecordingKeepsItsContextAndLeavesJoinToOnCue() {
        let coordinator = MeetingPreparationCoordinator()

        let reception = coordinator.prepare(for: .recording)

        #expect(reception == .busy)
        #expect(coordinator.notice == "Already recording another meeting, so the meeting info was not changed.")
    }

    @Test @MainActor func finalizingRecordingKeepsItsContextAndLeavesJoinToOnCue() {
        let coordinator = MeetingPreparationCoordinator()

        let reception = coordinator.prepare(for: .finalizing)

        #expect(reception == .busy)
        #expect(coordinator.notice == "Currently saving the recording, so the meeting info was not changed.")
    }

    @Test @MainActor func noticeCanBeDismissedWithoutChangingRecording() {
        let coordinator = MeetingPreparationCoordinator()
        _ = coordinator.prepare(for: .idle)

        coordinator.dismissNotice()

        #expect(coordinator.notice == nil)
    }

    @Test @MainActor func startingRecordingClearsPreparationNotice() {
        let coordinator = MeetingPreparationCoordinator()
        _ = coordinator.prepare(for: .idle)

        coordinator.recordingWillStart()

        #expect(coordinator.notice == nil)
    }
}
