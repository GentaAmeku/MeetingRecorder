import Foundation
import Testing
@testable import MeetingRecorder

struct MeetingLaunchRequestTests {
    @Test func parsesMeetingPreparationURL() throws {
        let url = try #require(URL(string:
            "meetingrecorder://prepare?title=%E9%80%B1%E6%AC%A1%E7%A2%BA%E8%AA%8D&counterpart=%E5%8F%82%E5%8A%A0%E8%80%85A&join=https%3A%2F%2Fmeet.google.com%2Fabc-defg-hij"
        ))

        let request = try MeetingLaunchRequest(url: url)

        #expect(request.title == "週次確認")
        #expect(request.counterpartName == "参加者A")
    }

    @Test func rejectsUntrustedOrAmbiguousURLs() throws {
        let wrongScheme = try #require(URL(string:
            "https://prepare?title=Test&join=https%3A%2F%2Fmeet.google.com%2Fabc-defg-hij"
        ))
        let duplicateTitle = try #require(URL(string:
            "meetingrecorder://prepare?title=First&title=Second&join=https%3A%2F%2Fmeet.google.com%2Fabc-defg-hij"
        ))
        let untrustedJoin = try #require(URL(string:
            "meetingrecorder://prepare?title=Test&join=https%3A%2F%2Fexample.com%2Froom"
        ))

        #expect(throws: MeetingLaunchRequestError.invalidURL) {
            _ = try MeetingLaunchRequest(url: wrongScheme)
        }
        #expect(throws: MeetingLaunchRequestError.ambiguousQuery) {
            _ = try MeetingLaunchRequest(url: duplicateTitle)
        }
        #expect(throws: MeetingLaunchRequestError.invalidJoinURL) {
            _ = try MeetingLaunchRequest(url: untrustedJoin)
        }
    }

    @Test func normalizesNamesAndRejectsUnknownQueryItems() throws {
        let normalized = try #require(URL(string:
            "meetingrecorder://prepare?title=%20%20%E7%A2%BA%E8%AA%8D%E4%BC%9A%20%20&counterpart=%20%E5%8F%82%E5%8A%A0%E8%80%85A%0A&join=https%3A%2F%2Fmeet.google.com%2Fabc-defg-hij"
        ))
        let unknownQuery = try #require(URL(string:
            "meetingrecorder://prepare?title=Test&join=https%3A%2F%2Fmeet.google.com%2Fabc-defg-hij&notes=private"
        ))

        let request = try MeetingLaunchRequest(url: normalized)

        #expect(request.title == "確認会")
        #expect(request.counterpartName == "参加者A")
        #expect(throws: MeetingLaunchRequestError.invalidURL) {
            _ = try MeetingLaunchRequest(url: unknownQuery)
        }
    }

    @Test func rejectsPreparationURLWithUnexpectedAuthorityOrPath() throws {
        let urls = try [
            "meetingrecorder://prepare/extra?title=Test&join=https%3A%2F%2Fmeet.google.com%2Fabc-defg-hij",
            "meetingrecorder://prepare:8443?title=Test&join=https%3A%2F%2Fmeet.google.com%2Fabc-defg-hij",
            "meetingrecorder://user@prepare?title=Test&join=https%3A%2F%2Fmeet.google.com%2Fabc-defg-hij",
            "meetingrecorder://prepare?title=Test&join=https%3A%2F%2Fmeet.google.com%2Fabc-defg-hij#extra"
        ].map { try #require(URL(string: $0)) }

        for url in urls {
            #expect(throws: MeetingLaunchRequestError.invalidURL) {
                _ = try MeetingLaunchRequest(url: url)
            }
        }
    }

    @Test func rejectsGoogleMeetURLWithUnexpectedAuthority() throws {
        let joinURLs = try [
            "https://user@meet.google.com/abc-defg-hij",
            "https://meet.google.com:8443/abc-defg-hij"
        ].map { try #require(URL(string: $0)) }

        for joinURL in joinURLs {
            var components = URLComponents()
            components.scheme = "meetingrecorder"
            components.host = "prepare"
            components.queryItems = [
                URLQueryItem(name: "title", value: "Test"),
                URLQueryItem(name: "join", value: joinURL.absoluteString)
            ]
            let url = try #require(components.url)

            #expect(throws: MeetingLaunchRequestError.invalidJoinURL) {
                _ = try MeetingLaunchRequest(url: url)
            }
        }
    }
}
