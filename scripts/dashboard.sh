#!/usr/bin/env bash
# Start the MaxPane dashboard (no intro sequence)
# Usage: ./scripts/dashboard.sh [--game bakery|frenpet|base|cattown] [--theme matrix|minimal|...]

set -euo pipefail
cd "$(dirname "$0")/.."

PIDFILE="data/maxpane.pid"
mkdir -p data

# Check if already running
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "MaxPane is already running (PID $(cat "$PIDFILE"))"
    echo "Use ./scripts/stop.sh to stop it first."
    exit 1
fi

# Activate venv
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "Error: .venv not found. Run: python3.11 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

# Clean terminal for TUI
if [[ "${TERM_PROGRAM:-}" == "iTerm.app" ]]; then
    printf '\e]1337;SetScrollbar=false\a'
fi
printf '\e[3J\e[H\e[2J'

# Launch the Textual dashboard directly (skip Rust intro)
echo $$ > "$PIDFILE"
exec python -m dashboard "$@"
