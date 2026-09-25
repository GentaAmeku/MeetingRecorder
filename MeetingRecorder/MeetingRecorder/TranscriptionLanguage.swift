//
//  TranscriptionLanguage.swift
//  MeetingRecorder
//
//  The transcription language shown in Settings and written to
//  postprocess-config.json's transcript.language. Kept to a small set of
//  choices in the UI; the postprocess CLI itself accepts "auto" or any
//  Whisper language code.
//

import Foundation

nonisolated enum TranscriptionLanguage: String, CaseIterable, Identifiable, Sendable {
    case auto
    case english = "en"
    case japanese = "ja"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .auto: return "Auto-detect"
        case .english: return "English"
        case .japanese: return "Japanese"
        }
    }
}
