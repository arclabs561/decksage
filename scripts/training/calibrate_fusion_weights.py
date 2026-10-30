#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
#     "numpy>=1.24.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Calibrate fusion signal weights against annotated test sets.

Grid-searches FusionWeights to maximize nDCG@k over judged candidates (the
condensed variant: unjudged results are ignored, while the ideal ranking uses
all judged candidates). The grid runs on an 80% query split
and the selected weights are reported on the held-out 20%; a fit-on-everything
number is not comparable to eval_per_mode.py.

Outputs best weights as JSON for loading via FUSION_WEIGHTS_PATH_{GAME}.

Usage:
    uv run scripts/training/calibrate_fusion_weights.py --game magic
    uv run scripts/training/calibrate_fusion_weights.py --all-games
    uv run scripts/training/calibrate_fusion_weights.py --game magic --quick
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import random
import sys
import time
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


# Signal grid: values to try per signal (will normalize to sum=1)
QUICK_GRID = {
    "embed": [0.0, 0.25, 0.5],
    "jaccard": [0.0, 0.15, 0.3],
    "functional": [0.0, 0.1],
    "text_embed": [0.0, 0.3, 0.5],
    "visual_embed": [0.0, 0.2],
}

FULL_GRID = {
    "embed": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
    "jaccard": [0.0, 0.05, 0.1, 0.15, 0.2, 0.3],
    "functional": [0.0, 0.05, 0.1, 0.15],
    "text_embed": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
    "visual_embed": [0.0, 0.05, 0.1, 0.2],
}


def load_test_set(game: str, allow_contradictions: bool = False) -> dict:
    """Load annotated test set for a game, refusing self-contradictory labels."""
    path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not path.exists():
        log.error(f"Test set not found: {path}")
        return {}
    with open(path) as f:
        data = json.load(f)
    from ml.contracts.annotations import curate_evaluation_data
    from ml.evaluation.label_gate import gate_or_refuse

    data, excluded = curate_evaluation_data(data)
    if excluded:
        log.warning("Excluded %s failed, synthetic, or fallback judgments", excluded)
    try:
        gate = gate_or_refuse(path, allow=allow_contradictions)
        log.info("Label gate: %s", gate.summary())
    except ValueError as exc:
        log.error("%s", exc)
        return {}
    return data


def load_graph(game: str):
    """Load co-occurrence graph for a game."""
    from ml.similarity.similarity_methods import load_graph

    pairs_dir = DATA_DIR / "processed"
    import glob

    pattern = str(pairs_dir / f"pairs_{game}_*.csv")
    matches = glob.glob(pattern)
    if not matches:
        return None
    # Use largest
    pairs_path = sorted(matches, key=lambda p: Path(p).stat().st_size)[-1]
    log.info(f"  Graph: {Path(pairs_path).name}")
    # similarity_methods.load_graph returns (adjacency, edge_weights); the
    # calibrator only needs the adjacency dict.
    adj, _weights = load_graph(pairs_path)
    return adj


def _ground_truth(labels) -> dict[str, float]:
    """Read substitution scores without substituting composite bucket labels."""
    gt: dict[str, float] = {}
    if isinstance(labels, dict):
        for ann in labels.get("annotations", []):
            name = ann.get("candidate") or ann.get("card") or ""
            score = ann.get("functional_score")
            if not name or score is None or ann.get("task") not in (None, "", "substitute"):
                continue
            gt[name] = max(gt.get(name, 0.0), float(score))
    return gt


def compute_ndcg(relevances: list[float], ideal_relevances: list[float], k: int) -> float:
    """Compute nDCG@k."""
    dcg = sum(r / np.log2(i + 2) for i, r in enumerate(relevances[:k]))
    ideal = sorted(ideal_relevances, reverse=True)
    idcg = sum(r / np.log2(i + 2) for i, r in enumerate(ideal[:k]))
    return dcg / idcg if idcg > 0 else 0.0


