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
Scale the annotated test set with mode labels. Designed for iterative growth.

Loads the existing annotated test set, selects new query cards from the
embedding vocabulary (prioritizing popular and cold-start cards), and uses
the LLM annotator to judge similarity + mode (synergy/substitution/meta)
for the top-10 neighbors of each new query.

Resilience features:
- Incremental save: each query annotation is flushed to disk immediately.
  If the script crashes at query 200, all 200 are preserved.
- Resume: re-running skips queries already in the output file.
- --batch-size: controls how many new queries to annotate per invocation.

Usage:
    # Dry run (no API calls, shows what would be annotated):
    uv run scripts/annotation/scale_annotations.py --dry-run

    # Full run (requires OPENROUTER_API_KEY or similar):
    uv run scripts/annotation/scale_annotations.py --game magic --target 500

    # Incremental batch (50 queries at a time):
    uv run scripts/annotation/scale_annotations.py --game magic --target 500 --batch-size 50

    # Resume after crash (just re-run the same command):
    uv run scripts/annotation/scale_annotations.py --game magic --target 500
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

**EXTENDED ANNOTATIONS (fill all of these):**

For each card, classify its primary role. Choose one:
  removal, threat, ramp, draw, counter, combo_piece, utility, land, other
Put the result in card_a_role (for the query card) and card_b_role (for the candidate).

Rate each card's competitive power level 1-10:
  1=unplayable draft chaff, 3=fringe playable, 5=average constructed card,
  7=strong staple, 9=format-defining, 10=banned-level power.
Put the result in card_a_power_level and card_b_power_level.

Rate substitutability as a continuous 0-1 value (finer than binary is_substitute).
  0.0=completely different cards, 0.5=partial overlap, 1.0=functional reprint.

Is card B a strict upgrade over card A (same effect but cheaper/better stats)?
  Set upgrade_direction to one of: a_upgrades_b, b_upgrades_a, sidegrade, neither.

Compare mana/resource efficiency:
  Set mana_efficiency_comparison to: a_more_efficient, b_more_efficient, or similar.

Do these two cards form a known combo or rules interaction?
  Set combo_potential to true/false.

Would both cards appear in the same deck archetype?
  Set same_archetype to true/false.

List ALL relationship types that apply (multi-label, pick all that fit):
  functional_substitute, synergy_partner, meta_companion, curve_filler,
  archetype_staple, budget_alternative

Rate your overall confidence in this annotation 0-1:
  0=uncertain/guessing, 0.5=reasonable judgment, 1.0=definitive.
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


def load_embeddings(
    game: str = "magic", embedding_name: str | None = None
) -> tuple[KeyedVectors | None, str]:
    """Load embeddings for a game.

    Returns (KeyedVectors, embedding_version_string) or (None, "").
    """
    if not HAS_GENSIM:
        logger.error("gensim not installed, cannot load embeddings")
        return None, ""

    # If explicit embedding name given, use it
    if embedding_name:
        p = PATHS.embeddings / f"{embedding_name}.wv"
        if p.exists():
            logger.info(f"Loading embeddings from {p}")
            return KeyedVectors.load(str(p)), embedding_name
        logger.error(f"Embedding not found: {p}")
        return None, ""

    # Try common embedding file patterns in priority order
    candidates = [
        (f"{game}_blended", PATHS.embeddings / f"{game}_blended.wv"),
        (f"{game}_enriched_v3", PATHS.embeddings / f"{game}_enriched_v3.wv"),
        (f"{game}_enriched_v2", PATHS.embeddings / f"{game}_enriched_v2.wv"),
        (f"{game}_cleaned_v4", PATHS.embeddings / f"{game}_cleaned_v4.wv"),
        (f"{game}_lightgcn", PATHS.embeddings / f"{game}_lightgcn.wv"),
    ]
    for name, p in candidates:
        if p.exists():
            logger.info(f"Loading embeddings from {p}")
            return KeyedVectors.load(str(p)), name

    logger.error(f"No embeddings found for {game}")
    return None, ""


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


