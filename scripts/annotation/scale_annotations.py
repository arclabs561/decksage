#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
#     "numpy>=1.26.0",
#     "pandas>=2.0.0",
#     "pydantic>=2.0",
#     "pydantic-ai>=0.1.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
Scale the annotated test set from 171 to 500 queries with mode labels.

Loads the existing annotated test set, selects new query cards from the
embedding vocabulary (prioritizing popular and cold-start cards), and uses
the LLM annotator to judge similarity + mode (synergy/substitution/meta)
for the top-10 neighbors of each new query.

Mode labels enable per-mode evaluation: synergy nDCG vs substitution nDCG.
Without them, embedding improvements that help one mode look like regressions
on the co-occurrence-aligned test set.

Usage:
    # Dry run (no API calls, shows what would be annotated):
    uv run scripts/annotation/scale_annotations.py --dry-run

    # Full run (requires ANNOTATOR_MODEL_SIMILARITY or OPENAI_API_KEY):
    uv run scripts/annotation/scale_annotations.py

    # Custom target count:
    uv run scripts/annotation/scale_annotations.py --target 300

    # Use specific model:
    ANNOTATOR_MODEL_SIMILARITY=openai/gpt-4o \\
        uv run scripts/annotation/scale_annotations.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.utils.data_loading import load_edgelist
from ml.utils.paths import PATHS

# Optional: pydantic-ai for LLM annotations
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from gensim.models import KeyedVectors

    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False
    KeyedVectors = None

try:
    from ml.annotation.llm_annotator import CardSimilarityAnnotation, LLMAnnotator

    HAS_ANNOTATOR = True
except ImportError:
    HAS_ANNOTATOR = False

try:
    from ml.utils.pydantic_ai_helpers import make_agent

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Relevance label thresholds (cosine similarity -> graded relevance)
RELEVANCE_THRESHOLDS = {
    "highly_relevant": 0.80,
    "relevant": 0.60,
    "somewhat_relevant": 0.40,
    "marginally_relevant": 0.20,
}

# Similarity mode definitions for LLM prompt
MODE_PROMPT = """
In addition to judging relevance, classify the PRIMARY MODE of similarity
between the query card and each candidate. Choose exactly one:

- **synergy**: Cards that work well TOGETHER in the same deck. They
  complement each other (e.g., Thassa's Oracle + Demonic Consultation,
  Pikachu V + Pikachu VMAX, Ash Blossom + Called by the Grave).

- **substitution**: Cards that serve the SAME ROLE and can REPLACE each
  other. A deckbuilder choosing between them weighs meta tradeoffs
  (e.g., Lightning Bolt vs Shock, Path to Exile vs Swords to Plowshares,
  Ultra Ball vs Nest Ball).

- **meta**: Cards that appear together due to the competitive metagame
  rather than direct synergy or substitution. Same archetype staples,
  format-defining pairs, sideboard companions
  (e.g., Thoughtseize + Fatal Push in Modern black decks).

If uncertain, prefer the mode that best explains WHY a deckbuilder would
search for the candidate after seeing the query card.
"""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_existing_test_set(path: Path) -> dict[str, Any]:
    """Load existing annotated test set."""
    if not path.exists():
        logger.warning(f"Test set not found: {path}")
        return {"version": "1.0", "game": "magic", "queries": {}}
    with open(path) as f:
        return json.load(f)


def load_embeddings(game: str = "magic") -> KeyedVectors | None:
    """Load the current production embeddings for a game."""
    if not HAS_GENSIM:
        logger.error("gensim not installed, cannot load embeddings")
        return None

    # Try common embedding file patterns in priority order
    candidates = [
        PATHS.embeddings / f"{game}_blended.wv",
        PATHS.embeddings / f"{game}_enriched_v3.wv",
        PATHS.embeddings / f"{game}_enriched_v2.wv",
        PATHS.embeddings / f"{game}_cleaned_v4.wv",
        PATHS.embeddings / f"{game}_lightgcn.wv",
    ]
    for p in candidates:
        if p.exists():
            logger.info(f"Loading embeddings from {p}")
            return KeyedVectors.load(str(p))

    logger.error(f"No embeddings found for {game}")
    return None


def compute_card_popularity(
    edgelist_path: Path,
) -> Counter:
    """Count how many edges each card appears in (proxy for deck frequency)."""
    edges, _ = load_edgelist(edgelist_path, collect_nodes=True)
    popularity: Counter = Counter()
    for c1, c2, w in edges:
        popularity[c1] += w
        popularity[c2] += w
    return popularity


