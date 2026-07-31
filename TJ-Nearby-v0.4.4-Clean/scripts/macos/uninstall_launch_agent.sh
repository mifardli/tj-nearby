#!/usr/bin/env bash
set -euo pipefail
LABEL="id.miftahulardli.tjnearby.launcher"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "TJ Nearby login launcher removed."