def evaluate_weights(
    game: str,
    w_embed: float,
    w_jaccard: float,
    w_functional: float,
    w_text: float,
    w_visual: float,
    test_data: dict,
    graph,
    wv,
    text_index_matrix,
    text_index_names,
    visual_index_matrix,
    visual_index_names,
    k: int = 10,
) -> float | None:
    """Return condensed nDCG only when every eligible query has judged results."""
    from ml.similarity.fusion import FusionWeights, WeightedLateFusion

    # Skip configs where all weights are 0
    total = w_embed + w_jaccard + w_functional + w_text + w_visual
    if total <= 0:
        return None

    weights = FusionWeights(
        embed=w_embed,
        jaccard=w_jaccard,
        functional=w_functional,
        text_embed=w_text,
        visual_embed=w_visual,
        archetype=0.0,
    )

    fusion = WeightedLateFusion(
        embeddings=wv,
        adj=graph,
        weights=weights,
        aggregator="rrf",
        game=game,
    )

    # Inject pre-computed indices
    if text_index_matrix is not None:
        fusion._text_index_matrix = text_index_matrix
        fusion._text_index_names = text_index_names
        fusion._text_name_to_idx = {n: i for i, n in enumerate(text_index_names)}
    if visual_index_matrix is not None:
        fusion._visual_index_matrix = visual_index_matrix
        fusion._visual_index_names = visual_index_names
        fusion._visual_name_to_idx = {n: i for i, n in enumerate(visual_index_names)}

    queries = test_data.get("queries", {})
    ndcg_scores = []

    for query_card, labels in queries.items():
        if query_card not in wv and (not graph or query_card not in graph):
            continue

        gt = _ground_truth(labels)

        if not gt or max(gt.values()) <= 0:
            continue

        results = fusion.similar(query_card, k=k)
        relevances = [gt[card] for card, _ in results if card in gt]
        if not relevances:
            return None
        ndcg_scores.append(compute_ndcg(relevances, list(gt.values()), k))

    return float(np.mean(ndcg_scores)) if ndcg_scores else None


def evaluate_weights_partial(
    game: str,
    w_embed: float,
    w_jaccard: float,
    w_functional: float,
    w_text: float,
    w_visual: float,
    test_data: dict,
    graph,
    wv,
    text_index_matrix,
    text_index_names,
    visual_index_matrix,
    visual_index_names,
    k: int = 10,
) -> dict | None:
    """Score on the queries that are actually judgeable, and report how many.

    The strict scorer returns None when a single eligible query lacks a judged
    result, which made the objective unmeasurable on the canonical set. This one
    scores the judgeable subset and returns the denominator with the score, so a
    published number always travels with its coverage. A caller that hides the
    coverage would be back to the 0065 mistake.
    """
    from ml.similarity.fusion import FusionWeights, WeightedLateFusion

    total = w_embed + w_jaccard + w_functional + w_text + w_visual
    if total <= 0:
        return None

    weights = FusionWeights(
        embed=w_embed,
        jaccard=w_jaccard,
        functional=w_functional,
        text_embed=w_text,
        visual_embed=w_visual,
        archetype=0.0,
    )
    fusion = WeightedLateFusion(
        embeddings=wv, adj=graph, weights=weights, aggregator="rrf", game=game
    )
    if text_index_matrix is not None:
        fusion._text_index_matrix = text_index_matrix
        fusion._text_index_names = text_index_names
        fusion._text_name_to_idx = {n: i for i, n in enumerate(text_index_names)}
    if visual_index_matrix is not None:
        fusion._visual_index_matrix = visual_index_matrix
        fusion._visual_index_names = visual_index_names
        fusion._visual_name_to_idx = {n: i for i, n in enumerate(visual_index_names)}

    eligible = scored = 0
    ndcg_scores: list[float] = []
    per_query: dict[str, float] = {}
    for query_card, labels in test_data.get("queries", {}).items():
        if query_card not in wv and (not graph or query_card not in graph):
            continue
        gt = _ground_truth(labels)
        if not gt or max(gt.values()) <= 0:
            continue
        eligible += 1
        results = fusion.similar(query_card, k=k)
        relevances = [gt[card] for card, _ in results if card in gt]
        if not relevances:
            continue
        scored += 1
        value = float(compute_ndcg(relevances, list(gt.values()), k))
        ndcg_scores.append(value)
        per_query[query_card] = value

    if not ndcg_scores:
        return None
    return {
        "ndcg_at_10": float(np.mean(ndcg_scores)),
        "queries_eligible": eligible,
        "queries_scored": scored,
        "coverage": scored / eligible if eligible else 0.0,
        # Per-query values so two arms can be compared on their intersection
        # instead of each on its own convenient subset.
        "per_query": per_query,
    }


