//
//  CLILocator.swift
//  MeetingRecorder
//
//  Resolves the location of the postprocess CLI. Normally
//  scripts/install_app.sh bakes the absolute path of
//  postprocess/.venv/bin/postprocess into Info.plist via the
//  POSTPROCESS_CLI_PATH build setting, and this reads it from there (never
//  rewritten after signing). As a development escape hatch this also checks
//  a UserDefaults override, but that is never exposed in the UI.
//

import Foundation

enum CLILocator {
    static let overrideKey = "postprocessCLIPathOverride"
    private static let infoPlistKey = "PostprocessCLIPath"

    /// Development override (UserDefaults, never shown in the UI). nil when unset.
    static var overridePath: String? {
        get { UserDefaults.standard.string(forKey: overrideKey) }
        set { UserDefaults.standard.set(newValue, forKey: overrideKey) }
    }

    /// The absolute path scripts/install_app.sh embeds into Info.plist at build time. nil when unset.
    private static var infoPlistPath: String? {
        Bundle.main.object(forInfoDictionaryKey: infoPlistKey) as? String
    }

    /// Resolution order: the UserDefaults development override, then Info.plist (set at install time).
    /// A candidate that isn't executable is skipped (so a stale override never blocks the automatic path).
    /// Returns nil if neither is executable.
    static var resolvedURL: URL? {
        for candidate in [overridePath, infoPlistPath] {
            guard let path = candidate?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !path.isEmpty
            else { continue }
            let url = URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
            if FileManager.default.isExecutableFile(atPath: url.path) { return url }
        }
        return nil
    }

    /// Whether the resolved path exists as an executable file. false when unset.
    static var isAvailable: Bool {
        guard let resolvedURL else { return false }
        return FileManager.default.isExecutableFile(atPath: resolvedURL.path)
    }
}
