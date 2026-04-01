#!/usr/bin/env bash
# Launch MaxPane maximized in the current terminal window.
# Usage: ./scripts/launch-maximized.sh [--game base|frenpet|cattown|ocm|bakery] [--theme matrix|...]

set -euo pipefail
cd "$(dirname "$0")/.."

# Maximize current window
if [[ "$TERM_PROGRAM" == "iTerm.app" ]]; then
    printf '\e]1337;SetFullscreen=true\a'
else
    printf '\e[9;1t'
fi

sleep 0.5

exec ./scripts/start.sh "$@"