# ---------------------------------------------------------------------------
# Query selection
# ---------------------------------------------------------------------------


def select_new_queries(
    kv: KeyedVectors,
    existing_queries: set[str],
    popularity: Counter,
    target_new: int = 330,
    popular_ratio: float = 0.5,
    cold_start_ratio: float = 0.3,
    random_ratio: float = 0.2,
    seed: int = 42,
) -> list[str]:
    """Select new query cards from embedding vocabulary.

    Strategy:
    - popular_ratio: cards with highest weighted degree (appear in many decks)
    - cold_start_ratio: cards with lowest weighted degree (few decks, hard cases)
    - random_ratio: uniform sample for coverage

    Filters out cards already in the existing test set and Card_XXXX numeric IDs.
    """
    import re

    rng = np.random.default_rng(seed)

    # All cards in embedding vocab, excluding existing queries and numeric IDs
    card_id_pattern = re.compile(r"^Card_\d+$")
    all_cards = [
        c for c in kv.key_to_index if c not in existing_queries and not card_id_pattern.match(c)
    ]

    if not all_cards:
        logger.warning("No new cards available for query selection")
        return []

    # Sort by popularity
    cards_by_pop = sorted(all_cards, key=lambda c: popularity.get(c, 0), reverse=True)

    n_popular = int(target_new * popular_ratio)
    n_cold = int(target_new * cold_start_ratio)
    n_random = target_new - n_popular - n_cold

    selected: list[str] = []

    # Popular cards (top of sorted list)
    popular_pool = cards_by_pop[: max(n_popular * 3, 500)]
    if popular_pool:
        chosen = rng.choice(popular_pool, size=min(n_popular, len(popular_pool)), replace=False)
        selected.extend(chosen.tolist())

    # Cold-start cards (bottom of sorted list, including zero-edge cards --
    # these are valid cold-start candidates that exist in embedding vocab
    # but appear in few or no decks in the edgelist)
    cold_pool = cards_by_pop[-max(n_cold * 5, 1000) :]
    already = set(selected)
    cold_pool = [c for c in cold_pool if c not in already]
    if cold_pool:
        chosen = rng.choice(cold_pool, size=min(n_cold, len(cold_pool)), replace=False)
        selected.extend(chosen.tolist())

    # Random fill
    already = set(selected)
    random_pool = [c for c in all_cards if c not in already]
    if random_pool:
        chosen = rng.choice(random_pool, size=min(n_random, len(random_pool)), replace=False)
        selected.extend(chosen.tolist())

    logger.info(
        f"Selected {len(selected)} new queries: "
        f"{min(n_popular, len(popular_pool))} popular, "
        f"{min(n_cold, len(cold_pool) if cold_pool else 0)} cold-start, "
        f"{min(n_random, len(random_pool) if random_pool else 0)} random"
    )

    return selected[:target_new]


# ---------------------------------------------------------------------------
# LLM annotation
# ---------------------------------------------------------------------------


def get_top_k_neighbors(kv: KeyedVectors, query: str, k: int = 10) -> list[tuple[str, float]]:
    """Get top-k most similar cards from embeddings."""
    if query not in kv:
        return []
    return [(card, float(sim)) for card, sim in kv.most_similar(query, topn=k)]


def sim_to_relevance(sim: float) -> str:
    """Map cosine similarity to graded relevance label."""
    for label, threshold in RELEVANCE_THRESHOLDS.items():
        if sim >= threshold:
            return label
    return "irrelevant"


