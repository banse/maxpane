#!/usr/bin/env bash
# Launch MaxPane maximized in the current terminal window.
# Usage: ./scripts/launch-maximized.sh [--game base|frenpet|cattown|ocm|bakery] [--theme matrix|...]

set -euo pipefail
cd "$(dirname "$0")/.."

# Python owns terminal setup and the first-run native intro.
exec ./scripts/start.sh "$@"
