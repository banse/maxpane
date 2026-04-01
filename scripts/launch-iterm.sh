#!/usr/bin/env bash
# Launch MaxPane fullscreen in iTerm2 (current window).
# Usage: ./scripts/launch-iterm.sh [--game base|frenpet|cattown|ocm|bakery] [--theme matrix|...]

set -euo pipefail
cd "$(dirname "$0")/.."

# iTerm2 proprietary escape sequence for fullscreen
printf '\e]1337;SetFullscreen=true\a'
sleep 0.5

exec ./scripts/start.sh "$@"
