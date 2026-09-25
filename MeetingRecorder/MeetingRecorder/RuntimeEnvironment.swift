//
//  RuntimeEnvironment.swift
//  MeetingRecorder
//
//  Unit tests run with MeetingRecorderTests hosting the main app (Xcode's
//  "Host Application" setting). Running launch-time work that can block on
//  user interaction as-is — requesting notification authorization, first
//  access to the Documents folder, etc. — would hang in that headless
//  environment before the test runner even connects, since nobody is there
//  to dismiss the dialog. This flag is checked before calling such work, to skip it.
//

import Foundation

enum RuntimeEnvironment {
    /// Whether running inside an XCTest host (i.e. during unit/UI tests).
    static var isRunningTests: Bool {
        ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
    }
}
