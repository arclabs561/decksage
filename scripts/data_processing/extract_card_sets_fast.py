#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mlxtend", "pandas"]
# ///
"""
Fast card set extraction using FP-Growth (10-100x faster than Apriori).

Uses mlxtend's FP-Growth implementation with sparse transaction encoding.
Replaces the old Apriori-based extract_card_sets.py (deleted) with same output format.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/data_processing/extract_card_sets_fast.py \
        --decks data/decks/decks_magic_goldfish.jsonl \
        --output data/processed/card_sets_magic_goldfish.jsonl \
        --min-support 10 --min-lift 2.0 --max-size 4 --exclude-basics
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from mlxtend.frequent_patterns import fpgrowth
from mlxtend.preprocessing import TransactionEncoder


def load_decks(path: Path) -> list[list[str]]:
    """Load decks as lists of card names."""
    decks = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            deck = json.loads(line)
            cards = []
            seen = set()
            for card in deck.get("cards", []):
                name = card.get("name", "")
                if not name or name in seen:
                    continue
                if name.startswith("Card_") and name[5:].isdigit():
                    continue
                cards.append(name)
                seen.add(name)
            if len(cards) >= 3:
                decks.append(cards)
    return decks


def compute_lift(
    card_set: frozenset[str],
    support_pct: float,
    item_support: dict[str, float],
) -> float:
    """Compute lift: P(A∩B∩C) / (P(A)*P(B)*P(C))."""
    p_individual = 1.0
    for card in card_set:
        p = item_support.get(card, 0.0)
        if p == 0:
            return float("inf")
        p_individual *= p
    if p_individual == 0:
        return float("inf")
    return support_pct / p_individual


def main():
    parser = argparse.ArgumentParser(description="Fast card set extraction via FP-Growth")
    parser.add_argument("--decks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-support", type=int, default=10,
                        help="Minimum deck count (default: 10)")
    parser.add_argument("--min-lift", type=float, default=2.0,
                        help="Minimum lift (default: 2.0)")
    parser.add_argument("--max-size", type=int, default=4,
                        help="Maximum set size (default: 4)")
    parser.add_argument("--top-k", type=int, default=10000,
                        help="Keep top K sets by lift (default: 10000)")
    parser.add_argument("--game", type=str, default=None)
    parser.add_argument("--exclude-energy", action="store_true")
    parser.add_argument("--exclude-basics", action="store_true")
    args = parser.parse_args()

    if not args.decks.exists():
        print(f"Error: {args.decks} not found", file=sys.stderr)
        return 1

    print(f"Loading decks from {args.decks}...", flush=True)
    decks = load_decks(args.decks)
    total_decks = len(decks)
    print(f"  {total_decks:,} decks loaded", flush=True)

    if args.exclude_basics:
        basics = {"Plains", "Island", "Swamp", "Mountain", "Forest",
                  "Snow-Covered Plains", "Snow-Covered Island",
                  "Snow-Covered Swamp", "Snow-Covered Mountain",
                  "Snow-Covered Forest", "Wastes"}
        decks = [[c for c in d if c not in basics] for d in decks]
        decks = [d for d in decks if len(d) >= 3]
        print(f"  After removing basics: {len(decks):,} decks", flush=True)

    if args.exclude_energy:
        decks = [[c for c in d if "Energy" not in c] for d in decks]
        decks = [d for d in decks if len(d) >= 3]
        print(f"  After removing energy: {len(decks):,} decks", flush=True)

    total_decks = len(decks)
    min_support_pct = args.min_support / total_decks

    # Pre-filter: only keep cards that appear in >= min_support decks
    card_counts = Counter()
    for deck in decks:
        for card in deck:
            card_counts[card] += 1
    frequent_cards = {c for c, n in card_counts.items() if n >= args.min_support}
    decks_filtered = [[c for c in d if c in frequent_cards] for d in decks]
    decks_filtered = [d for d in decks_filtered if len(d) >= 2]

    print(f"  {len(frequent_cards):,} cards with support >= {args.min_support}", flush=True)
    print(f"  {len(decks_filtered):,} decks after card filtering", flush=True)

    # Encode transactions as sparse DataFrame
    print("Encoding transactions (sparse)...", flush=True)
    t0 = time.time()
    te = TransactionEncoder()
    te_array = te.fit(decks_filtered).transform(decks_filtered, sparse=True)
    df = pd.DataFrame.sparse.from_spmatrix(te_array, columns=te.columns_)
    print(f"  Encoded in {time.time() - t0:.1f}s ({df.shape[0]:,} x {df.shape[1]:,})", flush=True)

    # Run FP-Growth
    print(f"Running FP-Growth (min_support={min_support_pct:.4f}, max_len={args.max_size})...", flush=True)
    t0 = time.time()
    freq_itemsets = fpgrowth(
        df,
        min_support=min_support_pct,
        max_len=args.max_size,
        use_colnames=True,
    )
    fpg_time = time.time() - t0
    print(f"  Found {len(freq_itemsets):,} frequent itemsets in {fpg_time:.1f}s", flush=True)

    if freq_itemsets.empty:
        print("No frequent itemsets found.", flush=True)
        return 0

    # Filter: size >= 2, compute lift
    print("Computing lift and filtering...", flush=True)
    item_support = {}
    single_items = freq_itemsets[freq_itemsets["itemsets"].apply(len) == 1]
    for _, row in single_items.iterrows():
        item = list(row["itemsets"])[0]
        item_support[item] = row["support"]

    results = []
    for _, row in freq_itemsets.iterrows():
        items = row["itemsets"]
        if len(items) < 2:
            continue
        support_pct = row["support"]
        support_count = int(round(support_pct * total_decks))

        lift = compute_lift(items, support_pct, item_support)
        if lift < args.min_lift:
            continue

        results.append({
            "cards": sorted(items),
            "size": len(items),
            "support": support_count,
            "support_pct": round(support_pct * 100, 1),
            "lift": round(lift, 3),
            "total_decks": total_decks,
        })

    # Take top-k per size to avoid larger sets dominating
    by_size_lists: dict[int, list] = defaultdict(list)
    for r in results:
        by_size_lists[r["size"]].append(r)

    per_size_k = max(1, args.top_k // max(len(by_size_lists), 1))
    capped = []
    for size in sorted(by_size_lists):
        size_results = sorted(by_size_lists[size], key=lambda x: -x["lift"])
        capped.extend(size_results[:per_size_k])
    results = sorted(capped, key=lambda x: -x["lift"])
    if len(results) > args.top_k:
        results = results[:args.top_k]
    print(f"  Kept top {per_size_k} per size ({len(by_size_lists)} sizes), total {len(results)}", flush=True)

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    elapsed = time.time() - t0
    with open(args.output, "w") as f:
        meta = {
            "_meta": True,
            "game": args.game,
            "source": str(args.decks),
            "min_support": args.min_support,
            "min_lift": args.min_lift,
            "max_size": args.max_size,
            "total_decks": total_decks,
            "total_sets": len(results),
            "method": "fpgrowth",
        }
        f.write(json.dumps(meta) + "\n")
        for item in results:
            f.write(json.dumps(item) + "\n")

    # Summary
    by_size = defaultdict(list)
    for r in results:
        by_size[r["size"]].append(r)

    print(f"\nResults:", flush=True)
    print(f"  Total sets with lift >= {args.min_lift}: {len(results)}", flush=True)
    for size in sorted(by_size):
        items = by_size[size]
        avg_lift = sum(i["lift"] for i in items) / len(items) if items else 0
        print(f"  {size}-card sets: {len(items)} (avg lift: {avg_lift:.2f})", flush=True)

    for size in sorted(by_size):
        items = sorted(by_size[size], key=lambda x: -x["lift"])[:3]
        print(f"\n  Top {size}-card sets:", flush=True)
        for item in items:
            cards = ", ".join(item["cards"])
            print(f"    lift={item['lift']:.2f}  support={item['support']}  [{cards}]", flush=True)

    print(f"\nWritten {len(results)} sets to {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
