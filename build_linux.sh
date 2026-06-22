#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -d venv ]]; then
    python3 -m venv venv
fi

source "$ROOT_DIR/venv/bin/activate"

python -m pip install --upgrade pip
if [[ -f requirements.txt ]]; then
    python -m pip install -r requirements.txt
fi
python -m pip install pyinstaller pillow
python scripts/generate_icons.py

python -m PyInstaller AmlogicFlashTool.spec     --noconfirm     --clean

echo "Build complete"
