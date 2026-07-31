#!/usr/bin/env bash
set -e
APP_PATH_FILE="$HOME/.tj-nearby/app_path"
if [[ -f "$APP_PATH_FILE" ]]; then
  /usr/bin/open "$(cat "$APP_PATH_FILE")"
else
  /usr/bin/open -a "TJ Nearby" || true
fi
echo "Click the bus icon, choose Check now, then Export app diagnostic."
read -n 1 -s -r -p "Press any key to close"
echo
