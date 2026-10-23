#!/usr/bin/env bash
# Start the MaxPane dashboard
# Usage: ./scripts/start.sh [--game surfboard] [--intro] [--theme matrix|minimal|...]

set -euo pipefail
cd "$(dirname "$0")/.."

# Activate venv
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "Error: .venv not found. Run: python3.11 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

# Let argparse handle informational flags before touching the terminal or PID.
for arg in "$@"; do
    case "$arg" in
        --help|-h|--version|-V) exec python -m maxpane_dashboard "$@" ;;
    esac
done

PIDFILE="data/maxpane.pid"
mkdir -p data
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "MaxPane is already running (PID $(cat "$PIDFILE"))"
    echo "Use ./scripts/stop.sh to stop it first."
    exit 1
fi

# Launch the Textual dashboard in the foreground so it has full
# terminal access (stdin/stdout).  The & + wait pattern redirects
# stdin from /dev/null in non-interactive bash, which starves Textual
# of keyboard input.
# Clean terminal for TUI: hide scrollbar (iTerm2) or clear scrollback (Terminal.app)
if [[ "${TERM_PROGRAM:-}" == "iTerm.app" ]]; then
    printf '\e]1337;SetScrollbar=false\a'
fi
printf '\e[3J\e[H\e[2J'

echo $$ > "$PIDFILE"
exec python -m maxpane_dashboard "$@"
