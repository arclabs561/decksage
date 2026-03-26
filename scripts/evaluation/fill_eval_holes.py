#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
#     "numpy>=1.26.0",
#     "python-dotenv>=1.0.0",
#     "requests>=2.28.0",
# ]
# ///
"""
Fill judgment holes in top-K evaluation results.

For each evaluation query, identify unjudged cards in the top-K retrieval
results and annotate them. This gives 100% judgment coverage in the
evaluation window, eliminating sparse-annotation bias from nDCG.

Based on: Upadhyay et al. (2024) "LLMs Can Patch Up Missing Relevance
Judgments in Evaluation" and Penha et al. (2025) "LLM-judges Align with
Human Relevance."

The filled annotations go into the test set (eval only, never training).

Usage:
    # Dry run: count holes per game
    uv run python scripts/evaluation/fill_eval_holes.py --game magic --dry-run

    # Fill holes using multi-model cascade
    uv run python scripts/evaluation/fill_eval_holes.py --game magic --model multi

    # Fill holes using Groq (fast, free tier)
    uv run python scripts/evaluation/fill_eval_holes.py --game magic --model groq/llama-3.3-70b-versatile

    # All games
    uv run python scripts/evaluation/fill_eval_holes.py --all-games --model multi
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)
sys.path.insert(0, str(PROJECT_ROOT / "src"))
DATA_DIR = PROJECT_ROOT / "data"

logger = logging.getLogger("fill_eval_holes")

# Embedding paths per game (match .env)
EMBEDDING_PATHS = {
    "magic": "magic_v7_spectral_mu35",
    "pokemon": "pokemon_v7_fused",
    "yugioh": "yugioh_v7_spectral_mu3",
}


def find_holes(game: str, k: int = 10, method: str = "cosine") -> list[tuple[str, str]]:
    """Find (query, candidate) pairs in top-K that aren't annotated.

    Args:
        method: "cosine" (batch matmul, fast) or "fusion" (WeightedLateFusion,
                retrieves different candidates using text+functional signals).
    """
    from gensim.models import KeyedVectors

    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    with open(test_path) as f:
        data = json.load(f)
    queries = data["queries"]

    emb_name = EMBEDDING_PATHS.get(game, f"{game}_v7_fused")
    emb_path = DATA_DIR / "embeddings" / f"{emb_name}.wv"
    kv = KeyedVectors.load(str(emb_path))

    if method == "fusion":
        return _find_holes_fusion(kv, queries, game, k)

    normed = kv.get_normed_vectors()
    idx_to_key = kv.index_to_key

    # Batch compute all top-K at once (vectorized)
    valid_queries = [(qname, qdata) for qname, qdata in queries.items() if qname in kv.key_to_index]
    query_indices = [kv.key_to_index[qname] for qname, _ in valid_queries]
    query_matrix = normed[query_indices]  # (Q, D)

    # Batch similarity: (Q, D) @ (V, D).T -> (Q, V)
    all_sims = query_matrix @ normed.T
    # Zero self-similarity
    for i, qi in enumerate(query_indices):
        all_sims[i, qi] = -2.0

    holes = []
    for i, (qname, qdata) in enumerate(valid_queries):
        annotated = {ann.get("candidate", "") for ann in qdata.get("annotations", [])}
        top_k_idx = np.argpartition(all_sims[i], -k)[-k:]
        top_k_idx = top_k_idx[np.argsort(-all_sims[i][top_k_idx])]

        for j in top_k_idx:
            card = idx_to_key[j]
            if card not in annotated:
                holes.append((qname, card))

    return holes


def _find_holes_fusion(
    kv, queries: dict, game: str, k: int = 10
) -> list[tuple[str, str]]:
    """Find holes using fusion-path candidates (substitution weights)."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from ml.similarity.fusion import WeightedLateFusion
    from ml.utils.shared_operations import load_graph_for_jaccard

    _GAME_TO_DB_CODE = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO"}
    db_game = _GAME_TO_DB_CODE.get(game, game)
    graph_db = DATA_DIR / "graphs" / f"{game}_unified.db"

    adj = load_graph_for_jaccard(graph_db=graph_db, game=db_game)
    print(f"  Loaded graph: {len(adj):,} cards")

    fusion = WeightedLateFusion(
        embeddings=kv, adj=adj, task_type="substitution", game=game,
    )

    valid_queries = [(qn, qd) for qn, qd in queries.items() if qn in kv.key_to_index]
    total = len(valid_queries)
    holes = []

    for i, (qname, qdata) in enumerate(valid_queries):
        annotated = {ann.get("candidate", "") for ann in qdata.get("annotations", [])}
        try:
            neighbors = fusion.similar(qname, k, task_type="substitution")
            for card, _ in neighbors:
                if card not in annotated:
                    holes.append((qname, card))
        except (KeyError, RuntimeError, ValueError):
            pass
        if (i + 1) % 500 == 0:
            print(f"    fusion holes: {i + 1}/{total}, found {len(holes)} so far")

    print(f"    fusion holes: {total}/{total}, total {len(holes)}")
    return holes


