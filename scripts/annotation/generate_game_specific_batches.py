#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["gensim", "pandas", "pyyaml", "numpy"]
# ///
"""
Generate game-specific hand annotation batches for Pokemon and YuGiOh.

Replaces the contaminated v1 batches (which contained Magic cards) by using
per-game card pools: embeddings + pairs CSVs that are strictly single-game.

Usage:
    .venv/bin/python scripts/annotation/generate_game_specific_batches.py

Outputs:
    annotations/hand_batch_pokemon_v2.yaml
    annotations/hand_batch_yugioh_v2.yaml
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import yaml
from gensim.models import KeyedVectors


ROOT = Path(__file__).resolve().parents[2]

# ── Config ──────────────────────────────────────────────────────────────────

GAMES = {
    "pokemon": {
        "embeddings": ROOT / "data" / "embeddings" / "pokemon_pecanpy.wv",
        "pairs": ROOT / "data" / "processed" / "pairs_pokemon_limitless-web.csv",
        "num_queries": 25,
        "candidates_per_query": 15,
        "batch_id": "hand_batch_pokemon_v2",
        "output": ROOT / "annotations" / "hand_batch_pokemon_v2.yaml",
    },
    "yugioh": {
        "embeddings": ROOT / "data" / "embeddings" / "yugioh_named_d64.wv",
        "pairs": ROOT / "data" / "processed" / "pairs_yugioh_ygoprodeck-tournament.csv",
        "num_queries": 25,
        "candidates_per_query": 15,
        "batch_id": "hand_batch_yugioh_v2",
        "output": ROOT / "annotations" / "hand_batch_yugioh_v2.yaml",
    },
}


# ── Helpers ─────────────────────────────────────────────────────────────────


def load_pairs(path: Path) -> pd.DataFrame:
    """Load pairs CSV; normalise weight column to COUNT_MULTISET."""
    df = pd.read_csv(path)
    if "COUNT_MULTISET" not in df.columns and "COUNT" in df.columns:
        df["COUNT_MULTISET"] = df["COUNT"]
    return df


def build_cooccurrence(df: pd.DataFrame) -> dict[str, list[tuple[str, float]]]:
    """
    Build sorted co-occurrence adjacency: card -> [(neighbour, weight), ...]
    sorted descending by weight.
    """
    adj: dict[str, float] = defaultdict(lambda: defaultdict(float))
    for _, row in df.iterrows():
        c1, c2 = str(row["NAME_1"]), str(row["NAME_2"])
        w = float(row.get("COUNT_MULTISET", 1))
        adj[c1][c2] += w
        adj[c2][c1] += w

    sorted_adj: dict[str, list[tuple[str, float]]] = {}
    for card, neighbours in adj.items():
        sorted_adj[card] = sorted(neighbours.items(), key=lambda x: x[1], reverse=True)
    return sorted_adj


def card_degree(df: pd.DataFrame) -> Counter:
    """Count how many distinct partners each card has (proxy for popularity)."""
    deg: Counter = Counter()
    for _, row in df.iterrows():
        deg[str(row["NAME_1"])] += 1
        deg[str(row["NAME_2"])] += 1
    return deg


def select_diverse_queries(
    wv: KeyedVectors,
    degree: Counter,
    card_pool: set[str],
    n: int,
    seed: int = 42,
) -> list[str]:
    """
    Pick n diverse query cards using stratified sampling across degree tiers,
    then maximise embedding distance within each tier.
    """
    rng = random.Random(seed)

    # Only consider cards that are in both embeddings and pairs
    eligible = sorted(card_pool & set(wv.key_to_index.keys()) & set(degree.keys()))
    if len(eligible) <= n:
        return eligible

    # Sort by degree descending
    eligible.sort(key=lambda c: degree[c], reverse=True)

    # Three tiers: high / medium / low popularity
    third = len(eligible) // 3
    tiers = [
        eligible[:third],
        eligible[third : 2 * third],
        eligible[2 * third :],
    ]

    per_tier = [n // 3, n // 3, n - 2 * (n // 3)]
    selected: list[str] = []

    for tier_cards, k in zip(tiers, per_tier):
        if len(tier_cards) <= k:
            selected.extend(tier_cards)
            continue

        # Greedy max-min-distance selection within this tier
        # Start with a random card
        pool = list(tier_cards)
        rng.shuffle(pool)
        picked = [pool[0]]
        pool_set = set(pool[1:])

        for _ in range(k - 1):
            best_card = None
            best_min_dist = -1.0
            for cand in pool_set:
                if cand not in wv.key_to_index:
                    continue
                min_dist = min(
                    (1.0 - wv.similarity(cand, s)) if s in wv.key_to_index else 2.0
                    for s in picked
                )
                if min_dist > best_min_dist:
                    best_min_dist = min_dist
                    best_card = cand
            if best_card is None:
                # Fallback: random
                best_card = rng.choice(list(pool_set))
            picked.append(best_card)
            pool_set.discard(best_card)

        selected.extend(picked)

    return selected[:n]


def generate_candidates(
    query: str,
    wv: KeyedVectors,
    cooc: dict[str, list[tuple[str, float]]],
    card_pool: list[str],
    k: int = 15,
    rng: random.Random | None = None,
) -> list[dict]:
    """
    For a query card, pick candidates from three sources:
      a) Top 5 embedding neighbours (from game-specific embeddings)
      b) Top 5 co-occurrence neighbours (from game-specific pairs)
      c) 5 random cards from the game pool (negative examples)
    Deduplicates across sources; backfills from random if a source is short.
    """
    if rng is None:
        rng = random.Random(42)

    seen: set[str] = {query}
    candidates: list[dict] = []

    # (a) Embedding neighbours ------------------------------------------------
    n_embed = 5
    if query in wv.key_to_index:
        similar = wv.most_similar(query, topn=n_embed * 3)  # over-fetch for dedup
        for card, score in similar:
            if card in seen or card not in set(card_pool):
                continue
            candidates.append({
                "card": card,
                "sources": ["embedding"],
                "scores": {"embedding": round(float(score), 4)},
            })
            seen.add(card)
            if sum(1 for c in candidates if "embedding" in c["sources"]) >= n_embed:
                break

    # (b) Co-occurrence neighbours --------------------------------------------
    n_cooc = 5
    if query in cooc:
        for card, weight in cooc[query]:
            if card in seen:
                continue
            candidates.append({
                "card": card,
                "sources": ["cooccurrence"],
                "scores": {"cooccurrence": round(float(weight), 2)},
            })
            seen.add(card)
            if sum(1 for c in candidates if "cooccurrence" in c["sources"]) >= n_cooc:
                break

    # (c) Random negatives ----------------------------------------------------
    n_random = k - len(candidates)
    pool_remaining = [c for c in card_pool if c not in seen]
    if n_random > 0 and pool_remaining:
        randoms = rng.sample(pool_remaining, min(n_random, len(pool_remaining)))
        for card in randoms:
            candidates.append({
                "card": card,
                "sources": ["random"],
                "scores": {},
            })
            seen.add(card)

    # If we still have fewer than k (unlikely), just return what we have
    return candidates[:k]


def generate_batch(game: str, cfg: dict) -> Path:
    """Generate one game's annotation batch."""
    print(f"\n{'='*60}")
    print(f"  Generating batch for {game}")
    print(f"{'='*60}")

    # Load data
    print(f"  Loading embeddings: {cfg['embeddings'].name}")
    wv = KeyedVectors.load(str(cfg["embeddings"]))
    emb_cards = set(wv.key_to_index.keys())
    print(f"    {len(emb_cards)} cards in embeddings")

    print(f"  Loading pairs: {cfg['pairs'].name}")
    df = load_pairs(cfg["pairs"])
    pair_cards = set(df["NAME_1"].unique()) | set(df["NAME_2"].unique())
    print(f"    {len(pair_cards)} unique cards in pairs ({len(df)} rows)")

    # Card pool = union of embeddings and pairs (all are game-specific)
    card_pool_set = emb_cards | pair_cards
    card_pool = sorted(card_pool_set)
    print(f"    Card pool (union): {len(card_pool)} cards")

    # Build co-occurrence graph
    cooc = build_cooccurrence(df)
    degree = card_degree(df)

    # Select diverse queries
    print(f"  Selecting {cfg['num_queries']} diverse queries...")
    queries = select_diverse_queries(
        wv, degree, card_pool_set, cfg["num_queries"], seed=42
    )
    print(f"    Selected {len(queries)} queries")
    for i, q in enumerate(queries):
        print(f"      {i+1:2d}. {q}  (degree={degree.get(q, 0)})")

    # Generate candidates for each query
    rng = random.Random(42)
    tasks = []
    source_stats = Counter()

    for query in queries:
        cands = generate_candidates(
            query, wv, cooc, card_pool, k=cfg["candidates_per_query"], rng=rng
        )
        for c in cands:
            for s in c["sources"]:
                source_stats[s] += 1

        task = {
            "query": query,
            "candidates": [
                {
                    "card": c["card"],
                    "sources": c["sources"],
                    "scores": c["scores"] if c["scores"] else None,
                    "relevance": None,
                    "notes": None,
                }
                for c in cands
            ],
        }
        tasks.append(task)

    total_cands = sum(len(t["candidates"]) for t in tasks)
    print(f"\n  Source breakdown across {total_cands} candidates:")
    for src, count in source_stats.most_common():
        print(f"    {src}: {count}")

    # Build output YAML
    batch = {
        "metadata": {
            "game": game,
            "batch_id": cfg["batch_id"],
            "num_queries": len(tasks),
            "total_candidates": total_cands,
            "card_pool_size": len(card_pool),
            "embeddings_file": cfg["embeddings"].name,
            "pairs_file": cfg["pairs"].name,
            "created": datetime.now(UTC).isoformat(),
        },
        "instructions": {
            "relevance_scale": {
                4: "Extremely similar (near substitutes, same function)",
                3: "Very similar (often seen together, similar role)",
                2: "Somewhat similar (related function or archetype)",
                1: "Marginally similar (loose connection)",
                0: "Irrelevant (different function, type, or archetype)",
            },
            "grading_guidelines": [
                "Focus on functional similarity (can they replace each other?)",
                "Consider archetype context (do they appear in same decks?)",
                "Add notes for edge cases or interesting patterns",
            ],
        },
        "tasks": tasks,
    }

    out = cfg["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        yaml.dump(batch, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\n  Wrote: {out}")
    print(f"    {len(tasks)} queries x ~{cfg['candidates_per_query']} candidates = {total_cands} total")
    return out


