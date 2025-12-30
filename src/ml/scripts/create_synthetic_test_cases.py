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
Create synthetic test cases from known patterns.

Generates test cases based on:
1. Functional roles (removal, card draw, ramp, etc.)
2. Archetype clusters (from embeddings)
3. Format-specific patterns
4. Power level tiers
5. Mana cost patterns
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    import numpy as np
    from gensim.models import KeyedVectors
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def create_functional_role_queries(
    pairs_csv: Path,
    embedding_path: Path | None = None,
    num_queries: int = 30,
) -> list[dict[str, Any]]:
    """
    Create synthetic queries based on functional roles.
    
    Groups cards by function (removal, card draw, ramp, etc.) and creates
    test cases where cards in the same functional role should be similar.
    """
    if not HAS_DEPS:
        return []
    
    print(f"📊 Creating functional role queries...")
    
    df = pd.read_csv(pairs_csv, nrows=10000)
    name1_col = df.columns[0]
    name2_col = df.columns[1]
    count_col = df.columns[2] if len(df.columns) > 2 else df.columns[-1]
    
    # Build card frequency
    card_freq = Counter()
    for _, row in df.iterrows():
        card_freq[row[name1_col]] += row[count_col]
        card_freq[row[name2_col]] += row[count_col]
    
    # Sample high-frequency cards as functional role seeds
    top_cards = [card for card, _ in card_freq.most_common(num_queries * 2)]
    
    queries = []
    for card in random.sample(top_cards, min(num_queries, len(top_cards))):
        # Find cards that co-occur with this card (likely same functional role)
        cooccurring = set()
        for _, row in df[df[name1_col] == card].iterrows():
            cooccurring.add(row[name2_col])
        for _, row in df[df[name2_col] == card].iterrows():
            cooccurring.add(row[name1_col])
        
        cooccurring_list = list(cooccurring)[:15]
        if len(cooccurring_list) >= 5:
            queries.append({
                "query": card,
                "type": "synthetic_functional_role",
                "highly_relevant": cooccurring_list[:5],
                "relevant": cooccurring_list[5:10] if len(cooccurring_list) >= 10 else [],
                "somewhat_relevant": cooccurring_list[10:15] if len(cooccurring_list) >= 15 else [],
            })
    
    print(f"  ✅ Created {len(queries)} functional role queries")
    return queries


def create_archetype_cluster_queries(
    embedding_path: Path,
    pairs_csv: Path,
    num_queries: int = 40,
    cluster_size: int = 10,
) -> list[dict[str, Any]]:
    """
    Create synthetic queries from embedding clusters.
    
    Uses K-means or similar clustering on embeddings to identify archetype groups,
    then creates test cases within clusters.
    """
    if not HAS_DEPS:
        return []
    
    print(f"📊 Creating archetype cluster queries...")
    
    try:
        wv = KeyedVectors.load(str(embedding_path))
    except Exception as e:
        print(f"  ⚠️  Could not load embeddings: {e}")
        return []
    
    # Sample cards from vocabulary
    vocab_cards = list(wv.key_to_index.keys())
    sample_size = min(num_queries * 2, len(vocab_cards))
    sample_cards = random.sample(vocab_cards, sample_size)
    
    queries = []
    for card in sample_cards[:num_queries]:
        try:
            # Get similar cards from embedding
            similar = wv.most_similar(card, topn=cluster_size)
            
            queries.append({
                "query": card,
                "type": "synthetic_archetype_cluster",
                "highly_relevant": [c for c, _ in similar[:5]],
                "relevant": [c for c, _ in similar[5:8]],
                "somewhat_relevant": [c for c, _ in similar[8:10]],
            })
        except KeyError:
            continue
    
    print(f"  ✅ Created {len(queries)} archetype cluster queries")
    return queries


