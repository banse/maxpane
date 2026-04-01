#!/usr/bin/env bash
# Stop the MaxPane dashboard
# Usage: ./scripts/stop.sh

set -euo pipefail
cd "$(dirname "$0")/.."

PIDFILE="data/maxpane.pid"

if [ ! -f "$PIDFILE" ]; then
    echo "No PID file found. MaxPane may not be running."
    # Try to find and kill any orphaned process
    PIDS=$(pgrep -f "python -m dashboard" 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "Found orphaned dashboard process(es): $PIDS"
        echo "$PIDS" | xargs kill 2>/dev/null || true
        echo "Stopped."
    else
        echo "No dashboard process found."
    fi
    exit 0
fi

PID=$(cat "$PIDFILE")

if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping MaxPane (PID $PID)..."
    kill "$PID"
    # Wait up to 5 seconds for graceful shutdown
    for i in 1 2 3 4 5; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    # Force kill if still alive
    if kill -0 "$PID" 2>/dev/null; then
        echo "Force killing..."
        kill -9 "$PID" 2>/dev/null || true
    fi
    echo "Stopped."
else
    echo "Process $PID not running (stale PID file)."
fi

rm -f "$PIDFILE"
