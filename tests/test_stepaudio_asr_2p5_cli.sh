#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_PATH="$REPO_ROOT/skills/stepaudio-asr-2p5/scripts/transcribe.py"

echo "[test] stepaudio-asr-2p5 transcribe.py --help"
python3 "$SCRIPT_PATH" --help >/dev/null

echo "stepaudio-asr-2p5 CLI help test passed."
