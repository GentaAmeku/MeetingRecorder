//
//  MeetingRecorderUITestsLaunchTests.swift
//  MeetingRecorderUITests
//

import XCTest

final class MeetingRecorderUITestsLaunchTests: XCTestCase {

    /// The Xcode template default is true, running the launch test in both light and dark.
    /// Switching it flips the whole Mac's appearance setting, which doesn't revert after the test ends.
    /// Not worth that just for two launch screenshots, so this is false.
    override class var runsForEachTargetApplicationUIConfiguration: Bool {
        false
    }

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    @MainActor
    func testLaunch() throws {
        let app = XCUIApplication()
        app.launch()

        // Insert steps here to perform after app launch but before taking a screenshot,
        // such as logging into a test account or navigating somewhere in the app
        // XCUIAutomation Documentation
        // https://developer.apple.com/documentation/xcuiautomation

        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Launch Screen"
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
