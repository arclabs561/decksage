#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Compare manual fusion vs learned reranking on test set.

Shows side-by-side comparison of:
- Manual fusion (RRF/weighted)
- Learned reranking (if model available)
- Feature importance analysis
"""

import sys
from pathlib import Path


# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths


setup_project_paths()

from scripts.evaluation.evaluate_reranker import main as evaluate_main


if __name__ == "__main__":
    # Use evaluate_reranker.py as the main implementation
    evaluate_main()
