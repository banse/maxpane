#!/usr/bin/env bash
# Launch MaxPane fullscreen in the current terminal window.
# Usage: ./scripts/launch.sh [--game base|frenpet|cattown|ocm|bakery] [--theme matrix|...]

set -euo pipefail
cd "$(dirname "$0")/.."

# Maximize current window first
if [[ "$TERM_PROGRAM" == "iTerm.app" ]]; then
    # iTerm2: use escape sequence to toggle fullscreen
    printf '\e]1337;SetFullscreen=true\a'
else
    # Terminal.app: resize via tput/escape sequences
    printf '\e[9;1t'
fi

# Small delay to let fullscreen transition complete
sleep 0.5

# Run the dashboard in this terminal
exec ./scripts/start.sh "$@"
