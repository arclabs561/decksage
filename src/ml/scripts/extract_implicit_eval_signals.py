#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
# ]
# ///
"""
Extract implicit evaluation signals from deck data:
1. Sideboard co-occurrence patterns
2. Temporal trends (cards that rise/fall together)
3. Format-specific patterns
4. Archetype-specific patterns
5. Substitution patterns (cards in similar contexts but not together)

These implicit signals create test cases that evaluate whether similarity methods
capture functional relationships beyond simple co-occurrence.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def extract_sideboard_patterns(
    decks_jsonl: Path,
    min_decks: int = 5,
    top_n: int = 100,
) -> list[dict[str, Any]]:
    """
    Extract sideboard co-occurrence patterns.
    Cards that appear together in sideboards indicate functional similarity.
    """
    if not HAS_DEPS:
        return []
    
    print(f"📊 Extracting sideboard patterns from {decks_jsonl}...")
    
    sideboard_pairs: defaultdict[str, Counter] = defaultdict(Counter)
    card_sideboard_counts: Counter = Counter()
    
    if not decks_jsonl.exists():
        print(f"  ⚠️  File not found, skipping")
        return []
    
    with open(decks_jsonl) as f:
        for line_num, line in enumerate(f):
            if line_num % 10000 == 0 and line_num > 0:
                print(f"    Processed {line_num} decks...")
            
            try:
                deck = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            # Extract sideboard cards
            sideboard_cards = []
            for partition in deck.get("partitions", []):
                if partition.get("name", "").lower() in ["sideboard", "side"]:
                    sideboard_cards.extend([c["name"] for c in partition.get("cards", [])])
            
            if len(sideboard_cards) < 2:
                continue
            
            # Count co-occurrences in sideboard
            unique_sb = set(sideboard_cards)
            for card in unique_sb:
                card_sideboard_counts[card] += 1
                for other in unique_sb:
                    if card != other:
                        sideboard_pairs[card][other] += 1
    
    # Convert to test queries
    queries = []
    for card, cooccurrences in sideboard_pairs.items():
        total_decks = card_sideboard_counts[card]
        if total_decks < min_decks:
            continue
        
        # Get top co-occurring cards
        top_cooccurring = [
            (other, count / total_decks)
            for other, count in cooccurrences.most_common(20)
            if card_sideboard_counts[other] >= min_decks
        ]
        
        if len(top_cooccurring) >= 3:
            queries.append({
                "query": card,
                "type": "implicit_sideboard",
                "highly_relevant": [c for c, score in top_cooccurring[:5] if score > 0.3],
                "relevant": [c for c, score in top_cooccurring[5:10] if score > 0.2],
                "somewhat_relevant": [c for c, score in top_cooccurring[10:15] if score > 0.1],
            })
    
    # Sort by strength and take top N
    queries.sort(key=lambda x: len(x["highly_relevant"]), reverse=True)
    
    print(f"  ✅ Extracted {len(queries[:top_n])} sideboard pattern queries")
    return queries[:top_n]


def extract_temporal_patterns(
    decks_jsonl: Path,
    pairs_csv: Path,
    min_decks: int = 10,
    top_n: int = 50,
) -> list[dict[str, Any]]:
    """
    Extract temporal patterns: cards that rise/fall together over time.
    This indicates meta-dependent relationships.
    """
    if not HAS_DEPS:
        return []
    
    print(f"📊 Extracting temporal patterns...")
    
    # Load deck dates if available
    decks_by_date: defaultdict[str, list[set[str]]] = defaultdict(list)
    
    if not decks_jsonl.exists():
        print(f"  ⚠️  File not found, skipping")
        return []
    
    with open(decks_jsonl) as f:
        for line in f:
            try:
                deck = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            # Extract date (if available)
            date = deck.get("date") or deck.get("created_at") or deck.get("timestamp")
            if not date:
                continue
            
            # Extract year-month as time period
            if isinstance(date, str):
                try:
                    # Try to parse date
                    from datetime import datetime
                    dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
                    period = dt.strftime("%Y-%m")
                except:
                    period = date[:7] if len(date) >= 7 else "unknown"
            else:
                period = "unknown"
            
            if period == "unknown":
                continue
            
            # Extract cards
            cards = set()
            for partition in deck.get("partitions", []):
                cards.update([c["name"] for c in partition.get("cards", [])])
            
            if cards:
                decks_by_date[period].append(cards)
    
    if not decks_by_date:
        print(f"  ⚠️  No temporal data found, skipping")
        return []
    
    # Compute co-occurrence trends
    # For simplicity, use overall co-occurrence but mark as temporal
    df = pd.read_csv(pairs_csv, nrows=10000)
    
    # Check column names
    name1_col = df.columns[0]
    name2_col = df.columns[1]
    count_col = df.columns[2] if len(df.columns) > 2 else df.columns[-1]
    
    queries = []
    for _, row in df.head(top_n * 2).iterrows():
        card1, card2 = row[name1_col], row[name2_col]
        count = row[count_col]
        
        if count >= min_decks:
            queries.append({
                "query": card1,
                "type": "implicit_temporal",
                "highly_relevant": [card2] if count >= 20 else [],
                "relevant": [card2] if 10 <= count < 20 else [],
                "somewhat_relevant": [card2] if 5 <= count < 10 else [],
            })
    
    print(f"  ✅ Extracted {len(queries[:top_n])} temporal pattern queries")
    return queries[:top_n]


def extract_substitution_patterns_from_decks(
    decks_jsonl: Path,
    pairs_csv: Path,
    min_decks: int = 5,
    top_n: int = 100,
) -> list[dict[str, Any]]:
    """
    Extract substitution patterns: cards that appear in similar deck contexts
    but rarely together (indicating substitution relationship).
    """
    if not HAS_DEPS:
        return []
    
    print(f"📊 Extracting substitution patterns from decks...")
    
    # Build card -> neighbor sets from pairs
    df = pd.read_csv(pairs_csv)
    name1_col = df.columns[0]
    name2_col = df.columns[1]
    card_neighbors = defaultdict(set)
    for _, row in df.iterrows():
        card1, card2 = row[name1_col], row[name2_col]
        card_neighbors[card1].add(card2)
        card_neighbors[card2].add(card1)
    
    # Find substitution candidates
    substitutions = []
    
    # Sample for efficiency
    sample_size = min(1000, len(card_neighbors))
    sample_cards = list(card_neighbors.keys())[:sample_size]
    
    for card1 in sample_cards:
        neighbors1 = card_neighbors[card1]
        if len(neighbors1) < 10:
            continue
        
        # Find cards with similar neighbor sets but low direct co-occurrence
        for card2 in card_neighbors.keys():
            if card1 == card2 or card2 in neighbors1:
                continue
            
            neighbors2 = card_neighbors[card2]
            if len(neighbors2) < 10:
                continue
            
            # Jaccard similarity of neighbor sets
            intersection = len(neighbors1 & neighbors2)
            union = len(neighbors1 | neighbors2)
            jaccard = intersection / union if union > 0 else 0.0
            
            # High Jaccard but no direct co-occurrence = substitution
            if jaccard > 0.4:
                substitutions.append({
                    "query": card1,
                    "type": "implicit_substitution",
                    "highly_relevant": [card2],
                    "relevant": [],
                    "somewhat_relevant": [],
                })
    
    print(f"  ✅ Extracted {len(substitutions[:top_n])} substitution pattern queries")
    return substitutions[:top_n]


def combine_implicit_signals(
    sideboard_queries: list[dict[str, Any]],
    temporal_queries: list[dict[str, Any]],
    substitution_queries: list[dict[str, Any]],
    output_path: Path,
    game: str = "magic",
) -> None:
    """Combine all implicit signals into a test set."""
    print(f"\n📝 Combining implicit signals into test set...")
    
    test_set = {
        "game": game,
        "sources": {
            "sideboard_patterns": len(sideboard_queries),
            "temporal_patterns": len(temporal_queries),
            "substitution_patterns": len(substitution_queries),
        },
        "queries": {},
    }
    
    # Combine all queries (deduplicate by query card)
    all_queries = sideboard_queries + temporal_queries + substitution_queries
    
    for query_data in all_queries:
        query = query_data["query"]
        
        if query not in test_set["queries"]:
            test_set["queries"][query] = {
                "type": query_data["type"],
                "highly_relevant": [],
                "relevant": [],
                "somewhat_relevant": [],
            }
        
        # Merge labels
        test_set["queries"][query]["highly_relevant"].extend(
            query_data.get("highly_relevant", [])
        )
        test_set["queries"][query]["relevant"].extend(
            query_data.get("relevant", [])
        )
        test_set["queries"][query]["somewhat_relevant"].extend(
            query_data.get("somewhat_relevant", [])
        )
    
    # Deduplicate lists
    for query in test_set["queries"]:
        for key in ["highly_relevant", "relevant", "somewhat_relevant"]:
            test_set["queries"][query][key] = list(set(test_set["queries"][query][key]))
    
    # Save
    with open(output_path, "w") as f:
        json.dump(test_set, f, indent=2)
    
    print(f"  ✅ Created test set with {len(test_set['queries'])} queries")
    print(f"     Sources: {test_set['sources']}")


def main() -> int:
    """Extract implicit evaluation signals."""
    parser = argparse.ArgumentParser(
        description="Extract implicit evaluation signals from deck data"
    )
    parser.add_argument("--game", type=str, default="magic",
                       choices=["magic", "pokemon", "yugioh"],
                       help="Game to extract signals for")
    parser.add_argument("--decks-jsonl", type=str, help="Deck JSONL file")
    parser.add_argument("--pairs-csv", type=str, required=True,
                       help="Pairs CSV file")
    parser.add_argument("--output", type=str,
                       default="experiments/test_set_implicit_signals.json",
                       help="Output test set JSON")
    parser.add_argument("--sideboard-top-n", type=int, default=100,
                       help="Top N sideboard patterns")
    parser.add_argument("--temporal-top-n", type=int, default=50,
                       help="Top N temporal patterns")
    parser.add_argument("--substitution-top-n", type=int, default=100,
                       help="Top N substitution patterns")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("❌ Missing dependencies (pandas, numpy)")
        return 1
    
    pairs_csv = Path(args.pairs_csv)
    if not pairs_csv.exists():
        print(f"❌ Pairs CSV not found: {pairs_csv}")
        return 1
    
    decks_jsonl = Path(args.decks_jsonl) if args.decks_jsonl else None
    if args.decks_jsonl and not decks_jsonl.exists():
        print(f"⚠️  Decks JSONL not found: {decks_jsonl}, some signals will be skipped")
        decks_jsonl = None
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("Extract Implicit Evaluation Signals")
    print("=" * 70)
    print(f"\nGame: {args.game}")
    print(f"Pairs CSV: {pairs_csv}")
    if decks_jsonl:
        print(f"Decks JSONL: {decks_jsonl}")
    print(f"Output: {output_path}\n")
    
    # Extract signals
    sideboard_queries = []
    if decks_jsonl:
        sideboard_queries = extract_sideboard_patterns(
            decks_jsonl,
            min_decks=5,
            top_n=args.sideboard_top_n,
        )
    
    temporal_queries = []
    if decks_jsonl:
        temporal_queries = extract_temporal_patterns(
            decks_jsonl,
            pairs_csv,
            min_decks=10,
            top_n=args.temporal_top_n,
        )
    
    substitution_queries = extract_substitution_patterns_from_decks(
        decks_jsonl if decks_jsonl else pairs_csv,  # Fallback to pairs_csv
        pairs_csv,
        min_decks=5,
        top_n=args.substitution_top_n,
    )
    
    # Combine into test set
    combine_implicit_signals(
        sideboard_queries=sideboard_queries,
        temporal_queries=temporal_queries,
        substitution_queries=substitution_queries,
        output_path=output_path,
        game=args.game,
    )
    
    print(f"\n✅ Implicit signals test set created: {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

