#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="$HOME/.tj-nearby"
VENV="$ROOT/.venv"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install Python 3.11+ first."
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required")
PY

mkdir -p "$STATE_DIR"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV/bin/python" -m pip install -e "$ROOT[mac]"

if [[ ! -f "$STATE_DIR/config.yaml" ]]; then
  cp "$ROOT/config.example.yaml" "$STATE_DIR/config.yaml"
  echo "Created $STATE_DIR/config.yaml"
else
  # Add new v0.3.4 keys without replacing any existing user value.
  "$VENV/bin/python" - "$ROOT/config.example.yaml" "$STATE_DIR/config.yaml" <<'PY_MIGRATE'
from pathlib import Path
import sys
import yaml

example_path = Path(sys.argv[1])
config_path = Path(sys.argv[2])
defaults = yaml.safe_load(example_path.read_text(encoding="utf-8")) or {}
current = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def merge_missing(target, source):
    changed = False
    for key, value in source.items():
        if key not in target:
            target[key] = value
            changed = True
        elif isinstance(target[key], dict) and isinstance(value, dict):
            changed = merge_missing(target[key], value) or changed
    return changed


if merge_missing(current, defaults):
    config_path.write_text(
        yaml.safe_dump(current, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"Migrated missing configuration keys in {config_path}")
else:
    print(f"Configuration already current: {config_path}")
PY_MIGRATE
fi

"$VENV/bin/tj-nearby" --config "$STATE_DIR/config.yaml" bootstrap

echo
echo "Python environment ready."
echo "For automatic macOS location, continue with scripts/build_app.sh or use:"
echo "  $ROOT/scripts/install_automatic_macos.sh"
echo "Terminal doctor remains useful in manual-location mode."
