#!/usr/bin/env python3
"""exp_049: Using Consolidated Shared Code (Actually Fixed)"""

import pandas as pd
from dotenv import load_dotenv

from ..similarity.similarity_methods import (
    evaluate_on_test_set,
    jaccard_similarity,
    load_graph,
)
from .true_closed_loop import ClosedLoopExperiment

load_dotenv()

# Constants


def run_baseline_consolidated(test_set, config):
    """Jaccard using shared methods (no duplication)"""

    adj, _weights = load_graph("../../src/backend/data/processed/pairs_large.csv")

    print(f"  Loaded graph: {len(adj)} cards")

    # Use shared evaluation
    return evaluate_on_test_set(lambda q: jaccard_similarity(q, adj, top_k=10), test_set)


loop = ClosedLoopExperiment(game="magic")

results = loop.run_with_context(
    run_baseline_consolidated,
    {
        "experiment_id": "exp_049",
        "date": "2025-10-01",
        "game": "magic",
        "phase": "code_consolidation",
        "hypothesis": "Shared methods produce same results as duplicated code",
        "method": "Jaccard via similarity_methods.py",
        "fix": "Eliminated code duplication (user principle: best code is no code)",
    },
)

print(f"\nConsolidated code works: {results['p10'] > 0}")
