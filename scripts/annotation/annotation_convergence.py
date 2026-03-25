#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
#     "numpy>=1.26.0",
#     "pydantic>=2.0",
#     "pydantic-ai>=0.1.0",
#     "python-dotenv>=1.0.0",
#     "requests>=2.28.0",
#     "sentence-transformers>=2.2.0",
# ]
# ///
"""
Annotation-eval convergence loop: progressively annotate unannotated candidates.

After each embedding iteration, the top-K results contain cards that aren't in
the test set's annotations. This script:
1. Identifies unannotated (query, candidate) pairs from MULTIPLE retrieval sources
2. Annotates them via multi-model LLM ensemble (cumulative, deduplicated)
3. Merges into the test set
4. Re-evaluates all embeddings on the enriched test set

Multi-source candidate selection prevents bias toward any single embedding:
  - Current best embedding top-K
  - Text similarity (E5/MiniLM) top-K
  - Previous embedding versions that rank differently
  - Random pairs (control group)

Usage:
    # Dry run: show what would be annotated
    uv run python scripts/annotation/annotation_convergence.py --game magic --dry-run

    # Run one cycle (discover + annotate + merge + eval)
    uv run python scripts/annotation/annotation_convergence.py --game magic --budget 200

    # Multiple cycles
    uv run python scripts/annotation/annotation_convergence.py --game magic --budget 200 --cycles 3
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
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)  # explicit project .env, not parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DATA_DIR = PROJECT_ROOT / "data"
logger = logging.getLogger("annotation_convergence")


# ---------------------------------------------------------------------------
# Step 1: Discover unannotated candidates from multiple sources
# ---------------------------------------------------------------------------


def load_test_set(game: str) -> dict:
    path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def get_annotated_pairs(queries: dict) -> set[tuple[str, str]]:
    """Return all (query, candidate) pairs that already have annotations."""
    pairs = set()
    for qname, qdata in queries.items():
        for ann in qdata.get("annotations", []):
            candidate = ann.get("candidate", "")
            if candidate:
                pairs.add((qname, candidate))
    return pairs


def discover_candidates(
    game: str,
    queries: dict,
    embedding_names: list[str],
    budget: int = 200,
    k: int = 10,
    text_fraction: float = 0.3,
    random_fraction: float = 0.1,
) -> list[tuple[str, str, str]]:
    """Find unannotated (query, candidate) pairs from multiple sources.

    Returns list of (query, candidate, source) tuples.
    Sources: 'embedding:<name>', 'text_similarity', 'random'.
    """
    from gensim.models import KeyedVectors

    annotated = get_annotated_pairs(queries)
    candidates: dict[tuple[str, str], str] = {}  # (q, c) -> source

    # Source 1: embedding top-K (one per embedding)
    emb_budget = int(budget * (1 - text_fraction - random_fraction))
    per_emb = max(1, emb_budget // max(len(embedding_names), 1))

    for emb_name in embedding_names:
        emb_path = DATA_DIR / "embeddings" / f"{emb_name}.wv"
        if not emb_path.exists():
            logger.warning(f"Embedding not found: {emb_path}")
            continue

        kv = KeyedVectors.load(str(emb_path))
        count = 0
        for qname in queries:
            if qname not in kv or count >= per_emb:
                break
            try:
                neighbors = kv.most_similar(qname, topn=k)
            except KeyError:
                continue
            for card, _ in neighbors:
                if (qname, card) not in annotated and (qname, card) not in candidates:
                    candidates[(qname, card)] = f"embedding:{emb_name}"
                    count += 1
                    if count >= per_emb:
                        break

    # Source 2: text similarity (oracle text via sentence-transformers)
    text_budget = int(budget * text_fraction)
    if text_budget > 0:
        try:
            import csv

            from sentence_transformers import SentenceTransformer

            # Load card texts
            game_attrs = {
                "magic": "card_attributes_enriched.csv",
                "pokemon": "card_attributes_pokemon.csv",
                "yugioh": "card_attributes_yugioh.csv",
            }
            csv_path = DATA_DIR / "processed" / game_attrs.get(game, "")
            if csv_path.exists():
                cards = {}
                with open(csv_path, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        name = row.get("name", "").strip()
                        text = row.get("oracle_text", "").strip()
                        if name and text and text != "nan":
                            cards[name] = f"{name}. {row.get('type', '')}. {text}"

                # Use cached embeddings if available
                cache_dir = DATA_DIR / "cache" / "text_embeddings"
                game_tag = {"magic": "magic", "pokemon": "pokemon", "yugioh": "yugioh"}[game]
                names_file = cache_dir / f"{game_tag}_names.txt"
                emb_file = cache_dir / f"{game_tag}_embeddings.npy"

                if names_file.exists() and emb_file.exists():
                    text_names = names_file.read_text().strip().split("\n")
                    text_embs = np.load(emb_file)
                    logger.info(f"Loaded cached text embeddings ({len(text_names)} cards)")
                else:
                    query_cards = [q for q in queries if q in cards]
                    text_names = query_cards
                    model = SentenceTransformer("all-MiniLM-L6-v2")
                    text_embs = model.encode(
                        [cards[c] for c in query_cards],
                        batch_size=256,
                        normalize_embeddings=True,
                        show_progress_bar=False,
                        convert_to_numpy=True,
                    )

                # For each query, find text-similar cards not yet annotated
                name_to_idx = {n: i for i, n in enumerate(text_names)}
                count = 0
                for qname in queries:
                    if qname not in name_to_idx or count >= text_budget:
                        break
                    qi = name_to_idx[qname]
                    sims = text_embs[qi] @ text_embs.T
                    sims[qi] = -2  # exclude self
                    top_idx = np.argsort(-sims)[: k * 2]
                    for j in top_idx:
                        card = text_names[j]
                        if (qname, card) not in annotated and (qname, card) not in candidates:
                            candidates[(qname, card)] = "text_similarity"
                            count += 1
                            if count >= text_budget:
                                break
        except Exception as e:
            logger.warning(f"Text similarity source failed: {e}")

    # Source 3: random pairs (control group)
    random_budget = int(budget * random_fraction)
    if random_budget > 0:
        rng = np.random.default_rng(42)
        query_list = list(queries.keys())
        # Need a vocabulary -- use the first available embedding
        for emb_name in embedding_names:
            emb_path = DATA_DIR / "embeddings" / f"{emb_name}.wv"
            if emb_path.exists():
                kv = KeyedVectors.load(str(emb_path))
                all_cards = list(kv.key_to_index.keys())
                count = 0
                for _ in range(random_budget * 10):
                    q = rng.choice(query_list)
                    c = rng.choice(all_cards)
                    if q != c and (q, c) not in annotated and (q, c) not in candidates:
                        candidates[(q, c)] = "random"
                        count += 1
                        if count >= random_budget:
                            break
                break

    result = [(q, c, src) for (q, c), src in candidates.items()]
    logger.info(
        f"Discovered {len(result)} unannotated pairs "
        f"(budget={budget}, sources: "
        f"{Counter(src for _, _, src in result).most_common()})"
    )
    return result[:budget]


# ---------------------------------------------------------------------------
# Step 2: Annotate with multi-model IAA
# ---------------------------------------------------------------------------


async def annotate_pairs(
    pairs: list[tuple[str, str, str]],
    game: str,
    card_context: dict[str, str],
    max_concurrent: int = 20,
    model_override: str | None = None,
) -> list[dict]:
    """Annotate (query, candidate) pairs using pydantic-ai agent.

    Cost optimizations:
    - Uses cheapest model by default (Haiku 4.5 ~$0.001/call)
    - Override with --model for specific model or IAA
    - Pairs with no card context are skipped (saves ~10% of calls)
    - Structured output avoids wasted tokens on reasoning
    """
    try:
        from ml.annotation.llm_annotator import CardSimilarityAnnotation
        from ml.utils.pydantic_ai_helpers import make_agent
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        return []

    # Model selection: explicit override > env var first model > cheap default
    if model_override:
        model_name = model_override
    else:
        models_str = os.environ.get("ANNOTATOR_MODEL_SIMILARITY", "")
        if models_str:
            model_name = models_str.split(",")[0].strip()
        else:
            model_name = "anthropic/claude-haiku-4-5-20251001"

    # Multi-model cascade (Groq 70B + Cerebras 235B, calibrated)
    use_multi = model_name == "multi"

    use_ollama = model_name.startswith("ollama/")
    ollama_model = model_name.removeprefix("ollama/") if use_ollama else None

    # Groq: fast cloud inference (developer tier: 500K RPM)
    use_groq = model_name.startswith("groq/")
    groq_model = model_name.removeprefix("groq/") if use_groq else None
    groq_key = os.environ.get("GROQ_API_KEY", "")

    # Cerebras: fast cloud inference (867 tok/s, 235B MoE)
    use_cerebras = model_name.startswith("cerebras/")
    cerebras_model = model_name.removeprefix("cerebras/") if use_cerebras else None
    cerebras_key = os.environ.get("CEREBRAS_API_KEY", "")

    # Local OpenAI-compatible server (mlx-lm serve, DMR, vLLM, SGLang)
    # Detected via LOCAL_LLM_URL env var or local:// model prefix
    use_local = model_name.startswith("local/")
    local_url = os.environ.get("LOCAL_LLM_URL", "http://localhost:8085/v1")
    local_model_name = model_name.removeprefix("local/") if use_local else None
    if not use_local and not use_groq and os.environ.get("LOCAL_LLM_URL"):
        # LOCAL_LLM_URL set but no local/ prefix -- auto-detect
        use_local = True
        local_model_name = model_name

    if use_multi:
        logger.info(
            "  Using multi-model cascade: Groq 70B + Cerebras 235B (calibrated, ~$0.28/1000 pairs)"
        )
        agent = None
    elif use_groq:
        logger.info(f"  Using Groq: {groq_model} (fast cloud, ~$0.024/1000 pairs)")
        agent = None
    elif use_cerebras:
        logger.info(f"  Using Cerebras: {cerebras_model} (fast cloud, 867 tok/s)")
        agent = None
    elif use_ollama:
        logger.info(f"  Using ollama: {ollama_model} (FREE, local)")
        agent = None
    elif use_local:
        logger.info(f"  Using local server: {local_url} model={local_model_name} (FREE, local)")
        agent = None
    else:
        logger.info(f"  Using model: {model_name}")
        agent = make_agent(
            model_name,
            result_cls=CardSimilarityAnnotation,
            system_prompt="You are a card game expert. Rate card similarity concisely.",
        )

    local_concurrency = int(os.environ.get("LOCAL_LLM_CONCURRENCY", "4"))
    if use_multi:
        effective_concurrency = min(max_concurrent, 10)  # multi-model: 4 API calls per pair
    elif use_groq:
        effective_concurrency = min(max_concurrent, 50)  # Groq handles 50+ easily
    elif use_cerebras:
        effective_concurrency = min(max_concurrent, 30)  # Cerebras: 30 RPM free tier
    elif use_ollama:
        effective_concurrency = int(os.environ.get("OLLAMA_NUM_PARALLEL", "1"))
    elif use_local:
        effective_concurrency = local_concurrency
    else:
        effective_concurrency = max_concurrent

    # Cost estimation
    est_tokens = len(pairs) * 400  # ~300 input + 100 output per pair
    cost_estimates = {
        "groq/llama-3.1-8b-instant": est_tokens * 0.065 / 1_000_000,  # $0.05 in + $0.08 out avg
        "groq/llama-3.3-70b-versatile": est_tokens * 0.69 / 1_000_000,
        "openrouter": est_tokens * 1.0 / 1_000_000,  # varies by model
        "local": 0.0,
    }
    if use_groq:
        est_cost = cost_estimates.get(f"groq/{groq_model}", est_tokens * 0.1 / 1_000_000)
        logger.info(
            f"  Estimated cost: ${est_cost:.4f} for {len(pairs)} pairs (~{est_tokens} tokens)"
        )
    elif use_ollama or use_local:
        logger.info("  Estimated cost: $0.00 (local inference)")
    else:
        est_cost = est_tokens * 1.0 / 1_000_000  # rough OpenRouter average
        logger.info(f"  Estimated cost: ~${est_cost:.4f} for {len(pairs)} pairs (varies by model)")

    results = []
    semaphore = asyncio.Semaphore(effective_concurrency)

    async def _call_openai_compatible(
        messages: list[dict],
        model: str,
        api_key: str,
        base_url: str,
    ) -> dict | None:
        """Call any OpenAI-compatible cloud API (Groq, Cerebras, etc.)."""
        session = requests.Session()
        resp = await asyncio.to_thread(
            session.post,
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 500,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _parse_json_response(content)

    async def _call_groq(messages: list[dict], model: str, api_key: str) -> dict | None:
        """Call Groq API (fast cloud inference)."""
        session = requests.Session()
        resp = await asyncio.to_thread(
            session.post,
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 500,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _parse_json_response(content)

    async def _call_local_openai(messages: list[dict], url: str, model: str) -> dict | None:
        """Call any OpenAI-compatible local server (mlx-lm, DMR, vLLM, SGLang)."""
        session = requests.Session()
        session.trust_env = False  # bypass proxy for localhost
        resp = await asyncio.to_thread(
            session.post,
            f"{url.rstrip('/')}/chat/completions",
            json={
                "model": model or "default",
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1500,
                "response_format": {"type": "json_object"},
            },
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _parse_json_response(content)

    async def _call_ollama(messages: list[dict], model: str) -> dict | None:
        """Call Ollama's native API."""
        session = requests.Session()
        session.trust_env = False
        resp = await asyncio.to_thread(
            session.post,
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.3},
            },
            timeout=120,
        )
        content = resp.json()["message"]["content"]
        return _parse_json_response(content)

    def _parse_json_response(content: str) -> dict | None:
        """Parse JSON from LLM response, handling markdown fences and extra text."""
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1].lstrip("json\n")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        return None

    async def annotate_one(query: str, candidate: str, source: str) -> dict | None:
        async with semaphore:
            try:
                q_ctx = card_context.get(query, query)
                c_ctx = card_context.get(candidate, candidate)

                # Richer prompt for smaller/faster models; compact for frontier
                if use_groq or use_ollama or use_local:
                    prompt = f"""Rate these {game.upper()} cards on similarity (0.0-1.0).

Card A: {q_ctx}

Card B: {c_ctx}

SCORING SCALE:
- 0.0-0.10: Unrelated. Different functions, different archetypes.
- 0.11-0.25: Tangential. Same broad category but different targets/timing/cost.
- 0.26-0.50: Moderate. Same function AND similar cost, or strong co-occurrence.
- 0.51-0.75: Strong similarity. Competitive alternatives, similar efficiency.
- 0.76-0.90: Near-substitute. Functionally interchangeable, minor differences.
- 0.91-1.0: Functional reprint or strictly-better/worse pair.

CALIBRATION: Lightning Bolt vs Shock = 0.70. Path to Exile vs Swords = 0.80. Sol Ring vs Wrath of God = 0.05. Most random pairs = 0.05-0.15.

Respond ONLY with JSON:
{{"similarity_score": 0.0, "functional_score": 0.0, "synergy_score": 0.0, "meta_relevance": 0.0}}

- similarity_score: overall similarity
- functional_score: how well one replaces the other
- synergy_score: how well they work together in a deck
- meta_relevance: co-occurrence in competitive decks"""
                else:
                    prompt = f"""Rate these {game.upper()} cards (0.0-1.0):

A: {q_ctx}

B: {c_ctx}

Anchors: 1.0=reprint, 0.8=same role, 0.6=similar function, 0.4=same archetype, 0.2=tangential, 0.0=unrelated.
Respond with JSON: {{"similarity_score": 0.0, "functional_score": 0.0, "synergy_score": 0.0, "meta_relevance": 0.0}}"""

                messages = [
                    {
                        "role": "system",
                        "content": "You are a card game expert. Respond with JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ]

                if use_multi:
                    from multi_model_annotate import annotate_pair

                    result = await annotate_pair(query, candidate, q_ctx, c_ctx, game)
                    ann = {
                        dim: result.get(dim, 0)
                        for dim in [
                            "similarity_score",
                            "functional_score",
                            "synergy_score",
                            "meta_relevance",
                        ]
                    }
                    ann["_provenance"] = result.get("_provenance", {})
                    ann["confidence"] = result.get("confidence", 0)
                    ann["tier_used"] = result.get("tier_used", "unknown")
                elif use_groq:
                    ann = await _call_groq(messages, groq_model, groq_key)
                elif use_cerebras:
                    ann = await _call_openai_compatible(
                        messages,
                        cerebras_model,
                        cerebras_key,
                        "https://api.cerebras.ai/v1",
                    )
                elif use_ollama:
                    ann = await _call_ollama(messages, ollama_model)
                elif use_local:
                    ann = await _call_local_openai(messages, local_url, local_model_name)
                else:
                    result = await agent.run(prompt)
                    ann = (
                        result.output.model_dump()
                        if hasattr(result.output, "model_dump")
                        else dict(result.output)
                    )

                if ann is None:
                    logger.warning(f"No JSON parsed for {query} vs {candidate}")
                    return None

                ann["query"] = query
                ann["candidate"] = candidate
                ann["discovery_source"] = source
                ann["model_name"] = model_name
                ann["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
                # Provenance metadata (multi-model sets its own)
                if "_provenance" not in ann:
                    backend = (
                        "groq"
                        if use_groq
                        else "cerebras"
                        if use_cerebras
                        else "ollama"
                        if use_ollama
                        else "local"
                        if use_local
                        else "openrouter"
                    )
                    ann["_provenance"] = {
                        "backend": backend,
                        "model": model_name,
                        "temperature": 0.3,
                        "prompt_version": "enriched_v1"
                        if (use_groq or use_cerebras or use_ollama or use_local)
                        else "compact_v1",
                        "concurrency": effective_concurrency,
                        "game": game,
                        "has_card_context": bool(card_context.get(query)),
                        "script": "annotation_convergence.py",
                    }
                return ann
            except Exception as e:
                logger.error(
                    f"Annotation failed for {query} vs {candidate}: {type(e).__name__}: {e}"
                )
            return None

    tasks = [annotate_one(q, c, src) for q, c, src in pairs]
    for i in range(0, len(tasks), max_concurrent):
        batch = tasks[i : i + max_concurrent]
        batch_results = await asyncio.gather(*batch)
        for r in batch_results:
            if r is not None:
                results.append(r)
        logger.info(f"  Annotated {min(i + max_concurrent, len(tasks))}/{len(tasks)} pairs")

    return results


# ---------------------------------------------------------------------------
# Step 3: Merge into test set (cumulative, deduplicated)
# ---------------------------------------------------------------------------


def merge_annotations(
    test_set: dict,
    new_annotations: list[dict],
) -> tuple[dict, int, int]:
    """Merge new annotations into test set. Returns (updated_test_set, added, deduped)."""
    queries = test_set.get("queries", {})
    added = 0
    deduped = 0

    for ann in new_annotations:
        query = ann.get("card_a", ann.get("query", ""))
        candidate = ann.get("card_b", ann.get("candidate", ""))
        if not query or not candidate:
            continue

        if query not in queries:
            queries[query] = {
                "highly_relevant": [],
                "relevant": [],
                "somewhat_relevant": [],
                "marginally_relevant": [],
                "irrelevant": [],
                "modes": {},
                "use_case": "convergence",
                "annotations": [],
            }

        qdata = queries[query]

        # Check for duplicate (same query+candidate pair)
        existing_candidates = {a.get("candidate", "") for a in qdata.get("annotations", [])}
        if candidate in existing_candidates:
            # Average with existing annotation
            for existing_ann in qdata["annotations"]:
                if existing_ann.get("candidate") == candidate:
                    n = existing_ann.get("n_annotators", 1)
                    for field in [
                        "similarity_score",
                        "functional_score",
                        "synergy_score",
                        "meta_relevance",
                        "substitutability",
                    ]:
                        old_val = existing_ann.get(field)
                        new_val = ann.get(field)
                        if old_val is not None and new_val is not None:
                            existing_ann[field] = (old_val * n + new_val) / (n + 1)
                    existing_ann["n_annotators"] = n + 1
                    deduped += 1
                    break
            continue

        # New annotation
        merged_ann = {
            "query": query,
            "candidate": candidate,
            "similarity_score": ann.get("similarity_score", 0),
            "functional_score": ann.get("functional_score", 0),
            "synergy_score": ann.get("synergy_score", 0),
            "meta_relevance": ann.get("meta_relevance", 0),
            "substitutability": ann.get("substitutability", 0),
            "confidence": ann.get("confidence", 0.5),
            "llm_model": ann.get("model_name", "unknown"),
            "discovery_source": ann.get("discovery_source", "unknown"),
            "n_annotators": 1,
            "timestamp": ann.get("timestamp", ""),
        }

        # Copy extended fields if present
        for field in [
            "reasoning",
            "is_substitute",
            "combo_potential",
            "same_archetype",
            "upgrade_direction",
            "card_a_role",
            "card_b_role",
            "card_a_power_level",
            "card_b_power_level",
            "relationship_types",
            "_provenance",
            "tier_used",
        ]:
            if field in ann:
                merged_ann[field] = ann[field]

        qdata["annotations"].append(merged_ann)

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

        # Update mode
        func = float(ann.get("functional_score", 0))
        syn = float(ann.get("synergy_score", 0))
        if func > syn:
            mode = "substitution"
        elif syn > 0.3:
            mode = "synergy"
        else:
            mode = "meta"
        qdata.setdefault("modes", {})[candidate] = mode

        added += 1

    test_set["queries"] = queries
    test_set["num_queries"] = len(queries)
    test_set["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    return test_set, added, deduped


# ---------------------------------------------------------------------------
# Step 4: Save and evaluate
# ---------------------------------------------------------------------------


def save_test_set(test_set: dict, game: str) -> Path:
    path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    with open(path, "w") as f:
        json.dump(test_set, f, indent=2, ensure_ascii=False)
    return path


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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Annotation-eval convergence loop")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument(
        "--budget", type=int, default=200, help="Max new pairs to annotate per cycle"
    )
    parser.add_argument(
        "--cycles", type=int, default=1, help="Number of discover-annotate-eval cycles"
    )
    parser.add_argument(
        "--embeddings", default="", help="Comma-separated embedding names for candidate discovery"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be annotated without calling LLM"
    )
    parser.add_argument("--k", type=int, default=10, help="Top-K neighbors per query")
    parser.add_argument(
        "--model", default="", help="LLM model for annotation (default: cheapest from env or haiku)"
    )
    parser.add_argument("--concurrency", type=int, default=20, help="Max concurrent LLM calls")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Default embeddings: current best + text for diversity
    if args.embeddings:
        embedding_names = [e.strip() for e in args.embeddings.split(",")]
    else:
        embedding_names = [
            f"{args.game}_v7_spectral_mu3",  # current best
            f"{args.game}_v7_fused",  # deployed (different ranking)
        ]

    for cycle in range(1, args.cycles + 1):
        print(f"\n{'=' * 60}")
        print(f"  CYCLE {cycle}/{args.cycles}: {args.game.upper()}")
        print(f"{'=' * 60}")

        # Load current test set
        test_set = load_test_set(args.game)
        queries = test_set.get("queries", {})
        annotated = get_annotated_pairs(queries)
        total_annotations = sum(len(q.get("annotations", [])) for q in queries.values())
        print(
            f"  Current: {len(queries)} queries, {total_annotations} annotations, "
            f"{len(annotated)} unique pairs"
        )

        # Step 1: Discover unannotated candidates
        print(f"\n  [1/4] Discovering unannotated candidates (budget={args.budget})...")
        candidates = discover_candidates(
            args.game,
            queries,
            embedding_names,
            budget=args.budget,
            k=args.k,
        )

        if not candidates:
            print("  No new candidates found. Annotations are saturated for top-K.")
            break

        source_counts = Counter(src for _, _, src in candidates)
        print(f"  Found {len(candidates)} pairs: {dict(source_counts)}")

        if args.dry_run:
            print(f"\n  [DRY RUN] Would annotate {len(candidates)} pairs:")
            for q, c, src in candidates[:10]:
                print(f"    {q} vs {c} ({src})")
            if len(candidates) > 10:
                print(f"    ... and {len(candidates) - 10} more")
            continue

        # Step 2: Annotate
        print(f"\n  [2/4] Annotating {len(candidates)} pairs...")
        card_context = load_card_context(args.game)
        new_annotations = asyncio.run(
            annotate_pairs(
                candidates,
                args.game,
                card_context,
                args.concurrency,
                model_override=args.model or None,
            )
        )
        print(f"  Got {len(new_annotations)} annotations")

        if not new_annotations:
            print("  No annotations produced. Check API keys.")
            continue

        # Step 3: Merge
        print("\n  [3/4] Merging into test set...")
        test_set, added, deduped = merge_annotations(test_set, new_annotations)
        print(f"  Added {added} new, averaged {deduped} duplicates")

        # Save
        out_path = save_test_set(test_set, args.game)
        new_total = sum(len(q.get("annotations", [])) for q in test_set["queries"].values())
        print(f"  Saved to {out_path} ({new_total} total annotations)")

        # Step 4: Evaluate
        print("\n  [4/4] Evaluating on enriched test set...")
        import subprocess

        for emb_name in embedding_names:
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts/evaluation/eval_per_mode.py"),
                    "--game",
                    args.game,
                    "--embedding",
                    emb_name,
                    "--quick",
                    "--json",
                ],
                capture_output=True,
                cwd=str(PROJECT_ROOT),
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    r = data[0]
                    sub = r["mode_substitute"]["ndcg_at_k"]
                    overall = r["overall_ndcg"]["ndcg_at_k"]
                    n_eval = r["mode_substitute"]["n_evaluated"]
                    print(f"  {emb_name}: sub={sub:.4f} overall={overall:.4f} (n={n_eval})")
                except (json.JSONDecodeError, KeyError, IndexError):
                    print(f"  {emb_name}: eval parse error")
            else:
                print(f"  {emb_name}: eval failed")

    print(f"\n{'=' * 60}")
    print("  Convergence loop complete.")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