def _card_context(name: str, card_data: dict[str, dict] | None) -> str:
    """Build card context string from metadata (oracle text, type, mana cost)."""
    if not card_data:
        return name
    info = card_data.get(name) or card_data.get(name.lower())
    if not info:
        return name
    parts = [name]
    if info.get("type_line") or info.get("type"):
        parts.append(f"  Type: {info.get('type_line') or info.get('type')}")
    if info.get("mana_cost"):
        parts.append(f"  Mana cost: {info['mana_cost']}")
    if info.get("oracle_text") or info.get("text"):
        text = str(info.get("oracle_text") or info.get("text"))[:300]
        parts.append(f"  Text: {text}")
    if info.get("power") and info.get("toughness"):
        parts.append(f"  P/T: {info['power']}/{info['toughness']}")
    if info.get("atk") is not None:
        parts.append(f"  ATK/DEF: {info.get('atk')}/{info.get('def_stat', '?')}")
    if info.get("hp"):
        parts.append(f"  HP: {info['hp']}")
    return "\n".join(parts)


async def annotate_pair_with_mode(
    agent: Any,
    query_card: str,
    candidate_card: str,
    cosine_sim: float,
    game: str = "magic",
    model_name: str = "unknown",
    embedding_version: str = "unknown",
    card_data: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Annotate a single query-candidate pair with relevance + mode.

    Returns dict with rich metadata per annotation.
    """
    q_ctx = _card_context(query_card, card_data)
    c_ctx = _card_context(candidate_card, card_data)

    prompt = f"""Judge the similarity between these two {game.upper()} cards:

Card 1 (query):
{q_ctx}

Card 2 (candidate):
{c_ctx}

Their embedding cosine similarity is {cosine_sim:.3f}.

{MODE_PROMPT}

IMPORTANT: Base your judgment on the card text and attributes above, NOT on the cosine similarity score. The score may be misleading -- cards with high co-occurrence similarity may serve completely different roles.

**CALIBRATION ANCHORS** (use these to anchor your similarity_score):
- 1.0: Functional reprint (e.g., Lightning Bolt = Chain Lightning for damage-to-face)
- 0.8: Same role, minor differences (e.g., Counterspell vs Mana Leak)
- 0.6: Related function, different power level (e.g., Counterspell vs Cancel)
- 0.4: Same archetype, different role (e.g., Lightning Bolt vs Monastery Swiftspear)
- 0.2: Tangential connection (e.g., both red, both cheap, but different functions)
- 0.0: Unrelated (e.g., Lightning Bolt vs Birds of Paradise)

Rate the candidate's relevance to the query and classify the similarity mode.
"""

    try:
        result = await agent.run(prompt)
        ann = result.output

        # Extract mode from similarity_type or infer from scores
        mode = _classify_mode(ann)
        relevance = _score_to_relevance(ann.similarity_score)

        return {
            "query": query_card,
            "candidate": candidate_card,
            "cosine_similarity": cosine_sim,
            "relevance": relevance,
            "mode": mode,
            "similarity_score": ann.similarity_score,
            "functional_score": ann.functional_score,
            "synergy_score": ann.synergy_score,
            "meta_relevance": ann.meta_relevance,
            "reasoning": ann.reasoning,
            "is_substitute": ann.is_substitute,
            # Extended pair-level labels
            "substitutability": getattr(ann, "substitutability", 0.0),
            "combo_potential": getattr(ann, "combo_potential", False),
            "same_archetype": getattr(ann, "same_archetype", False),
            "upgrade_direction": getattr(ann, "upgrade_direction", "neither"),
            "mana_efficiency_comparison": getattr(ann, "mana_efficiency_comparison", "similar"),
            # Per-card role labels
            "card_a_role": getattr(ann, "card_a_role", ""),
            "card_b_role": getattr(ann, "card_b_role", ""),
            "card_a_power_level": getattr(ann, "card_a_power_level", 5),
            "card_b_power_level": getattr(ann, "card_b_power_level", 5),
            # Multi-label relationship classification
            "relationship_types": getattr(ann, "relationship_types", []),
            # Confidence
            "confidence": getattr(ann, "confidence", 0.5),
            # Provenance
            "llm_model": model_name,
            "embedding_version": embedding_version,
            "game": game,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"Annotation failed for {query_card} <-> {candidate_card}: {e}")
        return {
            "query": query_card,
            "candidate": candidate_card,
            "cosine_similarity": cosine_sim,
            "relevance": sim_to_relevance(cosine_sim),
            "mode": "unknown",
            "similarity_score": cosine_sim,
            "reasoning": f"LLM annotation failed: {e}",
            "error": True,
            "llm_model": model_name,
            "embedding_version": embedding_version,
            "game": game,
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
    model_name: str = "unknown",
    embedding_version: str = "unknown",
    card_data: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Annotate all neighbors of a query card.

    Uses concurrent per-pair calls (not batch) because pydantic-ai
    structured output works per-call. Concurrency is controlled by
    the semaphore.
    """
    sem = semaphore or asyncio.Semaphore(10)

    async def _annotate_one(card: str, sim: float) -> dict[str, Any]:
        async with sem:
            return await annotate_pair_with_mode(
                agent,
                query_card,
                card,
                sim,
                game,
                model_name=model_name,
                embedding_version=embedding_version,
                card_data=card_data,
            )

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
    embedding_version: str = "unknown",
    game: str = "magic",
) -> dict[str, Any]:
    """Build a query entry using cosine similarity thresholds (no LLM)."""
    by_relevance: dict[str, list[str]] = {
        "highly_relevant": [],
        "relevant": [],
        "somewhat_relevant": [],
        "marginally_relevant": [],
        "irrelevant": [],
    }
    annotations = []

    for card, sim in neighbors:
        label = sim_to_relevance(sim)
        by_relevance[label].append(card)
        annotations.append(
            {
                "query": query_card,
                "candidate": card,
                "cosine_similarity": sim,
                "relevance": label,
                "mode": "unknown",
                "similarity_score": sim,
                "llm_model": "cosine_fallback",
                "embedding_version": embedding_version,
                "game": game,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    return {
        **by_relevance,
        "modes": {},  # No mode labels without LLM
        "annotations": annotations,
    }


# ---------------------------------------------------------------------------
# Incremental save
# ---------------------------------------------------------------------------


def _load_output_file(path: Path) -> dict[str, Any]:
    """Load existing output file for resume, or return empty structure."""
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            logger.info(
                f"Loaded existing output with {len(data.get('queries', {}))} queries for resume"
            )
            return data
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Corrupt output file {path}, starting fresh: {e}")
    return {}


def _flush_output(path: Path, data: dict[str, Any]) -> None:
    """Atomically write output file (write to .tmp then rename)."""
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.rename(path)


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
    batch_size: int | None = None,
    dry_run: bool = False,
    output_path: Path | None = None,
    embedding_name: str | None = None,
) -> dict[str, Any]:
    """Run the full annotation scaling pipeline.

    Saves incrementally (each query flushed to disk). Supports resume
    by skipping queries already in the output file.

    Returns summary statistics.
    """
    # 1. Resolve output path
    if output_path is None:
        output_path = PATHS.data / "test_sets" / f"annotated_{game}_v2.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Load seed test set (original annotations)
    existing_path = PATHS.data / f"test_set_annotated_{game}.json"
    seed_data = load_existing_test_set(existing_path)
    seed_queries = set(seed_data.get("queries", {}).keys())
    logger.info(f"Seed test set: {len(seed_queries)} queries from {existing_path}")

    # 3. Load output file for resume (may already have queries from prior runs)
    output_data = _load_output_file(output_path)
    # Only count queries with actual per-pair annotations as "done".
    # Bucket-only queries (from seed data) need LLM annotation.
    already_done = set()
    for qname, qdata in output_data.get("queries", {}).items():
        if qdata.get("annotations"):
            already_done.add(qname)
    all_existing = seed_queries | already_done
    n_existing = len(all_existing)
    n_bucket_only = len(seed_queries - already_done)
    if n_bucket_only > 0:
        logger.info(
            f"Total existing queries: {n_existing} ({n_bucket_only} bucket-only need annotation)"
        )
    else:
        logger.info(f"Total existing queries (seed + prior runs): {n_existing}")

    # 4. Load embeddings
    kv, embedding_version = load_embeddings(game, embedding_name)
    if kv is None:
        return {"error": "No embeddings found"}
    logger.info(f"Embedding vocabulary: {len(kv)} cards (version: {embedding_version})")

    # 4b. Load card metadata for prompt context (oracle text, type, mana cost)
    card_metadata: dict[str, dict] | None = None
    for attrs_name in [
        f"card_attributes_{game}_enriched.csv",
        f"card_attributes_enriched.csv" if game == "magic" else f"card_attributes_{game}.csv",
        f"card_attributes_{game}.csv",
    ]:
        attrs_path = PATHS.processed / attrs_name
        if attrs_path.exists():
            try:
                import pandas as pd

                df = pd.read_csv(attrs_path, low_memory=False)
                name_col = "name" if "name" in df.columns else df.columns[0]
                card_metadata = {}
                for _, row in df.iterrows():
                    name = str(row.get(name_col, ""))
                    if name:
                        card_metadata[name] = {
                            k: v for k, v in row.to_dict().items() if pd.notna(v)
                        }
                logger.info(
                    f"Loaded card metadata: {len(card_metadata)} cards from {attrs_path.name}"
                )
                break
            except Exception as e:
                logger.debug(f"Failed to load card attrs from {attrs_path}: {e}")
    if not card_metadata:
        logger.warning(
            "No card metadata loaded -- LLM annotations will be name-only (lower quality)"
        )

    # 5. Compute card popularity
    edgelist_path = PATHS.graphs / f"{game}_merged_all.edg"
    if edgelist_path.exists():
        popularity = compute_card_popularity(edgelist_path)
        logger.info(f"Popularity computed from {edgelist_path}: {len(popularity)} cards")
    else:
        logger.warning(f"Edgelist not found: {edgelist_path}, using uniform popularity")
        popularity = Counter({c: 1 for c in kv.key_to_index})

    # 6. Select new queries
    target_new = target - n_existing
    if target_new <= 0:
        logger.info(f"Already have {n_existing} >= {target} queries, nothing to add")
        return {"n_existing": n_existing, "n_new": 0, "n_total": n_existing}

    new_queries = select_new_queries(kv, all_existing, popularity, target_new=target_new)

    # Apply batch_size limit
    if batch_size is not None and batch_size > 0:
        new_queries = new_queries[:batch_size]
        logger.info(f"Batch size limit: processing {len(new_queries)} of {target_new} remaining")

    # 7. Get neighbors for each new query
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
        if batch_size:
            print(f"  Batch size: {batch_size}")
            print(f"  Remaining after this batch: {target_new - len(query_neighbors)}")
        print(f"  Target total: {target}")
        print(f"  Pairs to annotate: {cost['n_pairs']}")
        print(f"  Estimated cost: ${cost['cost_estimate_usd']}")
        print(f"  Embedding version: {embedding_version}")
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

        return {
            "n_existing": n_existing,
            "n_new": len(query_neighbors),
            "n_total": n_existing + len(query_neighbors),
            "cost": cost,
            "dry_run": True,
            "embedding_version": embedding_version,
        }

    # 8. Build merged queries dict (seed + prior output)
    merged_queries: dict[str, Any] = dict(seed_data.get("queries", {}))
    merged_queries.update(output_data.get("queries", {}))

    # Determine annotation method
    # Support model rotation for IAA: comma-separated models in env var
    # e.g., ANNOTATOR_MODEL_SIMILARITY=anthropic/claude-haiku-4-5-20251001,google/gemini-3-flash-preview
    model_str = os.getenv("ANNOTATOR_MODEL_SIMILARITY", "anthropic/claude-haiku-4-5-20251001")
    model_pool = [m.strip() for m in model_str.split(",") if m.strip()]
    model_name = model_pool[0]  # Primary model for metadata

    has_keys = bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
    )

    use_llm = HAS_PYDANTIC_AI and has_keys

    if not has_keys:
        logger.warning(
            "No API keys found. Set one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, "
            "GOOGLE_API_KEY, OPENROUTER_API_KEY. "
            "Falling back to cosine-similarity-only labels (no mode classification)."
        )

    agent = None
    agent_pool: list[tuple[str, Any]] = []  # (model_name, agent) for rotation
    if use_llm:
        import ml.annotation.llm_annotator as _ann_mod

        base_prompt = getattr(_ann_mod, "SIMILARITY_PROMPT_BASE", "")
        if not base_prompt:
            base_prompt = "You are an expert TCG judge creating similarity annotations."

        prompt = base_prompt + "\n\n" + MODE_PROMPT

        for m in model_pool:
            a = make_agent(m, CardSimilarityAnnotation, prompt)
            agent_pool.append((m, a))
            logger.info(f"LLM annotation model: {m}")

        agent = agent_pool[0][1]  # Default agent
        if len(agent_pool) > 1:
            logger.info(
                f"Model rotation enabled for IAA: {len(agent_pool)} models, rotating per-query"
            )
    else:
        logger.info("Building annotations from cosine similarity (no LLM)")
        model_name = "cosine_fallback"

    # 8b. Re-annotate bucket-only queries (seed data without per-pair annotations)
    bucket_only_queries: dict[str, list[tuple[str, float]]] = {}
    for qname, qdata in merged_queries.items():
        if not qdata.get("annotations") and qname in kv:
            neighbors = get_top_k_neighbors(kv, qname, k=k)
            if neighbors:
                bucket_only_queries[qname] = neighbors

    if bucket_only_queries:
        logger.info(f"Found {len(bucket_only_queries)} bucket-only queries to annotate with LLM")
        if batch_size is not None and batch_size > 0:
            # Limit bucket-only re-annotation to remaining batch budget
            remaining = batch_size - len(query_neighbors)
            if remaining > 0:
                items = list(bucket_only_queries.items())[:remaining]
                bucket_only_queries = dict(items)
            else:
                bucket_only_queries = {}
        # Merge into query_neighbors for unified processing
        query_neighbors.update(bucket_only_queries)

    # 9. Annotate queries incrementally
    sem = asyncio.Semaphore(batch_concurrency)
    n_done = 0
    n_total_to_do = len(query_neighbors)
    t0 = time.monotonic()
    mode_counts: Counter = Counter()

    def _build_header() -> dict[str, Any]:
        """Build the output file header with current stats."""
        return {
            "version": "2.0",
            "game": game,
            "source": "scale_annotations.py",
            "embedding_version": embedding_version,
            "llm_model": ",".join(m for m, _ in agent_pool) if agent_pool else model_name,
            "created": output_data.get("created", datetime.now(timezone.utc).isoformat()),
            "updated": datetime.now(timezone.utc).isoformat(),
            "num_queries": len(merged_queries),
            "num_seed": len(seed_queries),
            "mode_counts": dict(mode_counts),
        }

    for q_idx, (q, neighbors) in enumerate(query_neighbors.items()):
        # Rotate models for IAA (each query gets a different model)
        if agent_pool and len(agent_pool) > 1:
            chosen_model, chosen_agent = agent_pool[q_idx % len(agent_pool)]
        elif agent_pool:
            chosen_model, chosen_agent = agent_pool[0]
        else:
            chosen_model, chosen_agent = model_name, agent

        if use_llm and chosen_agent is not None:
            try:
                result = await annotate_query(
                    chosen_agent,
                    q,
                    neighbors,
                    game,
                    sem,
                    model_name=chosen_model,
                    embedding_version=embedding_version,
                    card_data=card_metadata,
                )
                # Keep annotations for rich metadata, strip bulk from stored result
                stored = {k: v for k, v in result.items() if k != "annotations"}
                stored["use_case"] = "embedding"
                stored["annotations"] = result["annotations"]
                merged_queries[q] = stored
            except Exception as e:
                logger.error(f"LLM annotation FAILED for query {q}: {e}")
                # Do NOT silently fall back to cosine-only annotations.
                # Skip the query entirely -- it can be retried on next run.
                continue
        else:
            fallback = build_fallback_query(
                q,
                neighbors,
                embedding_version=embedding_version,
                game=game,
            )
            fallback["use_case"] = "embedding"
            merged_queries[q] = fallback

        # Update mode counts
        q_modes = merged_queries[q].get("modes", {})
        for mode in q_modes.values():
            mode_counts[mode] += 1

        n_done += 1

        # Incremental save after every query
        output_doc = {**_build_header(), "queries": merged_queries}
        _flush_output(output_path, output_doc)

        if n_done % 10 == 0 or n_done == n_total_to_do:
            elapsed = time.monotonic() - t0
            rate = n_done / elapsed if elapsed > 0 else 0
            logger.info(
                f"  Progress: {n_done}/{n_total_to_do} queries "
                f"({rate:.1f} q/s, {len(merged_queries)} total saved)"
            )

    # 10. Final report
    print(f"\n--- Annotation Summary ---")
    print(f"  Seed queries: {len(seed_queries)}")
    print(f"  New queries this run: {n_done}")
    print(f"  Total queries: {len(merged_queries)}")
    print(f"  Output: {output_path}")
    print(f"  Embedding version: {embedding_version}")
    print(f"  LLM model: {model_name}")
    if mode_counts:
        print(f"  Mode breakdown (new queries):")
        for mode, count in mode_counts.most_common():
            print(f"    {mode}: {count}")
    print(f"  Cost: {cost}")

    remaining = target - len(merged_queries)
    if remaining > 0:
        print(f"\n  {remaining} queries remain to reach target {target}.")
        print(f"  Re-run this command to continue.")

    return {
        "n_existing": n_existing,
        "n_new": n_done,
        "n_total": len(merged_queries),
        "mode_counts": dict(mode_counts),
        "output_path": str(output_path),
        "embedding_version": embedding_version,
        "cost": cost,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scale annotated test set with mode labels.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Designed for iterative growth. Re-run to resume where you left off.
Use --batch-size to control how many queries per invocation.

Examples:
  # Dry run:
  uv run scripts/annotation/scale_annotations.py --dry-run --game magic --target 500

  # Annotate 50 queries at a time:
  uv run scripts/annotation/scale_annotations.py --game magic --target 500 --batch-size 50

  # Resume after crash or interruption (same command):
  uv run scripts/annotation/scale_annotations.py --game magic --target 500
""",
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
        "--batch-size",
        type=int,
        default=None,
        help="Max queries to annotate this run (default: all remaining)",
    )
    parser.add_argument(
        "--embedding",
        type=str,
        default=None,
        help="Embedding name (e.g. magic_cleaned_v4). Default: auto-detect.",
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
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            output_path=args.output,
            embedding_name=args.embedding,
        )
    )

    if "error" in result:
        logger.error(result["error"])
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
