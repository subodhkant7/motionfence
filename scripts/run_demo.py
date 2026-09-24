#!/usr/bin/env python3
"""Convenience runner for the MotionFence simulation demonstration."""

import os
import sys

# Ensure package root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.simulation.demo import main

if __name__ == "__main__":
    sys.exit(main())