async def annotate_pair_with_mode(
    agent: Any,
    query_card: str,
    candidate_card: str,
    cosine_sim: float,
    game: str = "magic",
) -> dict[str, Any]:
    """Annotate a single query-candidate pair with relevance + mode.

    Returns dict with relevance label, mode, and reasoning.
    """
    prompt = f"""Judge the similarity between these two {game.upper()} cards:

Card 1 (query): {query_card}
Card 2 (candidate): {candidate_card}

Their embedding cosine similarity is {cosine_sim:.3f}.

{MODE_PROMPT}

Rate the candidate's relevance to the query and classify the similarity mode.
"""

    try:
        result = await agent.run(prompt)
        ann = result.data

        # Extract mode from similarity_type or infer from scores
        mode = _classify_mode(ann)
        relevance = _score_to_relevance(ann.similarity_score)

        return {
            "candidate": candidate_card,
            "relevance": relevance,
            "mode": mode,
            "similarity_score": ann.similarity_score,
            "functional_score": ann.functional_score,
            "synergy_score": ann.synergy_score,
            "meta_relevance": ann.meta_relevance,
            "reasoning": ann.reasoning,
            "is_substitute": ann.is_substitute,
            "model_name": getattr(ann, "model_name", None),
        }
    except Exception as e:
        logger.warning(f"Annotation failed for {query_card} <-> {candidate_card}: {e}")
        return {
            "candidate": candidate_card,
            "relevance": sim_to_relevance(cosine_sim),
            "mode": "unknown",
            "similarity_score": cosine_sim,
            "reasoning": f"LLM annotation failed: {e}",
            "error": True,
        }


def _classify_mode(ann: Any) -> str:
    """Classify similarity mode from annotation sub-scores."""
    func = getattr(ann, "functional_score", None) or 0.0
    syn = getattr(ann, "synergy_score", None) or 0.0
    meta = getattr(ann, "meta_relevance", None) or 0.0

    sim_type = getattr(ann, "similarity_type", "")

    # Direct mapping from similarity_type if clear
    if sim_type == "functional":
        return "substitution"
    if sim_type == "synergy":
        return "synergy"

    # Fall back to sub-scores
    scores = {"substitution": func, "synergy": syn, "meta": meta}
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)

    # Default based on similarity_type string
    if sim_type in ("archetype", "manabase"):
        return "meta"
    return "synergy"  # conservative default


def _score_to_relevance(score: float) -> str:
    """Map LLM similarity score to graded relevance label."""
    if score >= 0.70:
        return "highly_relevant"
    if score >= 0.50:
        return "relevant"
    if score >= 0.30:
        return "somewhat_relevant"
    if score >= 0.15:
        return "marginally_relevant"
    return "irrelevant"


async def annotate_query(
    agent: Any,
    query_card: str,
    neighbors: list[tuple[str, float]],
    game: str = "magic",
    semaphore: asyncio.Semaphore | None = None,
) -> dict[str, Any]:
    """Annotate all neighbors of a query card."""
    sem = semaphore or asyncio.Semaphore(5)

    async def _annotate_one(card: str, sim: float) -> dict[str, Any]:
        async with sem:
            return await annotate_pair_with_mode(agent, query_card, card, sim, game)

    tasks = [_annotate_one(card, sim) for card, sim in neighbors]
    results = await asyncio.gather(*tasks)

    # Organize by relevance level
    by_relevance: dict[str, list[str]] = {
        "highly_relevant": [],
        "relevant": [],
        "somewhat_relevant": [],
        "marginally_relevant": [],
        "irrelevant": [],
    }
    modes: dict[str, str] = {}

    for r in results:
        label = r["relevance"]
        candidate = r["candidate"]
        by_relevance[label].append(candidate)
        modes[candidate] = r.get("mode", "unknown")

    return {
        **by_relevance,
        "modes": modes,
        "annotations": results,
    }