def create_power_level_queries(
    pairs_csv: Path,
    num_queries: int = 20,
) -> list[dict[str, Any]]:
    """
    Create synthetic queries based on power level tiers.
    
    Cards that appear in similar power-level contexts should be similar.
    """
    if not HAS_DEPS:
        return []
    
    print(f"📊 Creating power level queries...")
    
    df = pd.read_csv(pairs_csv, nrows=10000)
    name1_col = df.columns[0]
    name2_col = df.columns[1]
    count_col = df.columns[2] if len(df.columns) > 2 else df.columns[-1]
    
    # Build card frequency (proxy for power level - more frequent = more powerful/played)
    card_freq = Counter()
    for _, row in df.iterrows():
        card_freq[row[name1_col]] += row[count_col]
        card_freq[row[name2_col]] += row[count_col]
    
    # Group cards by frequency tiers
    tier_size = len(card_freq) // 5  # 5 tiers
    sorted_cards = sorted(card_freq.items(), key=lambda x: x[1], reverse=True)
    
    queries = []
    for tier in range(5):
        tier_cards = [card for card, _ in sorted_cards[tier * tier_size:(tier + 1) * tier_size]]
        
        # Sample from tier
        sample_size = min(num_queries // 5, len(tier_cards))
        if sample_size == 0:
            continue
        
        for card in random.sample(tier_cards, sample_size):
            # Find other cards in same tier
            tier_mates = [c for c in tier_cards if c != card][:10]
            
            if len(tier_mates) >= 3:
                queries.append({
                    "query": card,
                    "type": "synthetic_power_level",
                    "highly_relevant": tier_mates[:3],
                    "relevant": tier_mates[3:6] if len(tier_mates) >= 6 else [],
                    "somewhat_relevant": tier_mates[6:10] if len(tier_mates) >= 10 else [],
                })
    
    print(f"  ✅ Created {len(queries)} power level queries")
    return queries


def create_format_specific_queries(
    pairs_csv: Path,
    num_queries: int = 25,
) -> list[dict[str, Any]]:
    """
    Create synthetic queries for format-specific patterns.
    
    Cards that appear in similar format contexts should be similar.
    """
    if not HAS_DEPS:
        return []
    
    print(f"📊 Creating format-specific queries...")
    
    # For now, use overall co-occurrence as proxy
    # In production, would parse deck JSONL for format metadata
    df = pd.read_csv(pairs_csv, nrows=10000)
    name1_col = df.columns[0]
    name2_col = df.columns[1]
    count_col = df.columns[2] if len(df.columns) > 2 else df.columns[-1]
    
    # High co-occurrence = format staples together
    df_sorted = df.sort_values(count_col, ascending=False)
    
    queries = []
    for _, row in df_sorted.head(num_queries * 2).iterrows():
        card1, card2 = row[name1_col], row[name2_col]
        count = row[count_col]
        
        if count >= 20:  # High co-occurrence threshold
            queries.append({
                "query": card1,
                "type": "synthetic_format_specific",
                "highly_relevant": [card2],
                "relevant": [],
                "somewhat_relevant": [],
            })
        
        if len(queries) >= num_queries:
            break
    
    print(f"  ✅ Created {len(queries)} format-specific queries")
    return queries


def combine_synthetic_queries(
    functional_queries: list[dict[str, Any]],
    archetype_queries: list[dict[str, Any]],
    power_level_queries: list[dict[str, Any]],
    format_queries: list[dict[str, Any]],
    output_path: Path,
    game: str = "magic",
) -> None:
    """Combine all synthetic queries into a test set."""
    print(f"\n📝 Combining synthetic queries...")
    
    all_queries = {}
    
    for query_data in functional_queries + archetype_queries + power_level_queries + format_queries:
        query = query_data["query"]
        if query not in all_queries:
            all_queries[query] = {
                "type": query_data["type"],
                "highly_relevant": [],
                "relevant": [],
                "somewhat_relevant": [],
            }
        
        # Merge labels
        for level in ["highly_relevant", "relevant", "somewhat_relevant"]:
            all_queries[query][level].extend(query_data.get(level, []))
    
    # Deduplicate
    for query in all_queries:
        for level in ["highly_relevant", "relevant", "somewhat_relevant"]:
            all_queries[query][level] = list(set(all_queries[query][level]))
    
    test_set = {
        "game": game,
        "sources": {
            "functional_role": len(functional_queries),
            "archetype_cluster": len(archetype_queries),
            "power_level": len(power_level_queries),
            "format_specific": len(format_queries),
        },
        "queries": all_queries,
    }
    
    with open(output_path, "w") as f:
        json.dump(test_set, f, indent=2)
    
    print(f"  ✅ Created test set with {len(all_queries)} queries")
    print(f"     Sources: {test_set['sources']}")


def main() -> int:
    """Create synthetic test cases."""
    parser = argparse.ArgumentParser(
        description="Create synthetic test cases from known patterns"
    )
    parser.add_argument("--game", type=str, default="magic",
                       choices=["magic", "pokemon", "yugioh"],
                       help="Game to create test cases for")
    parser.add_argument("--pairs-csv", type=str, required=True,
                       help="Pairs CSV file")
    parser.add_argument("--embedding", type=str, help="Embedding file (.wv)")
    parser.add_argument("--output", type=str,
                       default="experiments/test_set_synthetic.json",
                       help="Output test set JSON")
    parser.add_argument("--functional-num", type=int, default=30,
                       help="Number of functional role queries")
    parser.add_argument("--archetype-num", type=int, default=40,
                       help="Number of archetype cluster queries")
    parser.add_argument("--power-level-num", type=int, default=20,
                       help="Number of power level queries")
    parser.add_argument("--format-num", type=int, default=25,
                       help="Number of format-specific queries")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("❌ Missing dependencies")
        return 1
    
    pairs_csv = Path(args.pairs_csv)
    if not pairs_csv.exists():
        print(f"❌ Pairs CSV not found: {pairs_csv}")
        return 1
    
    embedding_path = Path(args.embedding) if args.embedding else None
    if args.embedding and embedding_path and not embedding_path.exists():
        print(f"⚠️  Embedding not found: {embedding_path}, continuing without archetype clusters")
        embedding_path = None
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("Create Synthetic Test Cases")
    print("=" * 70)
    print(f"\nGame: {args.game}")
    print(f"Pairs CSV: {pairs_csv}")
    if embedding_path:
        print(f"Embedding: {embedding_path}")
    print(f"Output: {output_path}\n")
    
    # Generate all synthetic query types
    functional_queries = create_functional_role_queries(
        pairs_csv,
        embedding_path=embedding_path,
        num_queries=args.functional_num,
    )
    
    archetype_queries = []
    if embedding_path:
        archetype_queries = create_archetype_cluster_queries(
            embedding_path,
            pairs_csv,
            num_queries=args.archetype_num,
        )
    
    power_level_queries = create_power_level_queries(
        pairs_csv,
        num_queries=args.power_level_num,
    )
    
    format_queries = create_format_specific_queries(
        pairs_csv,
        num_queries=args.format_num,
    )
    
    # Combine into test set
    combine_synthetic_queries(
        functional_queries=functional_queries,
        archetype_queries=archetype_queries,
        power_level_queries=power_level_queries,
        format_queries=format_queries,
        output_path=output_path,
        game=args.game,
    )
    
    print(f"\n✅ Synthetic test set created: {output_path}")
    print(f"   Total queries: {len(functional_queries) + len(archetype_queries) + len(power_level_queries) + len(format_queries)}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

