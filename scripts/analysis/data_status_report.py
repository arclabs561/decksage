#!/usr/bin/env python3
"""Report the health of the datasets in this checkout."""

from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("dataset_health_check.py")), run_name="__main__")