def calibrate(game: str, quick: bool = False) -> dict | None:
    """Grid-search fusion weights for a game."""
    out_path = DATA_DIR / "embeddings" / f"fusion_weights_{game}.json"
    if out_path.exists():
        raise FileExistsError(f"Refusing to overwrite {out_path}")
    grid = QUICK_GRID if quick else FULL_GRID

    log.info(f"\n{'=' * 60}")
    log.info(f"Calibrating fusion weights for {game.upper()} ({'quick' if quick else 'full'} grid)")
    log.info(f"{'=' * 60}")

    # Load resources
    log.info("Loading resources...")
    test_data = load_test_set(game, allow_contradictions=ALLOW_CONTRADICTIONS)
    if not test_data:
        return None

    queries = test_data.get("queries", {})
    names = sorted(queries)
    random.Random(13).shuffle(names)
    split = int(len(names) * 0.8)
    train_data = {"queries": {name: queries[name] for name in names[:split]}}
    holdout_data = {"queries": {name: queries[name] for name in names[split:]}}
    log.info(f"  Fit queries: {split:,}  holdout: {len(names) - split:,}")

    from gensim.models import KeyedVectors

    emb_name = {
        "magic": "magic_v7_spectral_mu35",
        "pokemon": "pokemon_v7_fused",
        "yugioh": "yugioh_v7_spectral_mu3",
    }.get(game)
    emb_path = DATA_DIR / "embeddings" / f"{emb_name}.wv"
    if not emb_path.exists():
        log.error(f"Embedding not found: {emb_path}")
        return None
    wv = KeyedVectors.load(str(emb_path))
    log.info(f"  Embeddings: {emb_name} ({len(wv):,} cards)")

    graph = load_graph(game)

    # Load text/visual indices
    text_idx_path = DATA_DIR / "cache" / "text_embeddings" / f"{game}_embeddings.npy"
    text_names_path = DATA_DIR / "cache" / "text_embeddings" / f"{game}_names.txt"
    text_matrix = text_names = None
    if text_idx_path.exists():
        text_matrix = np.load(str(text_idx_path))
        with open(text_names_path) as f:
            text_names = [line.strip() for line in f]
        log.info(f"  Text index: {text_matrix.shape[0]:,} cards")

    vis_idx_path = DATA_DIR / "cache" / "visual_embeddings" / f"{game}_embeddings.npy"
    vis_names_path = DATA_DIR / "cache" / "visual_embeddings" / f"{game}_names.txt"
    vis_matrix = vis_names = None
    if vis_idx_path.exists():
        vis_matrix = np.load(str(vis_idx_path))
        with open(vis_names_path) as f:
            vis_names = [line.strip() for line in f]
        nonzero = int(np.count_nonzero(vis_matrix) / vis_matrix.shape[1])
        log.info(f"  Visual index: {vis_matrix.shape[0]:,} cards ({nonzero} with images)")

    # A weight is only meaningful for a signal that can actually produce a
    # score. WeightedLateFusion is built here without a tagger or text/visual
    # embedder, so any missing input yields a constant 0.0 and the grid would
    # happily "fit" it to zero, recording "this signal does not matter" when the
    # truth is "this signal was never computed".
    text_has_signal = text_matrix is not None and float(np.std(text_matrix[:512])) > 0.0
    visual_has_signal = (
        vis_matrix is not None
        and int(np.count_nonzero(vis_matrix[: min(512, vis_matrix.shape[0])])) > 0
    )
    availability = {
        "embed": len(wv) > 0,
        "jaccard": bool(graph) and len(graph) > 0,
        # No tagger is passed to WeightedLateFusion in this script, so the
        # functional signal can only ever score zero here.
        "functional": False,
        "text_embed": text_has_signal,
        "visual_embed": visual_has_signal,
    }
    excluded = {
        "embed": "embedding file is empty",
        "jaccard": "no co-occurrence graph",
        "functional": "no tagger is constructed in this script",
        "text_embed": "text index missing or constant",
        "visual_embed": "visual index missing or all-zero",
    }
    excluded = {k: excluded[k] for k, v in availability.items() if not v}
    for key, reason in excluded.items():
        log.warning(f"  Excluding {key}: {reason}")

    keys = [key for key in grid if availability[key]]
    if len(keys) < 2:
        log.error(
            "Refusing to calibrate: fewer than two live signals (%s). "
            "Weights fitted over constants are meaningless.",
            ", ".join(keys) or "none",
        )
        return None
    combos = list(itertools.product(*[grid[k] for k in keys]))
    log.info(f"  Grid: {len(combos)} combinations over {', '.join(keys)}")

    best_score = 0.0
    best_weights = None
    t0 = time.time()

    def run_eval(data, vals):
        """Score one weight vector; partial mode reports its own coverage."""
        args = (
            game,
            vals["embed"],
            vals["jaccard"],
            vals["functional"],
            vals["text_embed"],
            vals["visual_embed"],
            data,
            graph,
            wv,
            text_matrix,
            text_names,
            vis_matrix,
            vis_names,
        )
        if ALLOW_PARTIAL_COVERAGE:
            return evaluate_weights_partial(*args)
        strict = evaluate_weights(*args)
        if strict is None:
            return None
        return {"ndcg_at_10": strict, "coverage": 1.0, "queries_scored": 0, "queries_eligible": 0}

    for i, combo in enumerate(combos):
        vals = dict.fromkeys(grid, 0.0)
        vals.update(zip(keys, combo))
        outcome = run_eval(train_data, vals)
        if outcome is not None and outcome["coverage"] < MIN_COVERAGE:
            outcome = None
        score = outcome["ndcg_at_10"] if outcome else None
        if score is not None and score > best_score:
            best_score = score
            best_weights = vals
            log.info(
                f"  [{i + 1}/{len(combos)}] NEW BEST: nDCG={score:.4f}  "
                f"embed={vals['embed']:.2f} jacc={vals['jaccard']:.2f} "
                f"func={vals['functional']:.2f} text={vals['text_embed']:.2f} "
                f"vis={vals['visual_embed']:.2f}"
            )

    elapsed = time.time() - t0
    holdout_score = None
    holdout_coverage = 0.0
    if best_weights is not None and ALLOW_PARTIAL_COVERAGE:
        outcome = run_eval(holdout_data, best_weights)
        if outcome is not None and outcome["coverage"] >= MIN_COVERAGE:
            holdout_score = outcome["ndcg_at_10"]
            holdout_coverage = outcome["coverage"]
    elif best_weights is not None:
        holdout_score = evaluate_weights(
            game,
            best_weights["embed"],
            best_weights["jaccard"],
            best_weights["functional"],
            best_weights["text_embed"],
            best_weights["visual_embed"],
            holdout_data,
            graph,
            wv,
            text_matrix,
            text_names,
            vis_matrix,
            vis_names,
        )
    log.info(f"\nCalibration done in {elapsed:.0f}s")
    log.info(f"Fit nDCG@10: {best_score:.4f}")
    if best_weights is None or holdout_score is None:
        log.error(
            "Refusing to publish weights: comparable judged coverage is unavailable "
            "(strict mode; pass --allow-partial-coverage with --min-coverage to score "
            "the judgeable subset and publish its denominator)"
        )
        return None
    log.info(f"Holdout nDCG@10: {holdout_score:.4f}")
    log.info(f"Best weights: {best_weights}")

    result = {
        "game": game,
        "ndcg_at_10": holdout_score,
        "ndcg_at_10_fit": best_score,
        "best_weights": best_weights,
        "grid_size": len(combos),
        "fit_queries": split,
        "holdout_queries": len(names) - split,
        "elapsed_seconds": round(elapsed),
        "calibration_type": "quick" if quick else "full",
        "has_visual_index": vis_matrix is not None,
        "has_text_index": text_matrix is not None,
        "signals_used": keys,
        "signals_excluded": excluded,
        "objective": "partial-coverage-v1" if ALLOW_PARTIAL_COVERAGE else "strict-coverage-v1",
        "holdout_coverage": round(holdout_coverage, 4),
        "min_coverage": MIN_COVERAGE if ALLOW_PARTIAL_COVERAGE else 1.0,
        "experiment": "0067",
    }

    # Save
    with open(out_path, "x") as f:
        json.dump(result, f, indent=2)
    log.info(f"Saved to {out_path}")

    return result


