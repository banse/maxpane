#!/usr/bin/env bash
# Start the local Boardroom with the Matrix theme.
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec .venv/bin/python -m maxpane_dashboard --game surfboard --theme matrix "$@"
