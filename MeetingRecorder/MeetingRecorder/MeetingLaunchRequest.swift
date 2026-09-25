//
//  MeetingLaunchRequest.swift
//  MeetingRecorder
//
//  Validates the meetingrecorder://prepare custom URL passed in from OnCue,
//  and converts it into meeting info (title / counterpart name). Anything
//  that doesn't match the trusted shape is rejected.
//

import Foundation

enum MeetingLaunchRequestError: Error, Equatable {
    case invalidURL
    case ambiguousQuery
    case missingTitle
    case missingJoinURL
    case invalidJoinURL
}

struct MeetingLaunchRequest: Equatable, Sendable {
    let title: String
    let counterpartName: String

    init(url: URL) throws {
        guard url.scheme?.lowercased() == "meetingrecorder",
              url.host()?.lowercased() == "prepare",
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            throw MeetingLaunchRequestError.invalidURL
        }
        guard components.path.isEmpty,
              components.port == nil,
              components.user == nil,
              components.password == nil,
              components.fragment == nil else {
            throw MeetingLaunchRequestError.invalidURL
        }

        let items = components.queryItems ?? []
        let allowedNames: Set<String> = ["title", "counterpart", "join"]
        guard items.allSatisfy({ allowedNames.contains($0.name) }) else {
            throw MeetingLaunchRequestError.invalidURL
        }
        let groupedItems = Dictionary(grouping: items, by: \.name)
        guard groupedItems.values.allSatisfy({ $0.count == 1 }) else {
            throw MeetingLaunchRequestError.ambiguousQuery
        }
        guard let title = items.first(where: { $0.name == "title" })?.value,
              title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false else {
            throw MeetingLaunchRequestError.missingTitle
        }
        guard let joinValue = items.first(where: { $0.name == "join" })?.value,
              let joinURL = URL(string: joinValue),
              let joinComponents = URLComponents(url: joinURL, resolvingAgainstBaseURL: false) else {
            throw MeetingLaunchRequestError.missingJoinURL
        }
        guard joinComponents.scheme?.lowercased() == "https",
              joinComponents.host?.lowercased() == "meet.google.com",
              joinComponents.path.split(separator: "/").isEmpty == false,
              joinComponents.port == nil,
              joinComponents.user == nil,
              joinComponents.password == nil else {
            throw MeetingLaunchRequestError.invalidJoinURL
        }

        self.title = RecordingSession.normalizedTitle(title)
        self.counterpartName = RecordingSession.normalizedCounterpart(
            items.first(where: { $0.name == "counterpart" })?.value ?? ""
        )
    }
}
