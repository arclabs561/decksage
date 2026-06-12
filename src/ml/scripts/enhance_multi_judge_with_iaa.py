#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-ai>=0.0.12",
# ]
# ///
"""
Enhance multi-judge labeling with IAA tracking.

This script:
- Generates multiple independent judgments per query (via LLM judges)
- Computes Krippendorff's alpha across judges (ordinal 0-4 relevance scale)
- Writes an updated test set JSON with an `iaa` block per query

Notes:
- This is a scripts-layer tool. It assumes you have configured LLM provider env vars
  and that the label-generation scripts are available in this checkout.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Make `ml` importable when running as a script.
_script_file = Path(__file__).resolve()
_src_dir = _script_file.parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from ml.evaluation.inter_annotator_agreement import InterAnnotatorAgreement
from ml.scripts.parallel_multi_judge import (
    HAS_LABELING,
    HAS_PYDANTIC_AI,
    generate_labels_single_judge,
)


LEVEL_TO_SCORE: dict[str, int] = {
    "highly_relevant": 4,
    "relevant": 3,
    "somewhat_relevant": 2,
    "marginally_relevant": 1,
    "irrelevant": 0,
}

LEVEL_PRIORITY: dict[str, int] = {
    "highly_relevant": 4,
    "relevant": 3,
    "somewhat_relevant": 2,
    "marginally_relevant": 1,
    "irrelevant": 0,
}


def _normalize_judgment(judgment: dict[str, Any]) -> dict[str, list[str]]:
    """Remove internal contradictions (same card in multiple levels)."""
    card_to_levels: dict[str, set[str]] = {}
    for level in LEVEL_TO_SCORE:
        cards = judgment.get(level, [])
        if not isinstance(cards, list):
            continue
        for card in cards:
            if not isinstance(card, str) or not card:
                continue
            card_to_levels.setdefault(card, set()).add(level)

    cleaned: dict[str, list[str]] = {k: [] for k in LEVEL_TO_SCORE}
    for card, levels in card_to_levels.items():
        if len(levels) > 1:
            best_level = max(levels, key=lambda lvl: LEVEL_PRIORITY[lvl])
            cleaned[best_level].append(card)
        else:
            cleaned[next(iter(levels))].append(card)

    return cleaned


def _majority_vote(judgments: list[dict[str, list[str]]]) -> dict[str, list[str]]:
    """Majority vote over relevance levels (excludes cards without a majority)."""
    card_votes: dict[str, dict[str, int]] = {}
    for judgment in judgments:
        for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
            for card in judgment.get(level, []):
                card_votes.setdefault(card, {})
                card_votes[card][level] = card_votes[card].get(level, 0) + 1

    threshold = len(judgments) / 2
    final_labels: dict[str, list[str]] = {k: [] for k in LEVEL_TO_SCORE}
    for card, votes in card_votes.items():
        if not votes:
            continue
        best_level, vote_count = max(votes.items(), key=lambda x: x[1])
        if vote_count >= threshold:
            final_labels[best_level].append(card)

    return final_labels


def compute_krippendorff_alpha_for_query(
    query: str,
    judgments: list[dict[str, list[str]]],
    iaa_calculator: InterAnnotatorAgreement,
) -> dict[str, Any]:
    """Compute Krippendorff's alpha across judges for a single query."""
    if len(judgments) < 2:
        return {
            "query": query,
            "alpha": 0.0,
            "interpretation": "insufficient_judgments",
            "n_items": 0,
            "n_annotators": len(judgments),
        }

    # Item universe: all cards mentioned by any judge.
    all_cards: set[str] = set()
    for judgment in judgments:
        for level in LEVEL_TO_SCORE:
            all_cards.update(judgment.get(level, []))

    if not all_cards:
        return {
            "query": query,
            "alpha": 0.0,
            "interpretation": "no_items",
            "n_items": 0,
            "n_annotators": len(judgments),
        }

    ordered_cards = sorted(all_cards)

    # Build (annotator -> ratings list) with None for missing ratings.
    annotations: dict[str, list[int | None]] = {}
    for judge_idx, judgment in enumerate(judgments):
        card_to_score: dict[str, int] = {}
        for level, score in LEVEL_TO_SCORE.items():
            for card in judgment.get(level, []):
                card_to_score[card] = score
        ratings = [card_to_score.get(card) for card in ordered_cards]
        annotations[f"judge_{judge_idx}"] = ratings

    result = iaa_calculator.krippendorffs_alpha(annotations, metric="ordinal")
    result["query"] = query
    return result


def _collect_judgments(
    query: str,
    *,
    num_judges: int,
    use_case: str | None,
    game: str | None,
    max_workers: int,
    timeout_s: float,
) -> list[dict[str, list[str]]]:
    """Collect individual judgments for a query (best-effort)."""
    raw: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(generate_labels_single_judge, query, judge_id, use_case, game): judge_id
            for judge_id in range(num_judges)
        }

        try:
            for future in as_completed(futures, timeout=timeout_s * num_judges):
                judge_id = futures[future]
                try:
                    labels = future.result(timeout=1.0)
                    if labels:
                        raw.append(labels)
                except FutureTimeoutError:
                    logger.warning(f"Judge {judge_id} timed out retrieving result")
                except Exception as e:
                    logger.warning(f"Judge {judge_id} failed: {e}")
        except FutureTimeoutError:
            logger.warning(f"Overall labeling timed out after {timeout_s * num_judges:.1f}s")
            for future in futures:
                future.cancel()

    normalized = [_normalize_judgment(j) for j in raw if isinstance(j, dict)]
    return [j for j in normalized if any(j.values())]