def build_fallback_query(
    query_card: str,
    neighbors: list[tuple[str, float]],
) -> dict[str, Any]:
    """Build a query entry using cosine similarity thresholds (no LLM)."""
    by_relevance: dict[str, list[str]] = {
        "highly_relevant": [],
        "relevant": [],
        "somewhat_relevant": [],
        "marginally_relevant": [],
        "irrelevant": [],
    }

    for card, sim in neighbors:
        label = sim_to_relevance(sim)
        by_relevance[label].append(card)

    return {
        **by_relevance,
        "modes": {},  # No mode labels without LLM
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def estimate_cost(n_queries: int, k: int = 10) -> dict[str, Any]:
    """Estimate API cost for annotation run."""
    n_pairs = n_queries * k
    # Rough estimates based on ~500 input + ~200 output tokens per pair
    tokens_per_pair = 700
    total_tokens = n_pairs * tokens_per_pair

    # Approximate pricing (varies by model)
    cost_per_1k = 0.002  # GPT-4o-mini level
    cost_estimate = (total_tokens / 1000) * cost_per_1k

    return {
        "n_queries": n_queries,
        "n_pairs": n_pairs,
        "tokens_estimate": total_tokens,
        "cost_estimate_usd": round(cost_estimate, 2),
        "note": "Cost estimate assumes ~700 tokens/pair at $0.002/1K tokens (GPT-4o-mini)",
    }


async def run_pipeline(
    game: str = "magic",
    target: int = 500,
    k: int = 10,
    batch_concurrency: int = 5,
    dry_run: bool = False,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run the full annotation scaling pipeline.

    Returns summary statistics.
    """
    # 1. Load existing test set
    existing_path = PATHS.data / f"test_set_annotated_{game}.json"
    existing = load_existing_test_set(existing_path)
    existing_queries = set(existing.get("queries", {}).keys())
    n_existing = len(existing_queries)
    logger.info(f"Existing test set: {n_existing} queries from {existing_path}")

    # 2. Load embeddings
    kv = load_embeddings(game)
    if kv is None:
        return {"error": "No embeddings found"}
    logger.info(f"Embedding vocabulary: {len(kv)} cards")

    # 3. Compute card popularity
    edgelist_path = PATHS.graphs / f"{game}_merged_all.edg"
    if edgelist_path.exists():
        popularity = compute_card_popularity(edgelist_path)
        logger.info(f"Popularity computed from {edgelist_path}: {len(popularity)} cards")
    else:
        logger.warning(f"Edgelist not found: {edgelist_path}, using uniform popularity")
        popularity = Counter({c: 1 for c in kv.key_to_index})

    # 4. Select new queries
    target_new = target - n_existing
    if target_new <= 0:
        logger.info(f"Already have {n_existing} >= {target} queries, nothing to add")
        return {"n_existing": n_existing, "n_new": 0, "n_total": n_existing}

    new_queries = select_new_queries(kv, existing_queries, popularity, target_new=target_new)

    # 5. Get neighbors for each new query
    query_neighbors: dict[str, list[tuple[str, float]]] = {}
    for q in new_queries:
        neighbors = get_top_k_neighbors(kv, q, k=k)
        if neighbors:
            query_neighbors[q] = neighbors

    logger.info(f"Queries with neighbors: {len(query_neighbors)} / {len(new_queries)}")

    # Cost estimate
    cost = estimate_cost(len(query_neighbors), k=k)
    logger.info(
        f"Cost estimate: {cost['n_pairs']} pairs, "
        f"~{cost['tokens_estimate']:,} tokens, "
        f"~${cost['cost_estimate_usd']}"
    )

    if dry_run:
        # Report what would happen without making API calls
        pop_stats = [popularity.get(q, 0) for q in new_queries]
        pop_arr = np.array(pop_stats) if pop_stats else np.array([0])

        print(f"\n--- Dry Run Summary ---")
        print(f"  Existing queries: {n_existing}")
        print(f"  New queries to add: {len(query_neighbors)}")
        print(f"  Target total: {target}")
        print(f"  Pairs to annotate: {cost['n_pairs']}")
        print(f"  Estimated cost: ${cost['cost_estimate_usd']}")
        print(
            f"  New query popularity: mean={pop_arr.mean():.0f}, "
            f"median={np.median(pop_arr):.0f}, "
            f"min={pop_arr.min():.0f}, max={pop_arr.max():.0f}"
        )

        # Show sample queries
        print(f"\n  Sample popular queries:")
        popular = sorted(new_queries, key=lambda c: popularity.get(c, 0), reverse=True)[:5]
        for c in popular:
            print(f"    {c} (popularity={popularity.get(c, 0):.0f})")

        print(f"  Sample cold-start queries:")
        cold = sorted(new_queries, key=lambda c: popularity.get(c, 0))[:5]
        for c in cold:
            print(f"    {c} (popularity={popularity.get(c, 0):.0f})")

        # Build output with cosine-only labels (no LLM)
        new_annotations: dict[str, dict[str, Any]] = {}
        for q, neighbors in query_neighbors.items():
            new_annotations[q] = build_fallback_query(q, neighbors)
            new_annotations[q]["use_case"] = "embedding"

        return {
            "n_existing": n_existing,
            "n_new": len(query_neighbors),
            "n_total": n_existing + len(query_neighbors),
            "cost": cost,
            "dry_run": True,
            "new_annotations": new_annotations,
        }

    # 6. Annotate with LLM
    # Check for API keys
    has_keys = bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
    )

    if not has_keys:
        logger.warning(
            "No API keys found. Set one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, "
            "GOOGLE_API_KEY, OPENROUTER_API_KEY. "
            "Falling back to cosine-similarity-only labels (no mode classification)."
        )

    if not HAS_PYDANTIC_AI or not has_keys:
        # Fallback: use cosine similarity thresholds, no mode labels
        logger.info("Building annotations from cosine similarity (no LLM)")
        new_annotations = {}
        for q, neighbors in query_neighbors.items():
            new_annotations[q] = build_fallback_query(q, neighbors)
            new_annotations[q]["use_case"] = "embedding"
    else:
        # Full LLM annotation with mode classification
        # Import the similarity prompt (available when pydantic-ai is installed)
        import ml.annotation.llm_annotator as _ann_mod

        base_prompt = getattr(_ann_mod, "SIMILARITY_PROMPT_BASE", "")
        if not base_prompt:
            base_prompt = "You are an expert TCG judge creating similarity annotations."

        model_name = os.getenv("ANNOTATOR_MODEL_SIMILARITY", "google/gemini-3-flash-preview")
        prompt = base_prompt + "\n\n" + MODE_PROMPT
        agent = make_agent(model_name, CardSimilarityAnnotation, prompt)

        sem = asyncio.Semaphore(batch_concurrency)
        new_annotations = {}
        n_done = 0
        t0 = time.monotonic()

        for q, neighbors in query_neighbors.items():
            try:
                result = await annotate_query(agent, q, neighbors, game, sem)
                # Strip raw annotations from stored result (keep compact)
                stored = {k: v for k, v in result.items() if k != "annotations"}
                stored["use_case"] = "embedding"
                new_annotations[q] = stored
            except Exception as e:
                logger.warning(f"Failed to annotate query {q}: {e}")
                new_annotations[q] = build_fallback_query(q, neighbors)
                new_annotations[q]["use_case"] = "embedding"

            n_done += 1
            if n_done % 50 == 0:
                elapsed = time.monotonic() - t0
                rate = n_done / elapsed if elapsed > 0 else 0
                logger.info(
                    f"  Progress: {n_done}/{len(query_neighbors)} queries ({rate:.1f} queries/sec)"
                )

    # 7. Merge with existing and save
    merged_queries = dict(existing.get("queries", {}))
    merged_queries.update(new_annotations)

    # Count modes
    mode_counts: Counter = Counter()
    for q_data in new_annotations.values():
        modes = q_data.get("modes", {})
        for mode in modes.values():
            mode_counts[mode] += 1

    output = {
        "version": "2.0",
        "game": game,
        "source": "scale_annotations.py",
        "created": datetime.now(timezone.utc).isoformat(),
        "num_queries": len(merged_queries),
        "num_original": n_existing,
        "num_new": len(new_annotations),
        "mode_counts": dict(mode_counts),
        "queries": merged_queries,
    }

    if output_path is None:
        output_path = PATHS.data / "test_sets" / f"annotated_{game}_v2.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    logger.info(f"Saved {len(merged_queries)} queries to {output_path}")

    # 8. Report
    print(f"\n--- Annotation Summary ---")
    print(f"  Original queries: {n_existing}")
    print(f"  New queries: {len(new_annotations)}")
    print(f"  Total queries: {len(merged_queries)}")
    print(f"  Output: {output_path}")
    if mode_counts:
        print(f"  Mode breakdown (new queries):")
        for mode, count in mode_counts.most_common():
            print(f"    {mode}: {count}")
    print(f"  Cost: {cost}")

    return {
        "n_existing": n_existing,
        "n_new": len(new_annotations),
        "n_total": len(merged_queries),
        "mode_counts": dict(mode_counts),
        "output_path": str(output_path),
        "cost": cost,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scale annotated test set with mode labels.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--game", type=str, default="magic", help="Game name")
    parser.add_argument("--target", type=int, default=500, help="Target total query count")
    parser.add_argument("--k", type=int, default=10, help="Top-k neighbors per query")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Max concurrent LLM calls",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: data/test_sets/annotated_{game}_v2.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be annotated without making API calls",
    )
    args = parser.parse_args()

    result = asyncio.run(
        run_pipeline(
            game=args.game,
            target=args.target,
            k=args.k,
            batch_concurrency=args.concurrency,
            dry_run=args.dry_run,
            output_path=args.output,
        )
    )

    if "error" in result:
        logger.error(result["error"])
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
