#!/usr/bin/env bash
# Local change-request website, connected to the configured Codex session.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec .venv/bin/python -m change_requests serve "$@"
