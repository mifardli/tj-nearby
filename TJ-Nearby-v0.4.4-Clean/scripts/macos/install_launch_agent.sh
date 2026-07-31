#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="$HOME/.tj-nearby"
APP_PATH_FILE="$STATE_DIR/app_path"
LABEL="id.miftahulardli.tjnearby.launcher"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$STATE_DIR/logs"

if [[ -f "$APP_PATH_FILE" ]]; then
  APP_PATH="$(cat "$APP_PATH_FILE")"
elif [[ -d "/Applications/TJ Nearby.app" ]]; then
  APP_PATH="/Applications/TJ Nearby.app"
elif [[ -d "$HOME/Applications/TJ Nearby.app" ]]; then
  APP_PATH="$HOME/Applications/TJ Nearby.app"
else
  echo "TJ Nearby.app is not installed."
  echo "Run scripts/install_automatic_macos.sh first."
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/open</string>
    <string>$APP_PATH</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>$LOG_DIR/launcher-stdout.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/launcher-stderr.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "TJ Nearby will open automatically at login."
echo "App: $APP_PATH"
echo "LaunchAgent: $PLIST"