ALLOW_CONTRADICTIONS = False
ALLOW_PARTIAL_COVERAGE = False
MIN_COVERAGE = 0.5


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate fusion weights")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--quick", action="store_true", help="Smaller grid for fast iteration")
    parser.add_argument(
        "--allow-partial-coverage",
        action="store_true",
        help="Score the judgeable subset and publish its coverage instead of refusing",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.5,
        help="Refuse to publish when scored/eligible falls below this (partial mode)",
    )
    parser.add_argument(
        "--allow-contradictions",
        action="store_true",
        help="Calibrate even when labels contradict shipped card metadata (records the override)",
    )
    args = parser.parse_args()

    global ALLOW_CONTRADICTIONS, ALLOW_PARTIAL_COVERAGE, MIN_COVERAGE
    ALLOW_CONTRADICTIONS = args.allow_contradictions
    ALLOW_PARTIAL_COVERAGE = args.allow_partial_coverage
    MIN_COVERAGE = args.min_coverage

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    results = {}
    for game in games:
        r = calibrate(game, quick=args.quick)
        if r:
            results[game] = r

    if results:
        log.info(f"\n{'=' * 60}")
        log.info("Summary:")
        for game, r in results.items():
            w = r["best_weights"]
            log.info(
                f"  {game}: nDCG={r['ndcg_at_10']:.4f}  "
                f"e={w['embed']:.2f} j={w['jaccard']:.2f} "
                f"f={w['functional']:.2f} t={w['text_embed']:.2f} "
                f"v={w['visual_embed']:.2f}"
            )

    return 0 if len(results) == len(games) else 1


if __name__ == "__main__":
    sys.exit(main())
