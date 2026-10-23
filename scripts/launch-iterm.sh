#!/usr/bin/env bash
# Launch MaxPane fullscreen in iTerm2 (current window).
# Usage: ./scripts/launch-iterm.sh [--game base|frenpet|cattown|ocm|bakery] [--theme matrix|...]

set -euo pipefail
cd "$(dirname "$0")/.."

# Python owns terminal setup and the first-run native intro.
exec ./scripts/start.sh "$@"