def load_card_context(game: str) -> dict[str, str]:
    """Load card text context for LLM prompts."""
    import csv

    game_attrs = {
        "magic": "card_attributes_enriched.csv",
        "pokemon": "card_attributes_pokemon.csv",
        "yugioh": "card_attributes_yugioh.csv",
    }
    csv_path = DATA_DIR / "processed" / game_attrs.get(game, "")
    context = {}
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = row.get("name", "").strip()
                if name:
                    parts = [f"Type: {row.get('type', 'unknown')}"]
                    mc = row.get("mana_cost", "")
                    if mc:
                        parts.append(f"Mana cost: {mc}")
                    text = row.get("oracle_text", "")
                    if text and text != "nan":
                        parts.append(f"Text: {text}")
                    context[name] = "\n".join(parts)
    return context


async def annotate_holes(
    holes: list[tuple[str, str]],
    game: str,
    card_context: dict[str, str],
    model: str = "multi",
    concurrency: int = 20,
) -> list[dict]:
    """Annotate holes using the specified backend."""
    use_multi = model == "multi"

    if use_multi:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts/annotation"))
        from multi_model_annotate import annotate_pair

        logger.info(f"Using multi-model cascade (~$0.40/1000 pairs)")
    else:
        # Groq/Cerebras/OpenAI-compatible
        api_key = ""
        api_url = ""
        if model.startswith("groq/"):
            api_key = os.environ.get("GROQ_API_KEY", "")
            api_url = "https://api.groq.com/openai/v1"
            model_name = model.removeprefix("groq/")
        elif model.startswith("cerebras/"):
            api_key = os.environ.get("CEREBRAS_API_KEY", "")
            api_url = "https://api.cerebras.ai/v1"
            model_name = model.removeprefix("cerebras/")
        else:
            logger.error(f"Unknown model: {model}")
            return []
        logger.info(f"Using {model}")

    results = []
    sem = asyncio.Semaphore(concurrency if not use_multi else 10)
    done = 0

    async def fill_one(query: str, candidate: str) -> dict | None:
        nonlocal done
        async with sem:
            try:
                q_ctx = card_context.get(query, query)
                c_ctx = card_context.get(candidate, candidate)

                if use_multi:
                    ann = await annotate_pair(query, candidate, q_ctx, c_ctx, game)
                else:
                    prompt = f"""Rate these {game.upper()} cards (0.0-1.0):

A: {q_ctx}

B: {c_ctx}

Anchors: 1.0=reprint, 0.8=same role, 0.6=similar function, 0.4=same archetype, 0.2=tangential, 0.0=unrelated.
Respond with JSON: {{"similarity_score": 0.0, "functional_score": 0.0, "synergy_score": 0.0, "meta_relevance": 0.0}}"""

                    session = requests.Session()
                    session.trust_env = False
                    resp = await asyncio.to_thread(
                        session.post,
                        f"{api_url}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": model_name,
                            "messages": [
                                {"role": "system", "content": "You are a card game expert. Respond with JSON only."},
                                {"role": "user", "content": prompt},
                            ],
                            "temperature": 0.3,
                            "max_tokens": 300,
                            "response_format": {"type": "json_object"},
                        },
                        timeout=30,
                    )
                    resp.raise_for_status()
                    content = resp.json()["choices"][0]["message"]["content"].strip()
                    try:
                        ann = json.loads(content)
                    except json.JSONDecodeError:
                        start = content.find("{")
                        end = content.rfind("}") + 1
                        if start >= 0 and end > start:
                            ann = json.loads(content[start:end])
                        else:
                            return None

                ann["query"] = query
                ann["candidate"] = candidate
                ann["model_name"] = model
                ann["discovery_source"] = "eval_hole_fill"
                ann["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")

                done += 1
                if done % 100 == 0:
                    logger.info(f"  Filled {done}/{len(holes)} holes")

                return ann
            except Exception as e:
                logger.debug(f"Failed {query} vs {candidate}: {e}")
                return None

    tasks = [fill_one(q, c) for q, c in holes]

    # Process in chunks to show progress
    chunk_size = 100
    for i in range(0, len(tasks), chunk_size):
        chunk = tasks[i:i + chunk_size]
        chunk_results = await asyncio.gather(*chunk)
        for r in chunk_results:
            if r is not None:
                results.append(r)
        logger.info(f"  Progress: {min(i + chunk_size, len(tasks))}/{len(tasks)} "
                     f"({len(results)} successful)")

    return results


