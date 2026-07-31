#!/usr/bin/env bash
set -e
APP_PATH_FILE="$HOME/.tj-nearby/app_path"
if [[ -f "$APP_PATH_FILE" ]]; then
  APP_PATH="$(cat "$APP_PATH_FILE")"
elif [[ -d "/Applications/TJ Nearby.app" ]]; then
  APP_PATH="/Applications/TJ Nearby.app"
elif [[ -d "$HOME/Applications/TJ Nearby.app" ]]; then
  APP_PATH="$HOME/Applications/TJ Nearby.app"
else
  echo "TJ Nearby.app is not installed. Run Install TJ Nearby.command first."
  read -n 1 -s -r -p "Press any key to close"
  exit 1
fi
/usr/bin/open "$APP_PATH"
echo "TJ Nearby opened. Look for the bus icon in the menu bar."
