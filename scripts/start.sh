#!/usr/bin/env bash
# Start the MaxPane dashboard
# Usage: ./scripts/start.sh [--game bakery|frenpet|base] [--theme matrix|minimal|...]

set -euo pipefail
cd "$(dirname "$0")/.."

PIDFILE="data/maxpane.pid"
LOGFILE="data/maxpane.log"
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

# Build the Rust intro if cargo is available and source exists
if [ -d "maxpane/src" ] && command -v cargo &>/dev/null; then
    if [ ! -f "maxpane/target/release/maxpane" ] || \
       [ "maxpane/src/main.rs" -nt "maxpane/target/release/maxpane" 2>/dev/null ]; then
        echo "Building MaxPane intro..."
        (cd maxpane && cargo build --release --quiet 2>/dev/null) || true
    fi
fi

# Run the Rust intro sequence first (if built)
if [ -f "maxpane/target/release/maxpane" ]; then
    ./maxpane/target/release/maxpane
    # Reset terminal to clean state after Rust intro.
    # crossterm's restore_terminal can leave residual mode bits on macOS
    # that break Textual's own terminal setup.
    stty sane 2>/dev/null || true
    export MAXPANE_INTRO_SHOWN=1
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
