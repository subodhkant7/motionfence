#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

if [ -f "$DIR/.venv/bin/pytest" ]; then
    PYTEST_BIN="$DIR/.venv/bin/pytest"
else
    PYTEST_BIN="pytest"
fi

echo "=== Running MotionFence Automated Test Suite ==="
"$PYTEST_BIN" tests/ -v
