#!/usr/bin/env python3
"""Analyze dialogue annotations and convert to graded-relevance test sets.

Reads dialogue checkpoint JSONL files produced by judge_dialogue.py and:
1. Reports per-category accuracy (do hard_negatives score low? model_confirms high?)
2. Measures judge prediction quality (expected_similarity vs consensus score)
3. Aggregates suggestion reasons to surface systematic model weaknesses
4. Converts annotations to graded-relevance test sets (same format as convert_to_test_set.py)

Usage:
  PYTHONPATH=src .venv/bin/python scripts/evaluation/analyze_dialogue.py
  PYTHONPATH=src .venv/bin/python scripts/evaluation/analyze_dialogue.py --no-test-sets
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

# Same thresholds as convert_to_test_set.py
GRADE_THRESHOLDS = {
    "highly_relevant": 0.70,
    "relevant": 0.50,
    "somewhat_relevant": 0.35,
    "marginally_relevant": 0.20,
}

TYPE_TO_USE_CASE = {
    "functional": "functional",
    "synergy": "synergy",
    "archetype": "archetype",
    "manabase": "functional",
    "unrelated": "functional",
}

ANNOTATIONS_DIR = Path("data/annotations")
OUTPUT_DIR = Path("data")

# Which files to load, in priority order (larger runs preferred)
DIALOGUE_FILES = {
    "magic": [
        "dialogue_magic_50.checkpoint.jsonl",
        "dialogue_magic.checkpoint.jsonl",
    ],
    "pokemon": [
        "dialogue_pokemon_30.checkpoint.jsonl",
        "dialogue_pokemon.checkpoint.jsonl",
    ],
    "yugioh": [
        "dialogue_yugioh.checkpoint.jsonl",
    ],
}


def load_dialogue_entries(game: str) -> list[dict]:
    """Load dialogue entries for a game, preferring the largest available file."""
    candidates = DIALOGUE_FILES.get(game, [])
    for fname in candidates:
        path = ANNOTATIONS_DIR / fname
        if path.exists():
            entries = []
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
            return entries
    return []


def pearson_r(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n)
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n)
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n * sx * sy)


def analyze_category_accuracy(entries: list[dict]) -> dict[str, dict]:
    """Per-category stats: mean consensus score, score distribution."""
    by_cat: dict[str, list[float]] = defaultdict(list)
    for e in entries:
        cat = e.get("suggestion_metadata", {}).get("category", "unknown")
        score = e["consensus"]["similarity_score"]
        by_cat[cat].append(score)

    results = {}
    for cat, scores in sorted(by_cat.items()):
        n = len(scores)
        mean = sum(scores) / n
        std = math.sqrt(sum((s - mean) ** 2 for s in scores) / n) if n > 1 else 0
        results[cat] = {
            "n": n,
            "mean_score": round(mean, 3),
            "std": round(std, 3),
            "min": round(min(scores), 3),
            "max": round(max(scores), 3),
            "median": round(sorted(scores)[n // 2], 3),
        }
    return results


def analyze_judge_prediction(entries: list[dict]) -> dict:
    """Compare expected_similarity (judge prediction) vs consensus score."""
    expected = []
    actual = []
    errors = []
    for e in entries:
        meta = e.get("suggestion_metadata", {})
        exp = meta.get("expected_similarity")
        if exp is None:
            continue
        act = e["consensus"]["similarity_score"]
        expected.append(exp)
        actual.append(act)
        errors.append(act - exp)

    if not expected:
        return {"n": 0}

    n = len(expected)
    mae = sum(abs(e) for e in errors) / n
    rmse = math.sqrt(sum(e ** 2 for e in errors) / n)
    bias = sum(errors) / n
    r = pearson_r(expected, actual)

    return {
        "n": n,
        "pearson_r": round(r, 3),
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "bias": round(bias, 3),  # positive = actual > expected
    }


def analyze_error_rates(entries: list[dict]) -> dict:
    """False positive rate (hard_negatives scoring high) and false negative rate
    (hidden_substitutes scoring low)."""
    hard_neg_scores = []
    hidden_sub_scores = []

    for e in entries:
        cat = e.get("suggestion_metadata", {}).get("category")
        score = e["consensus"]["similarity_score"]
        if cat == "hard_negative":
            hard_neg_scores.append(score)
        elif cat == "hidden_substitute":
            hidden_sub_scores.append(score)

    result = {}

    if hard_neg_scores:
        # False positive: hard_negative pairs that score >= 0.50 (relevant threshold)
        fp = sum(1 for s in hard_neg_scores if s >= GRADE_THRESHOLDS["relevant"])
        result["hard_negative"] = {
            "n": len(hard_neg_scores),
            "false_positive_count": fp,
            "false_positive_rate": round(fp / len(hard_neg_scores), 3),
            "mean_score": round(sum(hard_neg_scores) / len(hard_neg_scores), 3),
        }

    if hidden_sub_scores:
        # False negative: hidden_substitute pairs that score < 0.50 (below relevant)
        fn = sum(1 for s in hidden_sub_scores if s < GRADE_THRESHOLDS["relevant"])
        result["hidden_substitute"] = {
            "n": len(hidden_sub_scores),
            "false_negative_count": fn,
            "false_negative_rate": round(fn / len(hidden_sub_scores), 3),
            "mean_score": round(sum(hidden_sub_scores) / len(hidden_sub_scores), 3),
        }

    return result


def aggregate_reasons(entries: list[dict], top_n: int = 10) -> dict[str, list[tuple[str, int]]]:
    """Extract common themes from suggestion reasons, grouped by category."""
    by_cat: dict[str, Counter] = defaultdict(Counter)
    for e in entries:
        meta = e.get("suggestion_metadata", {})
        cat = meta.get("category", "unknown")
        reason = meta.get("reason", "")
        if not reason:
            continue
        # Use first sentence as a rough theme key
        first_sentence = reason.split(".")[0].strip()
        if len(first_sentence) > 120:
            first_sentence = first_sentence[:117] + "..."
        by_cat[cat][first_sentence] += 1

    return {
        cat: counts.most_common(top_n)
        for cat, counts in sorted(by_cat.items())
    }


def convert_to_test_set(entries: list[dict], game: str, min_pairs: int = 2) -> dict:
    """Convert dialogue entries to graded-relevance test set format."""
    query_pairs: dict[str, list[dict]] = defaultdict(list)

    for e in entries:
        c1, c2 = e["card1"], e["card2"]
        consensus = e["consensus"]
        score = consensus["similarity_score"]
        sim_type = consensus.get("similarity_type", "functional")
        agreement = e.get("agreement_level", "unknown")

        entry = {"score": score, "sim_type": sim_type, "agreement": agreement}
        query_pairs[c1].append({**entry, "card": c2})
        query_pairs[c2].append({**entry, "card": c1})

    queries = {}
    for query_card, pairs in sorted(query_pairs.items()):
        if len(pairs) < min_pairs:
            continue

        type_counts: Counter = Counter(p["sim_type"] for p in pairs)
        dominant_type = type_counts.most_common(1)[0][0]
        use_case = TYPE_TO_USE_CASE.get(dominant_type, "functional")

        grades: dict[str, list[str]] = {
            "highly_relevant": [],
            "relevant": [],
            "somewhat_relevant": [],
            "marginally_relevant": [],
            "irrelevant": [],
        }

        for p in sorted(pairs, key=lambda x: x["score"], reverse=True):
            s = p["score"]
            if s >= GRADE_THRESHOLDS["highly_relevant"]:
                grades["highly_relevant"].append(p["card"])
            elif s >= GRADE_THRESHOLDS["relevant"]:
                grades["relevant"].append(p["card"])
            elif s >= GRADE_THRESHOLDS["somewhat_relevant"]:
                grades["somewhat_relevant"].append(p["card"])
            elif s >= GRADE_THRESHOLDS["marginally_relevant"]:
                grades["marginally_relevant"].append(p["card"])
            else:
                grades["irrelevant"].append(p["card"])

        n_agree = sum(1 for p in pairs if p["agreement"] in ("high", "medium"))
        iaa = round(n_agree / len(pairs), 3) if pairs else 0

        queries[query_card] = {"use_case": use_case, **grades, "iaa": iaa}

    return {
        "version": "dialogue_v1",
        "game": game,
        "source": "dialogue_annotations",
        "num_queries": len(queries),
        "queries": queries,
    }


def print_report(game: str, entries: list[dict]) -> None:
    """Print analysis report for one game."""
    n = len(entries)
    print(f"\n{'=' * 60}")
    print(f"  {game.upper()} -- {n} dialogue annotations")
    print(f"{'=' * 60}")

    # Category accuracy
    cat_stats = analyze_category_accuracy(entries)
    print(f"\n  Category accuracy:")
    print(f"  {'category':<20} {'n':>5} {'mean':>6} {'std':>6} {'med':>6} {'range':>12}")
    print(f"  {'-' * 57}")
    for cat, s in cat_stats.items():
        rng = f"[{s['min']:.2f}, {s['max']:.2f}]"
        print(f"  {cat:<20} {s['n']:>5} {s['mean_score']:>6.3f} {s['std']:>6.3f} {s['median']:>6.3f} {rng:>12}")

    # Judge prediction quality
    pred = analyze_judge_prediction(entries)
    if pred["n"] > 0:
        print(f"\n  Judge prediction quality (n={pred['n']}):")
        print(f"    Pearson r:  {pred['pearson_r']:+.3f}  (expected vs actual similarity)")
        print(f"    MAE:        {pred['mae']:.3f}")
        print(f"    RMSE:       {pred['rmse']:.3f}")
        print(f"    Bias:       {pred['bias']:+.3f}  ({'actual > expected' if pred['bias'] > 0 else 'expected > actual'})")

    # Error rates
    err = analyze_error_rates(entries)
    if "hard_negative" in err:
        hn = err["hard_negative"]
        print(f"\n  Hard negative false positive rate:")
        print(f"    {hn['false_positive_count']}/{hn['n']} hard_negatives scored >= 0.50 "
              f"({hn['false_positive_rate']:.1%} FP rate, mean={hn['mean_score']:.3f})")
    if "hidden_substitute" in err:
        hs = err["hidden_substitute"]
        print(f"\n  Hidden substitute false negative rate:")
        print(f"    {hs['false_negative_count']}/{hs['n']} hidden_substitutes scored < 0.50 "
              f"({hs['false_negative_rate']:.1%} FN rate, mean={hs['mean_score']:.3f})")


def main():
    parser = argparse.ArgumentParser(description="Analyze dialogue annotations")
    parser.add_argument("--no-test-sets", action="store_true",
                        help="Skip generating test set files")
    parser.add_argument("--min-pairs", type=int, default=2,
                        help="Minimum pairs per query card in test sets (default: 2)")
    parser.add_argument("--reasons", action="store_true",
                        help="Show top suggestion reasons per category")
    args = parser.parse_args()

    all_entries: dict[str, list[dict]] = {}
    for game in DIALOGUE_FILES:
        entries = load_dialogue_entries(game)
        if entries:
            all_entries[game] = entries

    if not all_entries:
        print("No dialogue checkpoint files found in data/annotations/")
        return 1

    total = sum(len(e) for e in all_entries.values())
    print(f"Dialogue annotation analysis -- {total} pairs across {len(all_entries)} games")

    # Per-game reports
    for game, entries in all_entries.items():
        print_report(game, entries)

    # Aggregate cross-game stats
    all_flat = [e for entries in all_entries.values() for e in entries]
    if len(all_entries) > 1:
        print_report("ALL GAMES", all_flat)

    # Suggestion reasons
    if args.reasons:
        print(f"\n{'=' * 60}")
        print("  Top suggestion reasons by category")
        print(f"{'=' * 60}")
        reasons = aggregate_reasons(all_flat, top_n=5)
        for cat, themes in reasons.items():
            print(f"\n  [{cat}]")
            for theme, count in themes:
                print(f"    ({count:>3}) {theme}")

    # Generate test sets
    if not args.no_test_sets:
        print(f"\n{'=' * 60}")
        print("  Test set generation")
        print(f"{'=' * 60}")
        for game, entries in all_entries.items():
            ts = convert_to_test_set(entries, game, min_pairs=args.min_pairs)
            out_path = OUTPUT_DIR / f"test_set_dialogue_{game}.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w") as f:
                json.dump(ts, f, indent=2, ensure_ascii=False)
                f.write("\n")

            # Grade distribution
            total_by_grade: Counter = Counter()
            for q in ts["queries"].values():
                for grade in ("highly_relevant", "relevant", "somewhat_relevant",
                              "marginally_relevant", "irrelevant"):
                    total_by_grade[grade] += len(q.get(grade, []))

            print(f"\n  {game}: {ts['num_queries']} queries -> {out_path}")
            for grade in ("highly_relevant", "relevant", "somewhat_relevant",
                          "marginally_relevant", "irrelevant"):
                print(f"    {grade}: {total_by_grade[grade]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
