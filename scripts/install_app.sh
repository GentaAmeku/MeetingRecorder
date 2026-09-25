#!/usr/bin/env bash
#
# Builds MeetingRecorder in Release configuration and installs it to /Applications.
#
#   scripts/install_app.sh
#
# Signing stays as the existing automatic Apple Development signing (not
# notarized). Because the bundle id + Team stay stable, TCC permissions
# (microphone/screen recording/Documents) survive moving to /Applications and
# reinstalling. Day to day, launch it from Launchpad/Spotlight; after
# changing the code, just re-run this script (no need to Run from Xcode).
#
# For the postprocess CLI, this script runs `uv sync --frozen` in
# postprocess/, then passes the resulting postprocess/.venv/bin/postprocess
# absolute path to the build as the POSTPROCESS_CLI_PATH build setting. The
# app only reads that value via Info.plist (CLILocator.swift); no personal
# real path is ever written into the repository.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJ="$REPO_ROOT/MeetingRecorder/MeetingRecorder.xcodeproj"
DERIVED="$REPO_ROOT/MeetingRecorder/build"
APP_NAME="MeetingRecorder.app"
APP_PATH="$DERIVED/Build/Products/Release/$APP_NAME"
DEST="/Applications/$APP_NAME"
POSTPROCESS_DIR="$REPO_ROOT/postprocess"
POSTPROCESS_CLI="$POSTPROCESS_DIR/.venv/bin/postprocess"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv was not found. See https://docs.astral.sh/uv/ for install instructions." >&2
  exit 1
fi

echo "==> Syncing postprocess dependencies (uv sync --frozen)…"
(cd "$POSTPROCESS_DIR" && uv sync --frozen)

[ -x "$POSTPROCESS_CLI" ] || {
  echo "postprocess CLI not found: $POSTPROCESS_CLI" >&2
  exit 1
}

echo "==> Building Release…"
xcodebuild build \
  -project "$PROJ" \
  -scheme MeetingRecorder \
  -configuration Release \
  -derivedDataPath "$DERIVED" \
  -destination 'platform=macOS' \
  "POSTPROCESS_CLI_PATH=$POSTPROCESS_CLI" \
  >/dev/null

[ -d "$APP_PATH" ] || { echo "Build product not found: $APP_PATH" >&2; exit 1; }

echo "==> Installing to /Applications…"
if [ -w /Applications ]; then
  rm -rf "$DEST"
  cp -R "$APP_PATH" "$DEST"
else
  echo "   (administrator privileges required — will prompt for sudo)"
  sudo rm -rf "$DEST"
  sudo cp -R "$APP_PATH" "$DEST"
fi

echo "==> Done: $DEST"
echo "   Launch it from Launchpad/Spotlight by searching 'MeetingRecorder'."
