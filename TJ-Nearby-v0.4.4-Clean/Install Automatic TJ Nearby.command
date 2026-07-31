#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
chmod +x scripts/*.sh *.command
./scripts/install_automatic_macos.sh
printf '\nInstaller finished. Look for the bus icon in the menu bar.\n'
read -n 1 -s -r -p "Press any key to close"
echo