# ── Contamination check ────────────────────────────────────────────────────


def verify_no_cross_contamination(path: Path, game: str, card_pool: set[str]) -> list[str]:
    """
    Verify every card name in the batch exists in the game's card pool.
    Returns list of violations (empty = clean).
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    violations = []
    for task in data.get("tasks", []):
        query = task["query"]
        if query not in card_pool:
            violations.append(f"query '{query}' not in {game} card pool")
        for cand in task.get("candidates", []):
            card = cand["card"]
            if card not in card_pool:
                violations.append(f"candidate '{card}' (query='{query}') not in {game} card pool")
    return violations


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    outputs: dict[str, Path] = {}
    pools: dict[str, set[str]] = {}

    for game, cfg in GAMES.items():
        # Verify input files exist
        if not cfg["embeddings"].exists():
            print(f"ERROR: embeddings not found: {cfg['embeddings']}")
            return 1
        if not cfg["pairs"].exists():
            print(f"ERROR: pairs not found: {cfg['pairs']}")
            return 1

        out = generate_batch(game, cfg)
        outputs[game] = out

        # Build card pool for verification
        wv = KeyedVectors.load(str(cfg["embeddings"]))
        df = pd.read_csv(cfg["pairs"])
        pool = set(wv.key_to_index.keys()) | set(df["NAME_1"].unique()) | set(df["NAME_2"].unique())
        pools[game] = pool

    # Cross-contamination check
    print(f"\n{'='*60}")
    print("  Cross-contamination verification")
    print(f"{'='*60}")

    all_clean = True
    for game, path in outputs.items():
        violations = verify_no_cross_contamination(path, game, pools[game])
        if violations:
            all_clean = False
            print(f"\n  FAIL: {game} has {len(violations)} violations:")
            for v in violations[:20]:
                print(f"    - {v}")
            if len(violations) > 20:
                print(f"    ... and {len(violations) - 20} more")
        else:
            print(f"  OK: {game} -- all cards verified in game-specific pool ({len(pools[game])} cards)")

    # Also check that Pokemon and YuGiOh pools don't overlap significantly
    overlap = pools["pokemon"] & pools["yugioh"]
    if overlap:
        print(f"\n  WARNING: {len(overlap)} cards appear in both pools:")
        for c in sorted(overlap)[:10]:
            print(f"    - {c}")
    else:
        print("\n  OK: Zero overlap between Pokemon and YuGiOh card pools")

    if all_clean:
        print("\n  All batches are clean. No cross-game contamination detected.")
        return 0
    else:
        print("\n  Some batches have contamination issues -- see above.")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