def enhance_labeling_with_iaa(
    *,
    test_set_path: Path,
    output_path: Path,
    num_judges: int = 5,
    min_agreement: float = 0.65,
    re_annotate_threshold: float = 0.60,
    game: str | None = None,
    max_workers: int | None = None,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """Enhance a test set JSON with per-query IAA results."""
    if not HAS_PYDANTIC_AI or not HAS_LABELING:
        logger.error("Required dependencies not available (pydantic-ai / labeling scripts)")
        return {}

    iaa_calculator = InterAnnotatorAgreement()

    if not test_set_path.exists():
        logger.error(f"Test set not found: {test_set_path}")
        return {}

    with open(test_set_path) as f:
        data = json.load(f)

    queries = data.get("queries", data) if isinstance(data, dict) else data
    if not isinstance(queries, dict):
        logger.error("Expected a mapping of query -> data in test set JSON")
        return {}

    logger.info(f"Processing {len(queries)} queries with {num_judges} judges each")
    logger.info(f"Minimum agreement threshold: {min_agreement}")
    logger.info(f"Re-annotation threshold: {re_annotate_threshold}")

    results: dict[str, Any] = {
        "total_queries": len(queries),
        "processed_queries": 0,
        "high_agreement": 0,  # alpha >= min_agreement
        "low_agreement": 0,  # alpha < re_annotate_threshold
        "medium_agreement": 0,  # re_annotate_threshold <= alpha < min_agreement
        "re_annotated": 0,
        "iaa_details": {},
        "queries_needing_re_annotation": [],
    }

    updated_queries: dict[str, Any] = {}
    workers = max_workers or min(num_judges, 8)

    for query_name, query_data in queries.items():
        use_case = query_data.get("use_case") if isinstance(query_data, dict) else None
        query_game = query_data.get("game") if isinstance(query_data, dict) else None
        effective_game = (query_game or game) if isinstance(query_game, str) else game

        judgments = _collect_judgments(
            query_name,
            num_judges=num_judges,
            use_case=use_case,
            game=effective_game,
            max_workers=workers,
            timeout_s=timeout_s,
        )

        if len(judgments) < 2:
            logger.warning(f"Insufficient judgments for {query_name}")
            continue

        iaa_result = compute_krippendorff_alpha_for_query(
            query=query_name,
            judgments=judgments,
            iaa_calculator=iaa_calculator,
        )
        alpha = float(iaa_result.get("alpha", 0.0) or 0.0)

        results["iaa_details"][query_name] = iaa_result

        if alpha >= min_agreement:
            results["high_agreement"] += 1
        elif alpha < re_annotate_threshold:
            results["low_agreement"] += 1
            results["queries_needing_re_annotation"].append(
                {
                    "query": query_name,
                    "alpha": alpha,
                    "interpretation": iaa_result.get("interpretation", "unknown"),
                }
            )
        else:
            results["medium_agreement"] += 1

        final_labels = _majority_vote(judgments)
        updated_queries[query_name] = {
            **(query_data if isinstance(query_data, dict) else {"data": query_data}),
            **final_labels,
            "iaa": iaa_result,
        }
        results["processed_queries"] += 1

    # Save updated test set
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({"queries": updated_queries}, f, indent=2)

    # Summary stats
    if results["processed_queries"]:
        alphas = [float(d.get("alpha", 0.0) or 0.0) for d in results["iaa_details"].values()]
        results["mean_alpha"] = sum(alphas) / len(alphas) if alphas else 0.0
        results["min_alpha"] = min(alphas) if alphas else 0.0
        results["max_alpha"] = max(alphas) if alphas else 0.0

    logger.info("=" * 70)
    logger.info("IAA ENHANCEMENT COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Total queries: {results['total_queries']}")
    logger.info(f"Processed queries: {results['processed_queries']}")
    logger.info(f"High agreement (alpha >= {min_agreement}): {results['high_agreement']}")
    logger.info(
        f"Medium agreement ({re_annotate_threshold} <= alpha < {min_agreement}): {results['medium_agreement']}"
    )
    logger.info(f"Low agreement (alpha < {re_annotate_threshold}): {results['low_agreement']}")
    logger.info(f"Mean alpha: {results.get('mean_alpha', 0.0):.3f}")
    logger.info(f"Queries needing re-annotation: {len(results['queries_needing_re_annotation'])}")
    logger.info(f"Enhanced test set saved to {output_path}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enhance multi-judge labeling with IAA tracking",
    )
    parser.add_argument("--test-set", type=Path, required=True, help="Input test set JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output test set JSON")
    parser.add_argument("--num-judges", type=int, default=5, help="Judges per query")
    parser.add_argument("--min-agreement", type=float, default=0.65, help="Min alpha threshold")
    parser.add_argument(
        "--re-annotate-threshold",
        type=float,
        default=0.60,
        help="Alpha threshold below which queries are flagged",
    )
    parser.add_argument(
        "--game",
        choices=["magic", "pokemon", "yugioh", "riftbound", "MTG", "PKM", "YGO"],
        default=None,
        help="Optional game override",
    )
    parser.add_argument("--max-workers", type=int, default=None, help="Parallel judge workers")
    parser.add_argument("--timeout-s", type=float, default=120.0, help="Per-judge timeout")
    args = parser.parse_args()

    results = enhance_labeling_with_iaa(
        test_set_path=args.test_set,
        output_path=args.output,
        num_judges=args.num_judges,
        min_agreement=args.min_agreement,
        re_annotate_threshold=args.re_annotate_threshold,
        game=args.game,
        max_workers=args.max_workers,
        timeout_s=args.timeout_s,
    )

    report_path = args.output.parent / f"{args.output.stem}_iaa_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"IAA analysis report saved to {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
