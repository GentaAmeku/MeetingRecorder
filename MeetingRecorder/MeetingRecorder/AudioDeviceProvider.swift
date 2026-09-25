//
//  AudioDeviceProvider.swift
//  MeetingRecorder
//
//  Enumerates input devices and resolves the selection.
//  The selected device's uniqueID flows to CaptureEngine ->
//  SCStreamConfiguration.microphoneCaptureDeviceID.
//

import AVFoundation

struct AudioInputDevice: Identifiable, Equatable, Hashable {
    let id: String   // AVCaptureDevice.uniqueID
    let name: String
}

enum AudioDeviceProvider {
    /// Enumerates available audio input devices.
    static func availableInputDevices() -> [AudioInputDevice] {
        let session = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.microphone, .external],
            mediaType: .audio,
            position: .unspecified
        )
        return session.devices.map { AudioInputDevice(id: $0.uniqueID, name: $0.localizedName) }
    }

    /// Resolves the saved selection ID against the current device list.
    /// Returns that ID if it's still present, otherwise nil (= system default). Pure logic / unit-tested.
    static func resolveSelection(savedID: String?, available: [AudioInputDevice]) -> String? {
        guard let savedID, available.contains(where: { $0.id == savedID }) else { return nil }
        return savedID
    }

    /// Looks up a device name from its uniqueID (for metadata). Falls back to the system default input's name.
    static func deviceName(for id: String?, available: [AudioInputDevice]) -> String {
        if let id, let device = available.first(where: { $0.id == id }) {
            return device.name
        }
        return AVCaptureDevice.default(for: .audio)?.localizedName ?? "Unknown"
    }
}