def merge_into_test_set(game: str, annotations: list[dict]) -> int:
    """Merge hole-fill annotations into the test set."""
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    with open(test_path) as f:
        data = json.load(f)

    queries = data["queries"]
    added = 0
    for ann in annotations:
        query = ann.get("query", "")
        candidate = ann.get("candidate", "")
        if not query or not candidate or query not in queries:
            continue

        qdata = queries[query]
        existing = {a.get("candidate", "") for a in qdata.get("annotations", [])}
        if candidate in existing:
            continue

        qdata.setdefault("annotations", []).append({
            "query": query,
            "candidate": candidate,
            "similarity_score": ann.get("similarity_score", 0),
            "functional_score": ann.get("functional_score", 0),
            "synergy_score": ann.get("synergy_score", 0),
            "meta_relevance": ann.get("meta_relevance", 0),
            "confidence": ann.get("confidence", 0.5),
            "llm_model": ann.get("model_name", "unknown"),
            "discovery_source": "eval_hole_fill",
            "timestamp": ann.get("timestamp", ""),
        })

        # Update relevance buckets
        sim = float(ann.get("similarity_score", 0))
        if sim >= 0.70:
            bucket = "highly_relevant"
        elif sim >= 0.50:
            bucket = "relevant"
        elif sim >= 0.30:
            bucket = "somewhat_relevant"
        elif sim >= 0.15:
            bucket = "marginally_relevant"
        else:
            bucket = "irrelevant"
        if candidate not in qdata.get(bucket, []):
            qdata.setdefault(bucket, []).append(candidate)

        added += 1

    data["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    with open(test_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return added


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill judgment holes in top-K eval results")
    parser.add_argument("--game", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--model", default="multi", help="Annotation backend (multi, groq/*, cerebras/*)")
    parser.add_argument("--k", type=int, default=10, help="Top-K depth to fill")
    parser.add_argument("--max-per-game", type=int, default=5000, help="Max holes to fill per game")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--method", default="cosine", choices=["cosine", "fusion"],
        help="Candidate retrieval: 'cosine' (embedding) or 'fusion' (text+functional for substitution)",
    )
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game] if args.game else []
    if not games:
        parser.error("Specify --game or --all-games")

    all_saturated = True
    for game in games:
        print(f"\n{'=' * 60}")
        print(f"  FILL EVAL HOLES: {game.upper()}")
        print(f"{'=' * 60}")

        holes = find_holes(game, k=args.k, method=args.method)
        print(f"  Found {len(holes)} unjudged items in top-{args.k}")

        if args.dry_run:
            # Show sample
            for q, c in holes[:5]:
                print(f"    {q} -> {c}")
            if len(holes) > 5:
                print(f"    ... and {len(holes) - 5} more")
            continue

        # Cap to budget
        to_fill = holes[:args.max_per_game]
        if len(holes) > args.max_per_game:
            print(f"  Capping to {args.max_per_game} (of {len(holes)})")

        card_context = load_card_context(game)

        # Process in chunks with incremental checkpointing
        CHUNK_SIZE = 1000
        total_added = 0
        for chunk_start in range(0, len(to_fill), CHUNK_SIZE):
            chunk = to_fill[chunk_start : chunk_start + CHUNK_SIZE]
            annotations = asyncio.run(
                annotate_holes(chunk, game, card_context, model=args.model, concurrency=args.concurrency)
            )
            added = merge_into_test_set(game, annotations)
            total_added += added
            print(f"  Checkpoint: {chunk_start + len(chunk)}/{len(to_fill)} holes, {total_added} merged")

        print(f"  Total: {total_added} new annotations")

        # Quick eval
        import subprocess
        for emb in [EMBEDDING_PATHS[game]]:
            result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "scripts/evaluation/eval_per_mode.py"),
                 "--game", game, "--embedding", emb, "--quick", "--json"],
                capture_output=True, cwd=str(PROJECT_ROOT),
            )
            if result.returncode == 0:
                try:
                    r = json.loads(result.stdout)[0]
                    sub = r["mode_substitute"]["ndcg_at_k"]
                    condensed = r["mode_substitute"]["condensed_ndcg"]
                    gap = r["mode_substitute"].get("convergence_gap", condensed - sub)
                    saturated = gap < 0.05
                    hit10 = r.get("hit_at_k", {}).get("10", {}).get("rate", "?")
                    status = "SATURATED" if saturated else f"gap={gap:.3f}"
                    print(f"  {emb}: sub={sub:.4f} condensed={condensed:.4f} [{status}] Hit@10={hit10}")
                    if not saturated:
                        all_saturated = False
                except (json.JSONDecodeError, KeyError):
                    all_saturated = False

    print(f"\n{'=' * 60}")
    print("  Hole filling complete.")
    print(f"{'=' * 60}")
    if all_saturated:
        print("\n  All games have converged (standard ~= condensed nDCG).")
        print("  Further hole-filling has diminishing returns.")
        print("  Focus on embedding improvements instead.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
