#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"
APP_BUILD="$ROOT/.app-build"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Run scripts/install_macos.sh first."
  exit 1
fi

# py2app 0.28.9+ rejects install_requires and does not support editable installs.
# Install the runtime package normally, then run a minimal setup_app.py from an
# isolated directory that has no pyproject.toml beside it.
"$VENV/bin/python" -m pip install --upgrade \
  "py2app>=0.28.10" \
  "pyobjc-framework-CoreLocation>=10.3" \
  "pyobjc-framework-Cocoa>=10.3" \
  "rumps>=0.4.0"
"$VENV/bin/python" -m pip uninstall -y tj-nearby >/dev/null 2>&1 || true
"$VENV/bin/python" -m pip install --no-deps "$ROOT"

rm -rf "$APP_BUILD" "$ROOT/build" "$ROOT/dist"
mkdir -p "$APP_BUILD"
cp "$ROOT/macos_app.py" "$ROOT/setup_app.py" "$APP_BUILD/"

cd "$APP_BUILD"
"$VENV/bin/python" setup_app.py py2app

if [[ ! -d "$APP_BUILD/dist/TJ Nearby.app" ]]; then
  echo "py2app did not produce $APP_BUILD/dist/TJ Nearby.app"
  exit 1
fi

mv "$APP_BUILD/dist" "$ROOT/dist"
mv "$APP_BUILD/build" "$ROOT/build"
APP="$ROOT/dist/TJ Nearby.app"

/usr/bin/plutil -lint "$APP/Contents/Info.plist"
/usr/bin/plutil -p "$APP/Contents/Info.plist" | grep -q "NSLocationUsageDescription"

# Catch incomplete bundles before the automatic installer signs/copies them.
if [[ ! -x "$APP/Contents/MacOS/TJ Nearby" ]]; then
  echo "Built app is missing its executable."
  exit 1
fi

echo "Built: $APP"
echo "The automatic installer will sign it locally and copy it to /Applications."
