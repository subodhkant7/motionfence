#!/usr/bin/env bash
set -e

echo "=== Running MotionFence Automated Test Suite ==="
python -m pytest tests/ -v
