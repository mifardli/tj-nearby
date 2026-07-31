#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_SOURCE="$ROOT/dist/TJ Nearby.app"
STATE_DIR="$HOME/.tj-nearby"
LOG="$HOME/Desktop/tj-nearby-v040-install.txt"

exec > >(tee "$LOG") 2>&1

echo "=== TJ Nearby v0.4.4 automatic installer ==="
echo "Project: $ROOT"

"$ROOT/scripts/install_macos.sh"
"$ROOT/.venv/bin/tj-nearby" location-auto
"$ROOT/.venv/bin/tj-nearby" notification-ready-window
"$ROOT/scripts/build_app.sh"

if [[ ! -d "$APP_SOURCE" ]]; then
  echo "Build failed: $APP_SOURCE not found"
  exit 1
fi

/usr/bin/codesign --force --deep --sign - "$APP_SOURCE"
/usr/bin/xattr -dr com.apple.quarantine "$APP_SOURCE" 2>/dev/null || true

if [[ -w "/Applications" ]]; then
  APP_DEST="/Applications/TJ Nearby.app"
else
  mkdir -p "$HOME/Applications"
  APP_DEST="$HOME/Applications/TJ Nearby.app"
fi

rm -rf "$APP_DEST"
/usr/bin/ditto "$APP_SOURCE" "$APP_DEST"
/usr/bin/codesign --verify --deep --strict "$APP_DEST"
mkdir -p "$STATE_DIR"
printf '%s\n' "$APP_DEST" > "$STATE_DIR/app_path"

"$ROOT/scripts/install_launch_agent.sh"

echo
echo "Installed: $APP_DEST"
echo "Config: $STATE_DIR/config.yaml"
echo "Log: $LOG"
echo
echo "Opening TJ Nearby. Click Allow when macOS asks for location access."
/usr/bin/open "$APP_DEST"
