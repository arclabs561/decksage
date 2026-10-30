#!/usr/bin/env python3
"""Compare a calibrated weighting against uniform weighting on the same judging.

Experiment 0067 pre-registers this comparison: calibrated weights only count as
an improvement if they beat uniform weighting by more than noise. A grid search
that reports its best point without that arm is reporting the maximum of many
tries, not an effect.

Both arms run through the same scorer, on the same test set, the same graph and
the same k. Candidate gathering is weight-independent — graph neighbours, the
embedding index and the text/visual top-N do not read the fusion weights — so
both arms draw from one candidate pool per query. What differs is the ranking the
weights impose, so each arm's nDCG@k is computed over its own top-k. The per-arm
means are therefore conditional on each arm's ranking, and the paired
intersection is the only like-for-like comparison. `docs/JUDGE-CALIBRATION.md`
states the rule.

Exit codes: 0 when a comparison was published (a delta on one query set, or a
paired intersection with the delta withheld), 2 when nothing was comparable.
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


def _per_query(outcome) -> dict:
    """Per-query values for a partial-coverage arm; empty for a strict score."""
    if not isinstance(outcome, dict):
        return {}
    return outcome.get("per_query") or {}


def _scored_or_eligible(outcome, key: str, fallback: int) -> int:
    if isinstance(outcome, dict) and outcome.get(key) is not None:
        return int(outcome[key])
    return fallback


def compare_outcomes(calibrated, uniform, k: int) -> dict:
    """Assemble the comparison record, refusing a delta across unlike query sets.

    An arm's own mean describes the queries it happened to score. Subtracting
    two such means mixes "the weighting is better" with "this arm retrieved
    judged candidates for more queries", so the raw delta is only published when
    both arms scored exactly the same queries. Otherwise the record carries the
    paired intersection and the reason the delta was withheld.
    """
    cal_map, uni_map = _per_query(calibrated), _per_query(uniform)
    cal_scored, uni_scored = set(cal_map), set(uni_map)
    shared = sorted(cal_scored & uni_scored)
    # The strict scorer returns a scalar only when every eligible query has a
    # judged result, so two scalars are already a like-for-like comparison.
    strict_pair = (
        calibrated is not None
        and uniform is not None
        and not isinstance(calibrated, dict)
        and not isinstance(uniform, dict)
    )
    same_subset = strict_pair or (bool(cal_scored) and cal_scored == uni_scored)

    paired = None
    if shared:
        diffs = [cal_map[q] - uni_map[q] for q in shared]
        paired = {
            "queries": len(shared),
            "calibrated_mean": sum(cal_map[q] for q in shared) / len(shared),
            "uniform_mean": sum(uni_map[q] for q in shared) / len(shared),
            "mean_delta": sum(diffs) / len(diffs),
            "calibrated_wins": sum(1 for d in diffs if d > 0),
            "uniform_wins": sum(1 for d in diffs if d < 0),
            "ties": sum(1 for d in diffs if d == 0),
        }

    def _ndcg(outcome):
        if outcome is None:
            return None
        return outcome["ndcg_at_10"] if isinstance(outcome, dict) else outcome

    def _cov(outcome):
        return outcome.get("coverage") if isinstance(outcome, dict) else None

    def _arm(outcome) -> dict:
        if outcome is not None and not isinstance(outcome, dict):
            # The strict scorer only returns a number when every eligible query
            # had a judged result, so its coverage is 1.0 and the counts are not
            # reported by that scorer.
            return {
                "ndcg_at_k": float(outcome),
                "coverage": 1.0,
                "queries_eligible": None,
                "queries_scored": None,
            }
        return {
            "ndcg_at_k": _ndcg(outcome),
            "coverage": _cov(outcome),
            "queries_eligible": _scored_or_eligible(
                outcome, "queries_eligible", len(_per_query(outcome))
            ),
            "queries_scored": _scored_or_eligible(
                outcome, "queries_scored", len(_per_query(outcome))
            ),
        }

    cal_score, uni_score = _ndcg(calibrated), _ndcg(uniform)
    withheld = None
    if not same_subset:
        if not cal_scored or not uni_scored:
            withheld = (
                "no per-query values to pair, so there is no evidence both arms "
                "scored the same queries; a delta would mix two query sets"
            )
        else:
            withheld = (
                "arms scored different query sets "
                f"(calibrated {len(cal_scored)}, uniform {len(uni_scored)}, "
                f"shared {len(shared)}); only the paired intersection is comparable"
            )
    elif cal_score is None or uni_score is None:
        withheld = "an arm produced no score"
    delta = (cal_score - uni_score) if withheld is None else None

    result = {
        "calibrated": _arm(calibrated),
        "uniform": _arm(uniform),
        "delta": delta,
        "delta_withheld": withheld,
        "same_subset": same_subset,
        "paired_intersection": paired,
        "k": k,
        "coverage_definition": "query coverage: queries with >= 1 judged result / eligible queries, at the reporting k",
        "note": "per-arm means come from each arm's own ranking of a shared candidate pool; the paired delta fixes the query set, not the ranking",
    }
    return result


def _coverage_label(arm: dict) -> str:
    """Coverage and its fraction, or the strict scorer's guarantee."""
    if arm.get("queries_eligible") is None:
        return "coverage 1.0, strict: every eligible query scored"
    return f"coverage {arm['coverage']}, {arm['queries_scored']}/{arm['queries_eligible']}"


def format_report(result: dict) -> str:
    """Human line for a comparison record; names coverage before any score."""
    cal, uni = result["calibrated"], result["uniform"]
    lines = [
        f"{result.get('game', 'game')} nDCG@{result['k']}: "
        f"calibrated={cal['ndcg_at_k']} ({_coverage_label(cal)}) "
        f"uniform={uni['ndcg_at_k']} ({_coverage_label(uni)})"
    ]
    if result["delta"] is None:
        lines.append(f"delta withheld: {result['delta_withheld']}")
    else:
        lines.append(f"delta={result['delta']} same_subset={result['same_subset']}")
    paired = result.get("paired_intersection")
    if paired:
        lines.append(
            f"paired on {paired['queries']} shared queries: "
            f"calibrated={paired['calibrated_mean']:.4f} "
            f"uniform={paired['uniform_mean']:.4f} "
            f"delta={paired['mean_delta']:+.4f} "
            f"({paired['calibrated_wins']}W/{paired['uniform_wins']}L/{paired['ties']}T)"
        )
    else:
        lines.append("paired intersection: none (the arms share no scored query)")
    return "\n".join(lines)


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

    result = compare_outcomes(calibrated, uniform, args.k)
    result = {
        "game": args.game,
        "weights_file": str(weights_path),
        "calibrated": {**result["calibrated"], "weights": best},
        "uniform": {**result["uniform"], "weights": uniform_weights},
        **{
            key: result[key]
            for key in (
                "delta",
                "delta_withheld",
                "same_subset",
                "paired_intersection",
                "k",
                "coverage_definition",
                "note",
            )
        },
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_report(result))
    # 0 means a comparison was published: a like-for-like delta, or a paired
    # intersection whose delta is explicitly withheld.
    published = result["delta"] is not None or result["paired_intersection"] is not None
    return 0 if published else 2


if __name__ == "__main__":
    sys.exit(main())
