#!/usr/bin/env python3
"""Compare a calibrated weighting against uniform weighting on the same judging.

Experiment 0067 pre-registers this comparison: calibrated weights only count as
an improvement if they beat uniform weighting by more than noise. A grid search
that reports its best point without that arm is reporting the maximum of many
tries, not an effect.

Both arms run through the same `evaluate_weights`, on the same test set, the same
graph, the same k, and the same judged ideal — only the weight vector changes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_calibrator():
    path = PROJECT_ROOT / "scripts" / "training" / "calibrate_fusion_weights.py"
    spec = importlib.util.spec_from_file_location("calibrate_fusion_weights", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["calibrate_fusion_weights"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", default="magic")
    parser.add_argument(
        "--weights", type=Path, help="calibrated weights json (default: shipped file)"
    )
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cal = _load_calibrator()
    weights_path = args.weights or (
        cal.DATA_DIR / "embeddings" / f"fusion_weights_{args.game}.json"
    )
    if not weights_path.exists():
        print(f"no weights file at {weights_path}; run the calibration first", file=sys.stderr)
        return 2
    payload = json.loads(weights_path.read_text())
    best = payload.get("best_weights") or payload.get("weights") or {}

    test_data = cal.load_test_set(args.game)
    if not test_data:
        print("test set refused by the gate; nothing to compare", file=sys.stderr)
        return 2
    graph = cal.load_graph(args.game)

    # The calibrator loads these inline rather than exposing helpers, so mirror
    # that here instead of inventing an API it does not have.
    import numpy as np
    from gensim.models import KeyedVectors

    emb_name = {
        "magic": "magic_v7_spectral_mu35",
        "pokemon": "pokemon_v7_fused",
        "yugioh": "yugioh_v7_spectral_mu3",
    }.get(args.game, f"{args.game}_v7_fused")
    wv = KeyedVectors.load(str(cal.DATA_DIR / "embeddings" / f"{emb_name}.wv"))

    def load_index(kind: str):
        idx = cal.DATA_DIR / "cache" / f"{kind}_embeddings" / f"{args.game}_embeddings.npy"
        names = cal.DATA_DIR / "cache" / f"{kind}_embeddings" / f"{args.game}_names.txt"
        if not idx.exists():
            return None, None
        return np.load(str(idx)), [line.strip() for line in names.read_text().splitlines()]

    text_matrix, text_names = load_index("text")
    visual_matrix, visual_names = load_index("visual")

    def score(weights: dict[str, float]) -> dict | float | None:
        # Partial coverage, matching how the weights were fitted: the strict
        # scorer returns None whenever one eligible query is unjudged, which is
        # exactly the condition that blocked the calibration.
        scorer = getattr(cal, "evaluate_weights_partial", None) or cal.evaluate_weights
        return scorer(
            args.game,
            weights.get("embed", 0.0),
            weights.get("jaccard", 0.0),
            weights.get("functional", 0.0),
            weights.get("text_embed", 0.0),
            weights.get("visual_embed", 0.0),
            test_data,
            graph,
            wv,
            text_matrix,
            text_names,
            visual_matrix,
            visual_names,
            k=args.k,
        )

    calibrated = score(best)
    # uniform over the five structural signals the calibrator searches
    uniform_weights = {
        "embed": 0.2,
        "jaccard": 0.2,
        "functional": 0.2,
        "text_embed": 0.2,
        "visual_embed": 0.2,
    }
    uniform = score(uniform_weights)

    def _ndcg(outcome):
        if outcome is None:
            return None
        return outcome["ndcg_at_10"] if isinstance(outcome, dict) else outcome

    def _cov(outcome):
        return outcome.get("coverage") if isinstance(outcome, dict) else None

    # Each arm only scores queries whose judged result it retrieved, so their own
    # means describe two different query sets. The valid comparison is the
    # intersection: queries both arms scored.
    shared_stats = None
    if isinstance(calibrated, dict) and isinstance(uniform, dict):
        cal_map = calibrated.get("per_query") or {}
        uni_map = uniform.get("per_query") or {}
        shared = sorted(set(cal_map) & set(uni_map))
        if shared:
            diffs = [cal_map[q] - uni_map[q] for q in shared]
            shared_stats = {
                "queries": len(shared),
                "calibrated_mean": sum(cal_map[q] for q in shared) / len(shared),
                "uniform_mean": sum(uni_map[q] for q in shared) / len(shared),
                "mean_delta": sum(diffs) / len(diffs),
                "calibrated_wins": sum(1 for d in diffs if d > 0),
                "uniform_wins": sum(1 for d in diffs if d < 0),
                "ties": sum(1 for d in diffs if d == 0),
            }

    same_subset = shared_stats is not None
    cal_score, uni_score = _ndcg(calibrated), _ndcg(uniform)
    result = {
        "game": args.game,
        "weights_file": str(weights_path),
        "calibrated": {"weights": best, "ndcg_at_k": cal_score, "coverage": _cov(calibrated)},
        "uniform": {"weights": uniform_weights, "ndcg_at_k": uni_score, "coverage": _cov(uniform)},
        "delta": (cal_score - uni_score)
        if (cal_score is not None and uni_score is not None)
        else None,
        "same_subset": same_subset,
        "paired_intersection": shared_stats,
        "k": args.k,
        "note": "one number per arm on the same judged subset; no interval here, the CI belongs to the comparison harness",
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"{args.game} nDCG@{args.k}: calibrated={cal_score} "
            f"(coverage {result['calibrated']['coverage']}) "
            f"uniform={uni_score} (coverage {result['uniform']['coverage']}) "
            f"delta={result['delta']} same_subset={same_subset}"
        )
    return 0 if result["delta"] is not None else 2


if __name__ == "__main__":
    sys.exit(main())
