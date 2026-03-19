#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy>=1.24.0",
#     "gensim>=4.3.0",
#     "scikit-learn>=1.3.0",
# ]
# ///
"""
Generate diverse annotation pairs that break the embedding echo chamber.

Current annotations only evaluate top-10 embedding neighbors, creating
a self-reinforcing loop. This script generates pairs from 4 sources:

1. TEXT SIMILARITY: cards with similar oracle text (TF-IDF cosine) but
   low embedding similarity. These are functional substitutes the
   embedding model misses.

2. ROLE-MATCHED: cards sharing the same functional role (removal, draw,
   ramp) but from different archetypes/colors. Cross-archetype substitutes.

3. HARD NEGATIVES: cards with high embedding similarity but different
   function (same set, same CMC, but different role). Training signal
   for what NOT to recommend.

4. BUDGET PAIRS: cheap card + expensive functional equivalent. For
   upgrade/downgrade evaluation.

Output: JSONL file with diverse pairs, ready for LLM annotation.

Usage:
    uv run scripts/annotation/generate_diverse_pairs.py --game magic --output data/annotations/diverse_pairs_magic.jsonl
    uv run scripts/annotation/generate_diverse_pairs.py --all-games
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from gensim.models import KeyedVectors
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

EMBEDDING_FILES = {
    "magic": "magic_v5_fused",
    "pokemon": "pokemon_v6_fused_a09",
    "yugioh": "yugioh_v5_fused_a09",
}

# Role keywords to detect from oracle text
ROLE_KEYWORDS = {
    "removal": ["destroy", "exile", "sacrifice", "deals damage", "-X/-X", "fight"],
    "draw": ["draw a card", "draw cards", "draw two", "draw three", "look at the top"],
    "counter": ["counter target", "can't be cast", "negate"],
    "ramp": [
        "add {",
        "add one mana",
        "search your library for a",
        "land card",
        "put it onto the battlefield",
    ],
    "threat": ["attack", "power", "toughness", "flying", "trample", "haste"],
    "utility": ["search your library", "return", "put into your hand", "shuffle"],
}


def load_card_data(game: str) -> pd.DataFrame:
    """Load enriched card CSV."""
    path = DATA_DIR / "processed" / f"card_attributes_{game}_enriched.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def load_embeddings(game: str) -> KeyedVectors | None:
    name = EMBEDDING_FILES.get(game, "")
    path = DATA_DIR / "embeddings" / f"{name}.wv"
    if path.exists():
        return KeyedVectors.load(str(path))
    return None


def detect_role(oracle_text: str) -> list[str]:
    """Detect functional roles from oracle text."""
    if not oracle_text or str(oracle_text) in ("nan", "None", ""):
        return []
    text = str(oracle_text).lower()
    roles = []
    for role, keywords in ROLE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            roles.append(role)
    return roles


def generate_text_similarity_pairs(
    df: pd.DataFrame, wv: KeyedVectors, n_pairs: int = 200, seed: int = 42
) -> list[dict]:
    """Find cards with similar oracle text but low embedding similarity."""
    rng = np.random.default_rng(seed)

    # Filter to cards in embedding vocab with oracle text
    cards = df[df["name"].isin(wv.key_to_index) & df["oracle_text"].notna()].copy()
    cards = cards[cards["oracle_text"].str.len() > 20]

    if len(cards) < 100:
        return []

    # TF-IDF on oracle text
    vectorizer = TfidfVectorizer(max_features=5000, stop_words="english", min_df=2)
    tfidf_matrix = vectorizer.fit_transform(cards["oracle_text"].fillna(""))

    # Sample query cards
    n_queries = min(n_pairs, len(cards) // 2)
    query_indices = rng.choice(len(cards), size=n_queries, replace=False)

    pairs = []
    for qi in query_indices:
        query_name = cards.iloc[qi]["name"]
        if query_name not in wv:
            continue

        # Find text-similar cards
        text_sims = sklearn_cosine(tfidf_matrix[qi : qi + 1], tfidf_matrix).flatten()

        # Get embedding similarities for the same cards
        for ci in np.argsort(text_sims)[::-1][1:20]:  # Top 20 text-similar
            cand_name = cards.iloc[ci]["name"]
            if cand_name == query_name or cand_name not in wv:
                continue

            text_sim = float(text_sims[ci])
            emb_sim = float(wv.similarity(query_name, cand_name))

            # We want: high text sim, LOW embedding sim (the gap the model misses)
            if text_sim > 0.3 and emb_sim < 0.5:
                pairs.append(
                    {
                        "card1": query_name,
                        "card2": cand_name,
                        "source": "text_similarity",
                        "text_sim": round(text_sim, 4),
                        "emb_sim": round(emb_sim, 4),
                        "gap": round(text_sim - emb_sim, 4),
                    }
                )
                break  # One pair per query

    return pairs


def generate_role_matched_pairs(
    df: pd.DataFrame, wv: KeyedVectors, n_pairs: int = 200, seed: int = 42
) -> list[dict]:
    """Find cards sharing the same role but from different colors/archetypes."""
    rng = np.random.default_rng(seed)

    # Detect roles
    cards = df[df["name"].isin(wv.key_to_index) & df["oracle_text"].notna()].copy()
    cards["roles"] = cards["oracle_text"].apply(detect_role)
    cards = cards[cards["roles"].apply(len) > 0]

    # Group by role
    role_cards: dict[str, list[str]] = defaultdict(list)
    card_colors: dict[str, str] = {}
    for _, row in cards.iterrows():
        name = row["name"]
        colors = str(row.get("colors", "")).strip()
        card_colors[name] = colors
        for role in row["roles"]:
            role_cards[role].append(name)

    pairs = []
    for role, card_list in role_cards.items():
        if len(card_list) < 10:
            continue

        # Sample pairs from DIFFERENT colors within the same role
        n_role_pairs = min(n_pairs // len(role_cards), len(card_list) // 2)
        indices = rng.choice(
            len(card_list), size=min(n_role_pairs * 4, len(card_list)), replace=False
        )

        for i in range(0, len(indices) - 1, 2):
            c1 = card_list[indices[i]]
            c2 = card_list[indices[i + 1]]
            col1 = card_colors.get(c1, "")
            col2 = card_colors.get(c2, "")

            # Prefer cross-color pairs
            if col1 == col2 and col1:
                continue

            if c1 in wv and c2 in wv:
                emb_sim = float(wv.similarity(c1, c2))
                pairs.append(
                    {
                        "card1": c1,
                        "card2": c2,
                        "source": "role_matched",
                        "shared_role": role,
                        "colors": f"{col1} vs {col2}",
                        "emb_sim": round(emb_sim, 4),
                    }
                )

            if len(pairs) >= n_pairs:
                break

    return pairs[:n_pairs]


def generate_hard_negatives(
    df: pd.DataFrame, wv: KeyedVectors, n_pairs: int = 100, seed: int = 42
) -> list[dict]:
    """Find cards with high embedding similarity but different functions."""
    rng = np.random.default_rng(seed)

    cards = df[df["name"].isin(wv.key_to_index) & df["oracle_text"].notna()].copy()
    cards["roles"] = cards["oracle_text"].apply(detect_role)

    # Sample query cards
    query_indices = rng.choice(len(cards), size=min(n_pairs * 2, len(cards)), replace=False)

    pairs = []
    for qi in query_indices:
        query = cards.iloc[qi]
        query_roles = set(query["roles"])
        if not query_roles or query["name"] not in wv:
            continue

        # Get top embedding neighbors
        try:
            neighbors = wv.most_similar(query["name"], topn=20)
        except KeyError:
            continue

        for nb_name, nb_sim in neighbors:
            if nb_sim < 0.6:
                break
            # Check if roles differ
            nb_row = cards[cards["name"] == nb_name]
            if nb_row.empty:
                continue
            nb_roles = set(nb_row.iloc[0]["roles"])
            if nb_roles and not (query_roles & nb_roles):
                # High similarity but different roles = hard negative
                pairs.append(
                    {
                        "card1": query["name"],
                        "card2": nb_name,
                        "source": "hard_negative",
                        "emb_sim": round(float(nb_sim), 4),
                        "card1_roles": list(query_roles),
                        "card2_roles": list(nb_roles),
                    }
                )
                break

        if len(pairs) >= n_pairs:
            break

    return pairs[:n_pairs]


def generate_budget_pairs(
    df: pd.DataFrame, wv: KeyedVectors, n_pairs: int = 100, seed: int = 42
) -> list[dict]:
    """Find cheap/expensive card pairs with similar function."""
    # Load Scryfall prices
    price_path = DATA_DIR / "processed" / "scryfall_prices.json"
    if not price_path.exists():
        return []

    with open(price_path) as f:
        prices = json.load(f)

    rng = np.random.default_rng(seed)
    cards = df[df["name"].isin(wv.key_to_index) & df["oracle_text"].notna()].copy()
    cards["roles"] = cards["oracle_text"].apply(detect_role)
    cards = cards[cards["roles"].apply(len) > 0]

    # Add prices
    cards["usd"] = cards["name"].apply(lambda n: float(prices.get(n, {}).get("usd", 0) or 0))
    cards = cards[cards["usd"] > 0]

    pairs = []
    # For each expensive card, find a cheap card with the same role
    expensive = cards[cards["usd"] > 5].sort_values("usd", ascending=False)
    cheap = cards[cards["usd"] < 2]

    for _, exp_row in expensive.iterrows():
        exp_roles = set(exp_row["roles"])
        exp_name = exp_row["name"]
        if exp_name not in wv:
            continue

        # Find cheap cards with matching role
        for _, ch_row in cheap.sample(min(20, len(cheap)), random_state=rng).iterrows():
            ch_roles = set(ch_row["roles"])
            ch_name = ch_row["name"]
            if ch_name not in wv or ch_name == exp_name:
                continue
            if exp_roles & ch_roles:
                emb_sim = float(wv.similarity(exp_name, ch_name))
                pairs.append(
                    {
                        "card1": ch_name,
                        "card2": exp_name,
                        "source": "budget_pair",
                        "shared_role": list(exp_roles & ch_roles)[0],
                        "price_cheap": round(ch_row["usd"], 2),
                        "price_expensive": round(exp_row["usd"], 2),
                        "emb_sim": round(emb_sim, 4),
                    }
                )
                break

        if len(pairs) >= n_pairs:
            break

    return pairs[:n_pairs]


def generate_all(game: str, output_path: Path | None = None) -> dict:
    """Generate diverse pairs for one game."""
    df = load_card_data(game)
    if df.empty:
        return {"game": game, "error": "no card data"}

    wv = load_embeddings(game)
    if wv is None:
        return {"game": game, "error": "no embeddings"}

    print(f"\n{'=' * 60}")
    print(f"{game.upper()} diverse pair generation")
    print(f"  Cards: {len(df)}, Embeddings: {len(wv)}")

    text_pairs = generate_text_similarity_pairs(df, wv)
    print(f"  Text similarity pairs: {len(text_pairs)}")

    role_pairs = generate_role_matched_pairs(df, wv)
    print(f"  Role-matched pairs: {len(role_pairs)}")

    hard_negs = generate_hard_negatives(df, wv)
    print(f"  Hard negatives: {len(hard_negs)}")

    budget_pairs = generate_budget_pairs(df, wv)
    print(f"  Budget pairs: {len(budget_pairs)}")

    all_pairs = text_pairs + role_pairs + hard_negs + budget_pairs
    print(f"  Total: {len(all_pairs)}")

    # Save
    if output_path is None:
        output_path = DATA_DIR / "annotations" / f"diverse_pairs_{game}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for p in all_pairs:
            p["game"] = game
            f.write(json.dumps(p) + "\n")
    print(f"  Saved to {output_path}")

    return {
        "game": game,
        "text_similarity": len(text_pairs),
        "role_matched": len(role_pairs),
        "hard_negatives": len(hard_negs),
        "budget_pairs": len(budget_pairs),
        "total": len(all_pairs),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate diverse annotation pairs")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    for game in games:
        result = generate_all(game, args.output)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
