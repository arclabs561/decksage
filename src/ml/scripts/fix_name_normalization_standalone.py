#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Standalone name normalization fix script (no scipy dependency).

This version avoids scipy by using only pandas, numpy, and gensim.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    from gensim.models import KeyedVectors
    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    print(f"Missing dependencies: {e}", file=sys.stderr)


def normalize_card_name(name: str) -> str:
    """Normalize card name for matching."""
    # Remove special characters, lowercase, strip
    normalized = re.sub(r'[^\w\s]', '', name.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def find_name_matches(
    query_name: str,
    candidate_names: list[str],
    threshold: float = 0.8,
) -> list[tuple[str, float]]:
    """Find fuzzy matches for a card name using SequenceMatcher."""
    from difflib import SequenceMatcher
    
    query_norm = normalize_card_name(query_name)
    matches = []
    
    for candidate in candidate_names:
        candidate_norm = normalize_card_name(candidate)
        similarity = SequenceMatcher(None, query_norm, candidate_norm).ratio()
        if similarity >= threshold:
            matches.append((candidate, similarity))
    
    return sorted(matches, key=lambda x: x[1], reverse=True)


def analyze_name_mismatches(
    test_set: dict[str, dict[str, Any]],
    wv: KeyedVectors,
    adj: dict[str, set[str]],
) -> dict[str, Any]:
    """Analyze name mismatches between test set and data."""
    mismatches = {
        "queries_not_in_embeddings": [],
        "queries_not_in_graph": [],
        "queries_not_in_either": [],
        "relevant_cards_not_found": {},
    }
    
    for query, labels in test_set.items():
        in_embeddings = query in wv
        in_graph = query in adj
        
        if not in_embeddings:
            mismatches["queries_not_in_embeddings"].append(query)
        if not in_graph:
            mismatches["queries_not_in_graph"].append(query)
        if not in_embeddings and not in_graph:
            mismatches["queries_not_in_either"].append(query)
        
        # Check if relevant cards exist
        all_relevant = set()
        for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
            all_relevant.update(labels.get(level, []))
        
        missing_in_embed = []
        missing_in_graph = []
        
        for card in all_relevant:
            if card not in wv:
                missing_in_embed.append(card)
            if card not in adj:
                missing_in_graph.append(card)
        
        if missing_in_embed or missing_in_graph:
            mismatches["relevant_cards_not_found"][query] = {
                "missing_in_embeddings": missing_in_embed[:10],  # Limit for readability
                "missing_in_graph": missing_in_graph[:10],
                "total_relevant": len(all_relevant),
            }
    
    return mismatches


def create_name_mapping(
    test_set: dict[str, dict[str, Any]],
    wv: KeyedVectors,
    adj: dict[str, set[str]],
) -> dict[str, str]:
    """Create mapping from test set names to actual names in data."""
    mapping = {}
    
    # Get all names from embeddings and graph
    embed_names = set(wv.index_to_key)
    graph_names = set(adj.keys())
    all_data_names = embed_names | graph_names
    
    print(f"  Total unique names in data: {len(all_data_names):,}")
    print(f"  Names in embeddings: {len(embed_names):,}")
    print(f"  Names in graph: {len(graph_names):,}")
    
    # Map test set queries
    print(f"\n  Mapping {len(test_set)} queries...")
    for i, query in enumerate(test_set.keys(), 1):
        if i % 10 == 0:
            print(f"    Progress: {i}/{len(test_set)}")
        
        if query in all_data_names:
            mapping[query] = query
        else:
            # Try fuzzy matching
            matches = find_name_matches(query, list(all_data_names), threshold=0.9)
            if matches:
                mapping[query] = matches[0][0]
                if query != matches[0][0]:
                    print(f"    Mapped: '{query}' -> '{matches[0][0]}' (similarity: {matches[0][1]:.3f})")
            else:
                mapping[query] = query  # Keep original if no match
    
    # Map relevant cards
    print(f"\n  Mapping relevant cards...")
    all_relevant_cards = set()
    for labels in test_set.values():
        for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
            all_relevant_cards.update(labels.get(level, []))
    
    print(f"  Total unique relevant cards: {len(all_relevant_cards):,}")
    for i, card in enumerate(all_relevant_cards, 1):
        if i % 100 == 0:
            print(f"    Progress: {i}/{len(all_relevant_cards)}")
        
        if card not in mapping:
            if card in all_data_names:
                mapping[card] = card
            else:
                matches = find_name_matches(card, list(all_data_names), threshold=0.9)
                if matches:
                    mapping[card] = matches[0][0]
                else:
                    mapping[card] = card
    
    return mapping


def main() -> int:
    """Fix name normalization."""
    parser = argparse.ArgumentParser(description="Fix name normalization")
    parser.add_argument(
        "--test-set",
        type=str,
        default="experiments/test_set_canonical_magic.json",
        help="Test set path",
    )
    parser.add_argument(
        "--embeddings",
        type=str,
        default="data/embeddings/magic_128d_test_pecanpy.wv",
        help="Embeddings file",
    )
    parser.add_argument(
        "--pairs-csv",
        type=str,
        default="data/processed/pairs_large.csv",
        help="Pairs CSV",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="experiments/name_mapping.json",
        help="Output mapping JSON",
    )
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("❌ Missing dependencies (pandas, gensim)", file=sys.stderr)
        return 1
    
    print("=" * 70)
    print("Name Normalization Analysis")
    print("=" * 70)
    print()
    
    # Load data
    test_set_path = Path(args.test_set)
    if not test_set_path.exists():
        print(f"❌ Test set not found: {test_set_path}", file=sys.stderr)
        return 1
    
    with open(test_set_path) as f:
        test_data = json.load(f)
        test_set = test_data.get("queries", test_data)
    
    print(f"📊 Loaded test set: {len(test_set)} queries")
    
    embed_path = Path(args.embeddings)
    if not embed_path.exists():
        print(f"❌ Embeddings not found: {embed_path}", file=sys.stderr)
        return 1
    
    print(f"📊 Loading embeddings from {embed_path}...")
    wv = KeyedVectors.load(str(embed_path))
    print(f"📊 Loaded embeddings: {len(wv):,} cards")
    
    pairs_csv = Path(args.pairs_csv)
    if not pairs_csv.exists():
        print(f"❌ Pairs CSV not found: {pairs_csv}", file=sys.stderr)
        return 1
    
    print(f"📊 Loading graph from {pairs_csv}...")
    df = pd.read_csv(pairs_csv)
    adj: dict[str, set[str]] = {}
    for _, row in df.iterrows():
        card1, card2 = row["NAME_1"], row["NAME_2"]
        if card1 not in adj:
            adj[card1] = set()
        if card2 not in adj:
            adj[card2] = set()
        adj[card1].add(card2)
        adj[card2].add(card1)
    print(f"📊 Loaded graph: {len(adj):,} cards")
    print()
    
    # Analyze mismatches
    print("📊 Analyzing name mismatches...")
    mismatches = analyze_name_mismatches(test_set, wv, adj)
    
    print(f"  Queries not in embeddings: {len(mismatches['queries_not_in_embeddings'])}")
    print(f"  Queries not in graph: {len(mismatches['queries_not_in_graph'])}")
    print(f"  Queries not in either: {len(mismatches['queries_not_in_either'])}")
    print(f"  Queries with missing relevant cards: {len(mismatches['relevant_cards_not_found'])}")
    print()
    
    # Create mapping
    print("📊 Creating name mapping...")
    mapping = create_name_mapping(test_set, wv, adj)
    
    # Save mapping
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump({
            "mismatches": mismatches,
            "mapping": mapping,
            "stats": {
                "total_queries": len(test_set),
                "queries_mapped": len([q for q in test_set.keys() if q in mapping]),
                "total_mappings": len(mapping),
                "exact_matches": len([k for k, v in mapping.items() if k == v]),
                "fuzzy_matches": len([k for k, v in mapping.items() if k != v]),
            },
        }, f, indent=2)
    
    print(f"✅ Results saved to {output_path}")
    
    # Show sample mismatches
    if mismatches["relevant_cards_not_found"]:
        print()
        print("📊 Sample mismatches:")
        for query, info in list(mismatches["relevant_cards_not_found"].items())[:3]:
            print(f"  {query}:")
            if info["missing_in_embeddings"]:
                print(f"    Missing in embeddings: {info['missing_in_embeddings'][:5]}")
            if info["missing_in_graph"]:
                print(f"    Missing in graph: {info['missing_in_graph'][:5]}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

