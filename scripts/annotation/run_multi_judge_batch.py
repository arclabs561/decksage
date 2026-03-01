#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic-ai", "pydantic", "python-dotenv", "gensim", "numpy", "anyio"]
# ///
"""
Run multi-judge annotation batch with smart selection and meta-judge resolution.

Pipeline:
1. Select pairs using smart strategies (Lift-weighted, uncertainty, embedding disagreement)
2. Run MultiAnnotatorIAA.annotate_pair_multi() on each pair (parallel)
3. Save results incrementally (checkpoint after every pair)
4. Optionally route disagreements through AgenticMetaJudge (separate phase)

Features:
- Incremental checkpointing: results saved after each pair, safe to kill/resume
- Cost tracking: input/output tokens per model, estimated USD
- Resume support: --resume skips already-completed pairs
- Per-judge timeout: 90s default, skip slow/broken judges

Usage:
  PYTHONPATH=src .venv/bin/python scripts/annotation/run_multi_judge_batch.py \
    --game yugioh --edgelist data/processed/pairs_yugioh_ygoprodeck-tournament.csv \
    --output data/annotations/yugioh_200.json \
    --num-pairs 200 --strategy smart --concurrency 10

Resume after interruption:
  PYTHONPATH=src .venv/bin/python scripts/annotation/run_multi_judge_batch.py \
    --game yugioh --edgelist data/processed/pairs_yugioh_ygoprodeck-tournament.csv \
    --output data/annotations/yugioh_200.json \
    --num-pairs 200 --strategy smart --concurrency 10 --resume
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


# Load API keys
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from ml.annotation.multi_annotator_iaa import MultiAnnotatorIAA


# ── Approximate OpenRouter pricing (USD per 1M tokens, Feb 2026) ──
MODEL_PRICING = {
    # Active ensemble (v2, 7 judges)
    "anthropic/claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "openai/gpt-5.2": {"input": 1.75, "output": 14.00},
    "google/gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "google/gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "deepseek/deepseek-v3.2": {"input": 0.25, "output": 0.40},
    "deepseek/deepseek-chat-v3.1": {"input": 0.15, "output": 0.75},
    "mistralai/mistral-large-2512": {"input": 0.50, "output": 1.50},
    "qwen/qwen3-235b-a22b": {"input": 0.455, "output": 1.82},
    "qwen/qwen3-235b-a22b-2507": {"input": 0.071, "output": 0.10},
    "x-ai/grok-4.1-fast": {"input": 0.20, "output": 0.50},
    # Legacy (from v1 ensemble, kept for cost tracking on old runs)
    "google/gemini-3-flash-preview": {"input": 0.50, "output": 3.00},
    "anthropic/claude-haiku-4.5": {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
    "google/gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
}


class UsageTracker:
    """Thread-safe token usage and cost tracker."""

    def __init__(self):
        self.lock = threading.Lock()
        self.by_model: dict[str, dict[str, int]] = {}  # model -> {input_tokens, output_tokens, requests}

    def record(self, model: str, usage: dict):
        with self.lock:
            if model not in self.by_model:
                self.by_model[model] = {
                    "input_tokens": 0, "output_tokens": 0,
                    "cache_write_tokens": 0, "cache_read_tokens": 0,
                    "requests": 0,
                }
            self.by_model[model]["input_tokens"] += usage.get("input_tokens", 0)
            self.by_model[model]["output_tokens"] += usage.get("output_tokens", 0)
            self.by_model[model]["cache_write_tokens"] += usage.get("cache_write_tokens", 0)
            self.by_model[model]["cache_read_tokens"] += usage.get("cache_read_tokens", 0)
            self.by_model[model]["requests"] += usage.get("requests", 0)

    def _model_cost(self, model: str, usage: dict) -> float:
        pricing = MODEL_PRICING.get(model, {"input": 2.0, "output": 8.0})
        cost = usage["input_tokens"] / 1e6 * pricing["input"]
        cost += usage["output_tokens"] / 1e6 * pricing["output"]
        if "cache_write" in pricing:
            cost += usage["cache_write_tokens"] / 1e6 * pricing["cache_write"]
        if "cache_read" in pricing:
            cost += usage["cache_read_tokens"] / 1e6 * pricing["cache_read"]
        return cost

    def estimated_cost_usd(self) -> float:
        with self.lock:
            return sum(self._model_cost(m, u) for m, u in self.by_model.items())

    def summary(self) -> str:
        lines = []
        with self.lock:
            total_in, total_out, total_cw, total_cr, total_req = 0, 0, 0, 0, 0
            for model, usage in sorted(self.by_model.items()):
                cost = self._model_cost(model, usage)
                cache_str = ""
                if usage["cache_write_tokens"] or usage["cache_read_tokens"]:
                    cache_str = f" / cache: {usage['cache_write_tokens']:,}w+{usage['cache_read_tokens']:,}r"
                lines.append(
                    f"  {model.split('/')[-1]}: "
                    f"{usage['input_tokens']:,} in / {usage['output_tokens']:,} out"
                    f"{cache_str} / {usage['requests']} req / ${cost:.4f}"
                )
                total_in += usage["input_tokens"]
                total_out += usage["output_tokens"]
                total_cw += usage["cache_write_tokens"]
                total_cr += usage["cache_read_tokens"]
                total_req += usage["requests"]
            cache_total = ""
            if total_cw or total_cr:
                cache_total = f" / cache: {total_cw:,}w+{total_cr:,}r"
            lines.append(
                f"  TOTAL: {total_in:,} in / {total_out:,} out"
                f"{cache_total} / {total_req} req / ${self.estimated_cost_usd():.4f}"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        with self.lock:
            return {
                "by_model": dict(self.by_model),
                "estimated_cost_usd": round(self.estimated_cost_usd(), 4),
            }


class ProgressTracker:
    """Thread-safe progress tracker with live stats."""

    def __init__(self, total: int):
        self.total = total
        self.lock = threading.Lock()
        self.completed = 0
        self.failed = 0
        self.agreements = {"high": 0, "medium": 0, "low": 0, "disagreement": 0}
        self.judge_participation: dict[str, int] = {}
        self.t0 = time.monotonic()
        self.pair_times: list[float] = []

    def record(self, agreement_level: str, judges: list[str], elapsed_pair: float):
        with self.lock:
            self.completed += 1
            self.agreements[agreement_level] = self.agreements.get(agreement_level, 0) + 1
            self.pair_times.append(elapsed_pair)
            for j in judges:
                self.judge_participation[j] = self.judge_participation.get(j, 0) + 1

    def record_failure(self):
        with self.lock:
            self.failed += 1

    def summary_line(self, usage: UsageTracker | None = None) -> str:
        with self.lock:
            done = self.completed + self.failed
            elapsed = time.monotonic() - self.t0
            rate = elapsed / max(done, 1)
            remaining = (self.total - done) * rate
            pct = 100 * done / self.total if self.total else 0
            agree = self.agreements.get("high", 0) + self.agreements.get("medium", 0)
            disagree = self.agreements.get("disagreement", 0) + self.agreements.get("low", 0)
            cost_str = f" | ${usage.estimated_cost_usd():.3f}" if usage else ""
            return (
                f"  Progress: {done}/{self.total} ({pct:.0f}%) | "
                f"{rate:.1f}s/pair | ETA {remaining/60:.0f}m | "
                f"agree={agree} disagree={disagree} fail={self.failed}{cost_str}"
            )

    def final_report(self, usage: UsageTracker | None = None) -> str:
        elapsed = time.monotonic() - self.t0
        lines = [
            f"\n{'='*60}",
            f"Batch complete: {self.completed}/{self.total} annotated, {self.failed} failed",
            f"Wall time: {elapsed:.0f}s ({elapsed/max(self.completed,1):.1f}s/pair)",
            f"Agreement: {dict(self.agreements)}",
        ]
        if self.judge_participation:
            total_possible = self.completed
            lines.append("Judge participation:")
            for j, count in sorted(self.judge_participation.items()):
                pct = 100 * count / total_possible if total_possible else 0
                lines.append(f"  {j}: {count}/{total_possible} ({pct:.0f}%)")
        if self.pair_times:
            sorted_t = sorted(self.pair_times)
            p50 = sorted_t[len(sorted_t) // 2]
            p95 = sorted_t[int(len(sorted_t) * 0.95)]
            lines.append(f"Latency: p50={p50:.1f}s p95={p95:.1f}s")
        if usage:
            lines.append(f"Token usage & cost:\n{usage.summary()}")
        lines.append(f"{'='*60}")
        return "\n".join(lines)


from ml.utils.data_loading import load_edgelist as _load_edgelist_raw


def load_edgelist(path: Path) -> list[tuple[str, str, float]]:
    """Load edgelist with annotation-specific filtering (self-loops, unresolved IDs)."""
    raw = _load_edgelist_raw(path)
    return [
        (c1, c2, w) for c1, c2, w in raw
        if c1 != c2 and not c1.startswith("Card_") and not c2.startswith("Card_")
    ]


def select_pairs_random(
    edges: list[tuple[str, str, float]], num_pairs: int, seed: int = 42
) -> list[tuple[str, str]]:
    """Stratified random sampling across weight quartiles."""
    rng = random.Random(seed)
    sorted_edges = sorted(edges, key=lambda e: e[2], reverse=True)
    n = len(sorted_edges)
    buckets = [
        (sorted_edges[: n // 4], 0.30),
        (sorted_edges[n // 4 : n // 2], 0.30),
        (sorted_edges[n // 2 : 3 * n // 4], 0.20),
        (sorted_edges[3 * n // 4 :], 0.20),
    ]
    selected, seen = [], set()
    for bucket, frac in buckets:
        count = int(num_pairs * frac)
        sample = rng.sample(bucket, min(count, len(bucket)))
        for c1, c2, _ in sample:
            key = tuple(sorted([c1, c2]))
            if key not in seen:
                seen.add(key)
                selected.append((c1, c2))
    if len(selected) < num_pairs:
        remaining = [(c1, c2) for c1, c2, _ in edges if tuple(sorted([c1, c2])) not in seen]
        extra = rng.sample(remaining, min(num_pairs - len(selected), len(remaining)))
        selected.extend(extra)
    return selected[:num_pairs]


def select_pairs_hub(
    edges: list[tuple[str, str, float]], num_pairs: int, seed: int = 42,
    pairs_per_hub: int = 8, min_degree: int = 20,
) -> list[tuple[str, str]]:
    """Hub-centric sampling: pick high-degree nodes, sample multiple neighbors per hub.

    Ensures each hub card appears in enough pairs for meaningful test set queries.
    Designed for large card pools (MTG 7.5M edges) where random sampling is too sparse.

    Args:
        edges: List of (card1, card2, weight) tuples.
        num_pairs: Total pairs to sample.
        pairs_per_hub: Neighbors to sample per hub card.
        min_degree: Minimum node degree to qualify as a hub.
    """
    rng = random.Random(seed)

    # Build adjacency with weights
    adj: dict[str, list[tuple[str, float]]] = {}
    for c1, c2, w in edges:
        adj.setdefault(c1, []).append((c2, w))
        adj.setdefault(c2, []).append((c1, w))

    # Select hub cards: high degree nodes, shuffled
    hubs = [card for card, neighbors in adj.items() if len(neighbors) >= min_degree]
    if not hubs:
        # Fall back to top-degree nodes
        degree_sorted = sorted(adj.items(), key=lambda x: len(x[1]), reverse=True)
        hubs = [card for card, _ in degree_sorted[:num_pairs // pairs_per_hub + 10]]
    rng.shuffle(hubs)

    selected = []
    seen = set()
    num_hubs_needed = (num_pairs // pairs_per_hub) + 5  # slight overshoot

    for hub in hubs[:num_hubs_needed]:
        neighbors = adj.get(hub, [])
        # Sort by weight (descending) and take a mix: top-weight + random
        neighbors_sorted = sorted(neighbors, key=lambda x: x[1], reverse=True)
        # Take top half from high-weight, half random for diversity
        n_top = pairs_per_hub // 2
        n_rand = pairs_per_hub - n_top
        top_picks = [(hub, n) for n, _ in neighbors_sorted[:n_top]]
        remaining = [(hub, n) for n, _ in neighbors_sorted[n_top:]]
        if remaining:
            rand_picks = rng.sample(remaining, min(n_rand, len(remaining)))
        else:
            rand_picks = []

        for hub_card, neighbor in top_picks + rand_picks:
            key = tuple(sorted([hub_card, neighbor]))
            if key not in seen:
                seen.add(key)
                selected.append((hub_card, neighbor))

        if len(selected) >= num_pairs:
            break

    return selected[:num_pairs]


def select_pairs_focused(
    edges: list[tuple[str, str, float]], num_pairs: int, seed: int = 42, min_weight: float = 5.0
) -> list[tuple[str, str]]:
    """Select high-weight (high Lift / high co-occurrence) pairs for synergy signal."""
    rng = random.Random(seed)
    high_weight = [(c1, c2) for c1, c2, w in edges if w >= min_weight]
    if not high_weight:
        high_weight = [(c1, c2) for c1, c2, _ in sorted(edges, key=lambda e: e[2], reverse=True)]
    rng.shuffle(high_weight)
    seen = set()
    selected = []
    for c1, c2 in high_weight:
        key = tuple(sorted([c1, c2]))
        if key not in seen:
            seen.add(key)
            selected.append((c1, c2))
        if len(selected) >= num_pairs:
            break
    return selected[:num_pairs]


def select_pairs_smart(
    edges: list[tuple[str, str, float]],
    num_pairs: int,
    seed: int = 42,
    embedding_paths: list[Path] | None = None,
    prior_annotations_path: Path | None = None,
) -> list[tuple[str, str]]:
    """Smart selection: Lift-weighted + embedding disagreement + active learning feedback.

    Allocation:
    - 40% high-Lift pairs (strong synergy signal)
    - 30% embedding-disagreement pairs (where models are confused)
    - 20% random diverse (exploration)
    - 10% re-annotate prior disagreements (active learning)
    """
    rng = random.Random(seed)
    seen = set()
    selected = []

    def _add(pairs: list[tuple[str, str]], budget: int):
        added = 0
        for c1, c2 in pairs:
            key = tuple(sorted([c1, c2]))
            if key not in seen:
                seen.add(key)
                selected.append((c1, c2))
                added += 1
            if added >= budget:
                break

    # -- Bucket 1: High-Lift pairs (40%) --
    high_lift_budget = int(num_pairs * 0.40)
    sorted_by_weight = sorted(edges, key=lambda e: e[2], reverse=True)
    top_pairs = [(c1, c2) for c1, c2, _ in sorted_by_weight[:max(high_lift_budget * 3, 500)]]
    rng.shuffle(top_pairs)
    _add(top_pairs, high_lift_budget)
    print(f"  Smart selection: {len(selected)} high-Lift pairs")

    # -- Bucket 2: Embedding disagreement (30%) --
    disagree_budget = int(num_pairs * 0.30)
    models = _load_embedding_models(embedding_paths)
    if models and len(models) >= 2:
        candidate_pool = [(c1, c2) for c1, c2, _ in edges if tuple(sorted([c1, c2])) not in seen]
        rng.shuffle(candidate_pool)
        candidate_pool = candidate_pool[:5000]

        scored = []
        for c1, c2 in candidate_pool:
            preds = []
            for m in models.values():
                try:
                    if c1 in m and c2 in m:
                        preds.append(float(m.similarity(c1, c2)))
                except Exception:
                    pass
            if len(preds) >= 2:
                mean_p = sum(preds) / len(preds)
                std = (sum((p - mean_p) ** 2 for p in preds) / len(preds)) ** 0.5
                scored.append((c1, c2, std))

        scored.sort(key=lambda x: x[2], reverse=True)
        _add([(c1, c2) for c1, c2, _ in scored], disagree_budget)
        print(f"  Smart selection: +{disagree_budget} embedding-disagreement pairs ({len(models)} models)")
    else:
        mid = len(sorted_by_weight) // 3
        mid_pairs = [(c1, c2) for c1, c2, _ in sorted_by_weight[mid : mid * 2]]
        rng.shuffle(mid_pairs)
        _add(mid_pairs, disagree_budget)
        print(f"  Smart selection: +{disagree_budget} mid-weight pairs (no embeddings for disagreement)")

    # -- Bucket 3: Random diverse (20%) --
    diverse_budget = int(num_pairs * 0.20)
    all_remaining = [(c1, c2) for c1, c2, _ in edges if tuple(sorted([c1, c2])) not in seen]
    rng.shuffle(all_remaining)
    _add(all_remaining, diverse_budget)
    print(f"  Smart selection: +{diverse_budget} random diverse pairs")

    # -- Bucket 4: Re-annotate prior disagreements (10%) --
    reannotate_budget = num_pairs - len(selected)
    if prior_annotations_path and prior_annotations_path.exists():
        with open(prior_annotations_path) as f:
            prior = json.load(f)
        disagreements = [
            (lbl["card1"], lbl["card2"])
            for lbl in prior.get("labels", [])
            if lbl.get("agreement_level") == "disagreement"
        ]
        rng.shuffle(disagreements)
        _add(disagreements, reannotate_budget)
        print(f"  Smart selection: +{min(reannotate_budget, len(disagreements))} re-annotation of prior disagreements")
    elif reannotate_budget > 0:
        _add(all_remaining, reannotate_budget)
        print(f"  Smart selection: +{reannotate_budget} extra random (no prior annotations)")

    return selected[:num_pairs]


def _load_embedding_models(paths: list[Path] | None) -> dict:
    """Load KeyedVectors embedding models for disagreement scoring."""
    if not paths:
        embed_dir = Path("data/embeddings")
        if embed_dir.exists():
            paths = sorted(embed_dir.glob("*.wv"))[:4]
    if not paths:
        return {}
    try:
        from gensim.models import KeyedVectors
    except ImportError:
        return {}
    models = {}
    for p in paths:
        if p.exists():
            try:
                models[p.stem] = KeyedVectors.load(str(p))
            except Exception as e:
                print(f"  Warning: couldn't load {p}: {e}")
    return models


def _judge_entry(ann) -> dict:
    """Serialize a single judge annotation with full provenance and structured output."""
    entry = {
        "similarity_score": ann.similarity_score,
        "similarity_type": ann.similarity_type,
        "is_substitute": ann.is_substitute,
        "reasoning": ann.reasoning,
        "functional_score": ann.functional_score,
        "synergy_score": ann.synergy_score,
        "meta_relevance": getattr(ann, "meta_relevance", None),
        "key_similarities": ann.key_similarities,
        "key_differences": ann.key_differences,
        "model_name": ann.model_name,
        "model_params": ann.model_params,
        "prompt_version": ann.prompt_version,
        "prompt_hash": ann.prompt_hash,
        "timestamp": ann.timestamp,
    }
    return {k: v for k, v in entry.items() if v is not None}


def _result_entry(result, game: str) -> dict:
    """Convert a MultiAnnotatorResult to a serializable dict."""
    entry = {
        "card1": result.card1,
        "card2": result.card2,
        "game": game,
        "timestamp": datetime.now().isoformat(),
        "agreement_level": result.agreement_level,
        "iaa_metrics": result.iaa_metrics,
        "consensus": {
            "similarity_score": result.consensus_annotation.similarity_score,
            "similarity_type": result.consensus_annotation.similarity_type,
            "is_substitute": result.consensus_annotation.is_substitute,
            "reasoning": result.consensus_annotation.reasoning,
        } if result.consensus_annotation else None,
        "per_judge": {
            name: _judge_entry(ann)
            for name, ann in result.annotations.items()
        },
    }
    # Include usage if available
    if result.usage_by_judge:
        entry["usage"] = result.usage_by_judge
    return entry


# ── Checkpoint I/O ──

def _checkpoint_path(output_path: Path) -> Path:
    return output_path.with_suffix(".checkpoint.jsonl")


def _load_checkpoint(output_path: Path) -> list[dict]:
    """Load completed results from checkpoint file."""
    cp = _checkpoint_path(output_path)
    if not cp.exists():
        return []
    results = []
    with open(cp) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return results


def _append_checkpoint(output_path: Path, entry: dict):
    """Append one result to checkpoint file (JSONL, one line per pair)."""
    cp = _checkpoint_path(output_path)
    cp.parent.mkdir(parents=True, exist_ok=True)
    with open(cp, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def annotate_one_pair(
    iaa: MultiAnnotatorIAA,
    card1: str,
    card2: str,
    game: str,
    idx: int,
    total: int,
    sem: asyncio.Semaphore,
    card_attrs: dict[str, dict] | None = None,
    edge_stats: dict | None = None,
    progress: ProgressTracker | None = None,
    usage: UsageTracker | None = None,
    output_path: Path | None = None,
) -> tuple[dict | None, object | None]:
    """Annotate a single pair. Returns (entry_dict, raw_result_if_disagreement)."""
    async with sem:
        print(f"  [{idx}/{total}] {card1} <-> {card2}", flush=True)
        t_start = time.monotonic()
        try:
            # Build dynamic card context for this pair
            card_context = None
            if card_attrs:
                pair_ctx = {}
                for name in (card1, card2):
                    if name in card_attrs:
                        pair_ctx[name] = card_attrs[name]
                if pair_ctx:
                    card_context = pair_ctx

            # Build graph context from edge stats (factual data, not scoring guidance)
            graph_context = None
            if edge_stats:
                pair_key = tuple(sorted([card1, card2]))
                cooccur = edge_stats["pair_counts"].get(pair_key, 0)
                freq1 = edge_stats["card_frequency"].get(card1, 0)
                freq2 = edge_stats["card_frequency"].get(card2, 0)
                total_decks = edge_stats.get("total_decks", 0)
                lines = ["\n**CO-OCCURRENCE DATA (from tournament decklists):**"]
                lines.append(f"- This pair co-occurs in {cooccur} decks")
                if total_decks > 0:
                    lines.append(f"- {card1}: appears in {freq1} decks ({freq1/total_decks*100:.1f}% of {total_decks} total)")
                    lines.append(f"- {card2}: appears in {freq2} decks ({freq2/total_decks*100:.1f}% of {total_decks} total)")
                    if freq1 > 0 and freq2 > 0:
                        # Jaccard-like: co-occur / (freq1 + freq2 - co-occur)
                        union = freq1 + freq2 - cooccur
                        jaccard = cooccur / union if union > 0 else 0
                        lines.append(f"- Deck overlap (Jaccard): {jaccard:.3f}")
                graph_context = "\n".join(lines)

            result = await iaa.annotate_pair_multi(card1, card2, graph_context=graph_context, card_context=card_context)
            entry = _result_entry(result, game)
            elapsed_pair = time.monotonic() - t_start
            alpha = result.iaa_metrics.get("krippendorff_alpha", 0)
            n_judges = len(result.annotations)
            scores = [f"{a.similarity_score:.2f}" for a in result.annotations.values()]

            # Track usage
            if usage and result.usage_by_judge:
                for judge_name, judge_usage in result.usage_by_judge.items():
                    # Find the model name from annotations
                    ann = result.annotations.get(judge_name)
                    model = ann.model_name if ann else judge_name
                    usage.record(model, judge_usage)

            print(
                f"    [{idx}] {result.agreement_level} "
                f"(alpha={alpha:.2f}, {n_judges} judges, scores=[{','.join(scores)}]) "
                f"{elapsed_pair:.1f}s"
            )
            if progress:
                progress.record(result.agreement_level, list(result.annotations.keys()), elapsed_pair)
                # Print running summary every 10 pairs
                if (progress.completed + progress.failed) % 10 == 0:
                    print(progress.summary_line(usage), flush=True)

            # Incremental checkpoint
            if output_path:
                _append_checkpoint(output_path, entry)

            # Reset watchdog: if the event loop hangs after all pairs complete,
            # SIGALRM fires after the last successful pair.
            # Budget: JUDGE_TIMEOUT (45s) + 30s buffer = 75s, enough for
            # the next concurrent batch to complete before alarm fires.
            try:
                signal.alarm(75)
            except Exception:
                pass

            return entry, result if result.agreement_level == "disagreement" else None
        except Exception as e:
            print(f"    [{idx}] FAILED ({time.monotonic() - t_start:.1f}s): {e}")
            if progress:
                progress.record_failure()
            return None, None


async def resolve_disagreements(
    disagreements: list[tuple[dict, object]],
    iaa: MultiAnnotatorIAA,
    sem: asyncio.Semaphore,
) -> list[dict]:
    """Route disagreement pairs through agentic meta-judge for multi-round resolution."""
    try:
        from ml.annotation.agentic_meta_judge import AgenticMetaJudge
    except ImportError:
        print("  Warning: agentic_meta_judge not available, skipping resolution")
        return []

    meta_judge = AgenticMetaJudge(
        max_rounds=2,
        min_consensus_threshold=0.6,
        min_quality_threshold=0.5,
    )
    resolved = []

    async def _resolve_one(entry: dict, raw_result, idx: int):
        async with sem:
            c1, c2 = entry["card1"], entry["card2"]
            print(f"    Meta-judge [{idx}/{len(disagreements)}] {c1} <-> {c2}", flush=True)
            try:
                final_round, all_rounds = await meta_judge.moderate_multi_round(
                    initial_annotations=raw_result.annotations,
                    multi_annotator=iaa,
                    card1=c1,
                    card2=c2,
                )
                action = final_round.consensus_decision.recommended_action if final_round.consensus_decision else "unknown"
                rounds_used = len(all_rounds)

                entry["meta_judge"] = {
                    "action": action,
                    "rounds": rounds_used,
                    "final_consensus_score": (
                        final_round.consensus_decision.consensus_score
                        if final_round.consensus_decision else None
                    ),
                }

                if final_round.annotations and action in ("accept", "revise"):
                    entry["per_judge_revised"] = {
                        name: {
                            "similarity_score": ann.similarity_score,
                            "similarity_type": ann.similarity_type,
                            "is_substitute": ann.is_substitute,
                            "reasoning": ann.reasoning,
                        }
                        for name, ann in final_round.annotations.items()
                    }
                    entry["agreement_level"] = f"resolved_{action}"

                print(f"      [{idx}] -> {action} after {rounds_used} rounds")
                resolved.append(entry)
            except Exception as e:
                print(f"      [{idx}] -> meta-judge FAILED: {e}")

    tasks = [
        _resolve_one(entry, raw_result, i)
        for i, (entry, raw_result) in enumerate(disagreements, 1)
    ]
    await asyncio.gather(*tasks)
    return resolved


def _load_card_attrs_for_game(game: str) -> dict[str, dict] | None:
    """Load card attributes for dynamic context injection."""
    import csv

    csv_candidates = [
        Path("data/processed/card_attributes_enriched.csv"),
        Path(f"data/processed/{game}_card_attributes.csv"),
        Path(f"data/processed/card_attributes_{game}.csv"),
    ]
    for csv_path in csv_candidates:
        if csv_path.exists():
            attrs = {}
            with open(csv_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("name") or row.get("card_name", "")
                    if name:
                        attrs[name] = {k: v for k, v in row.items() if k not in ("name", "card_name") and v}
            if attrs:
                print(f"  Loaded {len(attrs):,} card attributes from {csv_path}")
                return attrs

    json_candidates = [
        Path(f"src/backend/data-full/games/{game}/scryfall/cards"),
    ]
    for json_dir in json_candidates:
        if json_dir.is_dir():
            attrs = {}
            try:
                import zstandard
                for jf in sorted(json_dir.glob("*.json.zst"))[:5]:
                    try:
                        with open(jf, "rb") as fh:
                            dctx = zstandard.ZstdDecompressor()
                            data = json.loads(dctx.decompress(fh.read()))
                        cards = data if isinstance(data, list) else [data]
                        for card in cards:
                            name = card.get("name", "")
                            if name:
                                attrs[name] = {
                                    "oracle_text": card.get("oracle_text", ""),
                                    "type_line": card.get("type_line", ""),
                                    "mana_cost": card.get("mana_cost", ""),
                                    "power": card.get("power"),
                                    "toughness": card.get("toughness"),
                                    "keywords": card.get("keywords", []),
                                    "color_identity": card.get("color_identity", []),
                                    "cmc": card.get("cmc"),
                                }
                    except Exception:
                        continue
            except ImportError:
                pass
            if attrs:
                print(f"  Loaded {len(attrs):,} card attributes from Scryfall ({json_dir})")
                return attrs

    for json_dir in json_candidates:
        if json_dir.is_dir():
            for jf in sorted(json_dir.glob("*.json"))[:5]:
                try:
                    with open(jf) as fh:
                        data = json.load(fh)
                    cards = data if isinstance(data, list) else [data]
                    attrs = {}
                    for card in cards:
                        name = card.get("name", "")
                        if name:
                            attrs[name] = {
                                "oracle_text": card.get("oracle_text", ""),
                                "type_line": card.get("type_line", ""),
                                "mana_cost": card.get("mana_cost", ""),
                                "power": card.get("power"),
                                "toughness": card.get("toughness"),
                                "keywords": card.get("keywords", []),
                                "color_identity": card.get("color_identity", []),
                                "cmc": card.get("cmc"),
                            }
                    if attrs:
                        print(f"  Loaded {len(attrs):,} card attributes from {jf}")
                        return attrs
                except Exception:
                    continue

    print("  No card attributes found (judges will rely on their own knowledge)")
    return None


async def run_batch(
    game: str,
    edgelist_path: Path,
    output_path: Path,
    num_pairs: int,
    seed: int,
    concurrency: int = 10,
    strategy: str = "random",
    resolve: bool = False,
    prior_annotations: Path | None = None,
    card_attrs_path: Path | None = None,
    resume: bool = False,
    format_filter: str | None = None,
    banlist_path: Path | None = None,
) -> dict:
    """Run multi-judge annotation batch with checkpointing and cost tracking."""
    # Load edges
    print(f"Loading edgelist: {edgelist_path}")
    edges = load_edgelist(edgelist_path)
    print(f"  {len(edges):,} edges loaded")

    # Apply ban list filtering if format specified
    if format_filter:
        from ml.utils.banlist_filter import BanlistFilter
        bl_path = banlist_path or Path(f"data/banlists/{game}_banlists.json")
        if bl_path.exists():
            bf = BanlistFilter.load(game, bl_path)
            pre_count = len(edges)
            edges = bf.filter_edges(edges, format_filter)
            removed = pre_count - len(edges)
            print(f"  Ban list filter ({format_filter}): {removed:,} edges removed, {len(edges):,} remaining")
            print(f"  Banned cards in {format_filter}: {bf.stats(format_filter)['num_banned']}")
        else:
            print(f"  Warning: ban list not found at {bl_path}, skipping format filter")

    # Select pairs
    print(f"Selecting {num_pairs} pairs (strategy={strategy})...")
    if strategy == "smart":
        pairs = select_pairs_smart(edges, num_pairs, seed=seed, prior_annotations_path=prior_annotations)
    elif strategy == "focused":
        pairs = select_pairs_focused(edges, num_pairs, seed=seed)
    elif strategy == "hub":
        pairs = select_pairs_hub(edges, num_pairs, seed=seed)
        # Show hub distribution
        from collections import Counter as _HC
        hub_counts = _HC()
        for c1, c2 in pairs:
            hub_counts[c1] += 1
            hub_counts[c2] += 1
        cards_with_3plus = sum(1 for c, n in hub_counts.items() if n >= 3)
        print(f"  Hub sampling: {len(hub_counts)} unique cards, {cards_with_3plus} with 3+ pairs")
    elif strategy == "curriculum":
        from curriculum_sampler import CurriculumSampler
        _card_attrs = _load_card_attrs_for_game(game)
        sampler = CurriculumSampler(edges, card_attrs=_card_attrs, seed=seed)
        stats = sampler.stats()
        print(f"  Difficulty distribution: easy={stats['easy_pct']}, medium={stats['medium_pct']}, hard={stats['hard_pct']}")
        classified = sampler.sample(num_pairs, phase="auto")
        pairs = [(p.card1, p.card2) for p in classified]
        from collections import Counter as _C
        diff_counts = _C(p.difficulty for p in classified)
        print(f"  Selected: easy={diff_counts['easy']}, medium={diff_counts['medium']}, hard={diff_counts['hard']}")
    else:
        pairs = select_pairs_random(edges, num_pairs, seed=seed)
    print(f"  Selected {len(pairs)} pairs")

    # Resume: skip already-completed pairs
    completed_pairs = set()
    existing_results = []
    if resume:
        existing_results = _load_checkpoint(output_path)
        if existing_results:
            completed_pairs = {
                tuple(sorted([r["card1"], r["card2"]])) for r in existing_results
            }
            print(f"  Resuming: {len(completed_pairs)} pairs already completed, skipping")

    remaining_pairs = [
        (c1, c2) for c1, c2 in pairs
        if tuple(sorted([c1, c2])) not in completed_pairs
    ]
    print(f"  Pairs to annotate: {len(remaining_pairs)}")

    if not remaining_pairs:
        print("  All pairs already completed!")
        _finalize(existing_results, game, output_path, strategy)
        return {"total": len(existing_results), "elapsed_s": 0, "skipped": len(completed_pairs)}

    # Load card attributes for dynamic context injection
    print("Loading card attributes for dynamic context...")
    card_attrs = None
    if card_attrs_path and card_attrs_path.exists():
        import csv
        attrs = {}
        with open(card_attrs_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name") or row.get("card_name", "")
                if name:
                    attrs[name] = {k: v for k, v in row.items() if k not in ("name", "card_name") and v}
        if attrs:
            card_attrs = attrs
            print(f"  Loaded {len(card_attrs):,} card attributes from {card_attrs_path}")
    else:
        card_attrs = _load_card_attrs_for_game(game)

    # Load game knowledge
    game_knowledge = None
    gk_path = Path(f"data/game_knowledge/{game}.json")
    if gk_path.exists():
        with open(gk_path) as f:
            game_knowledge = json.load(f)
        n_formats = len(game_knowledge.get("formats", []))
        n_archetypes = len(game_knowledge.get("archetypes", []))
        print(f"  Game knowledge: {gk_path} ({n_formats} formats, {n_archetypes} archetypes)")

    # Initialize multi-annotator system
    print("Initializing multi-annotator IAA system...")
    iaa = MultiAnnotatorIAA(
        annotator_configs=None,
        min_iaa_threshold=0.6,
        use_consensus=True,
        game=game,
        game_knowledge=game_knowledge,
    )
    print(f"  Judges: {list(iaa.agents.keys())}")
    print(f"  Concurrency: {concurrency} pairs in parallel")

    # Build edge stats lookup for per-pair context injection
    # This gives judges factual co-occurrence data without biasing their scores
    print("Building edge stats for per-pair context...")
    from collections import Counter as _Counter
    pair_counts: dict[tuple[str, str], float] = {}
    card_frequency: dict[str, int] = _Counter()
    for c1_e, c2_e, count in edges:
        pair_key = tuple(sorted([c1_e, c2_e]))
        pair_counts[pair_key] = pair_counts.get(pair_key, 0) + count
        card_frequency[c1_e] += 1
        card_frequency[c2_e] += 1
    # Estimate total decks from max card frequency (most popular card ~ appears in most decks)
    total_decks = max(card_frequency.values()) if card_frequency else 0
    edge_stats = {
        "pair_counts": pair_counts,
        "card_frequency": card_frequency,
        "total_decks": total_decks,
    }
    print(f"  {len(pair_counts):,} unique pairs, {len(card_frequency):,} cards, ~{total_decks:,} estimated decks")

    # Phase 1: Parallel annotation with checkpointing
    # Judge-level timeouts use anyio.move_on_after (works on asyncio backend).
    sem = asyncio.Semaphore(concurrency)
    t0 = time.monotonic()
    progress = ProgressTracker(len(remaining_pairs))
    usage_tracker = UsageTracker()

    pair_coros = [
        annotate_one_pair(
            iaa, c1, c2, game, i, len(remaining_pairs), sem,
            card_attrs=card_attrs, edge_stats=edge_stats,
            progress=progress, usage=usage_tracker,
            output_path=output_path,
        )
        for i, (c1, c2) in enumerate(remaining_pairs, 1)
    ]
    # Hard deadline: 75s per batch of concurrent pairs + 30s buffer.
    # If asyncio.gather blocks (httpx zombie tasks), we fall through
    # and finalize from checkpoint data.
    batch_timeout = 75.0 * max(len(remaining_pairs) / concurrency, 1) + 30
    try:
        raw_results = await asyncio.wait_for(
            asyncio.gather(*pair_coros, return_exceptions=True),
            timeout=batch_timeout,
        )
    except TimeoutError:
        print(f"\n  [WARN] Batch timed out after {batch_timeout:.0f}s (httpx zombie tasks)")
        print("  Finalizing from checkpoint data...")
        raw_results = []

    new_results = []
    disagreements = []
    for item in raw_results:
        if isinstance(item, Exception):
            print(f"  Pair-level exception: {item}")
            continue
        entry, raw_result = item
        if entry is not None:
            new_results.append(entry)
            if raw_result is not None:
                disagreements.append((entry, raw_result))

    print(progress.final_report(usage_tracker))

    # Combine with existing results from resume
    all_results = existing_results + new_results

    # Phase 2: Meta-judge resolution (optional, separate phase)
    n_disagree = len(disagreements)
    meta_judge_resolved = 0
    if resolve and disagreements:
        print(f"\nPhase 2: Meta-judge resolution for {n_disagree} disagreements...")
        meta_sem = asyncio.Semaphore(max(concurrency // 2, 1))
        resolved = await resolve_disagreements(disagreements, iaa, meta_sem)
        meta_judge_resolved = len(resolved)
        print(f"  Resolved: {meta_judge_resolved}/{n_disagree}")

    elapsed = time.monotonic() - t0
    print(f"\nTotal: {len(all_results)} pairs in {elapsed:.0f}s ({elapsed/max(len(new_results),1):.1f}s/pair)")

    # Save final output
    _finalize(
        all_results, game, output_path, strategy,
        meta_judge_resolved=meta_judge_resolved,
        usage=usage_tracker,
    )
    print(f"Saved: {output_path}")

    # Clean up checkpoint now that final output is written
    cp = _checkpoint_path(output_path)
    if cp.exists():
        cp.unlink()
        print(f"Cleaned up checkpoint: {cp}")

    # Save disagreement manifest for active learning
    if disagreements:
        manifest_path = output_path.with_suffix(".disagreements.json")
        _save_disagreement_manifest(disagreements, manifest_path)
        print(f"Disagreement manifest: {manifest_path} ({len(disagreements)} pairs)")

    return {
        "total": len(all_results),
        "new": len(new_results),
        "resumed": len(existing_results),
        "elapsed_s": round(elapsed, 1),
        "disagreements": n_disagree,
        "cost_usd": round(usage_tracker.estimated_cost_usd(), 4),
    }


def _recompute_agreement(results: list[dict]) -> list[dict]:
    """Recompute agreement using 3-bin scheme, z-normalization, and MACE-style weighting.

    Pipeline:
    1. Z-normalize each judge's scores (remove additive scale bias)
    2. Estimate judge reliability via mean pairwise Spearman correlation
    3. Compute weighted consensus using reliability weights on z-scores
    4. Classify agreement using 3-bin majority voting
    """
    from collections import defaultdict

    def _bin3(score: float) -> str:
        if score < 0.35:
            return "low"
        elif score < 0.65:
            return "mid"
        return "high"

    # -- Step 1: Collect and z-normalize per judge --
    judge_scores: dict[str, list[float]] = defaultdict(list)
    judge_pair_idx: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(results):
        for j, a in r.get("per_judge", {}).items():
            s = a.get("similarity_score")
            if s is not None:
                judge_scores[j].append(s)
                judge_pair_idx[j].append(i)

    z_scores: dict[str, dict[int, float]] = {}
    judge_stats: dict[str, dict] = {}
    for j, scores in judge_scores.items():
        if len(scores) < 2:
            continue
        mu = sum(scores) / len(scores)
        std = (sum((s - mu) ** 2 for s in scores) / len(scores)) ** 0.5
        judge_stats[j] = {"mean": round(mu, 4), "std": round(std, 4), "n": len(scores)}
        if std < 1e-8:
            z_scores[j] = dict.fromkeys(judge_pair_idx[j], 0.5)
            continue
        raw_z = [(s - mu) / std for s in scores]
        z_min, z_max = min(raw_z), max(raw_z)
        z_range = z_max - z_min if z_max > z_min else 1.0
        z_scores[j] = {
            idx: (z - z_min) / z_range
            for idx, z in zip(judge_pair_idx[j], raw_z)
        }

    # -- Step 2: Estimate judge reliability via mean Spearman correlation --
    # A judge's reliability = mean correlation with all other judges on z-scores.
    # Higher correlation = more aligned with ensemble = higher weight.
    judges = sorted(z_scores.keys())
    judge_reliability: dict[str, float] = {}
    for j1 in judges:
        correlations = []
        for j2 in judges:
            if j1 == j2:
                continue
            # Find pairs where both judges scored
            common_pairs = set(z_scores[j1].keys()) & set(z_scores[j2].keys())
            if len(common_pairs) < 10:
                continue
            pairs_sorted = sorted(common_pairs)
            s1 = [z_scores[j1][p] for p in pairs_sorted]
            s2 = [z_scores[j2][p] for p in pairs_sorted]
            # Spearman via rank correlation
            def _rank(vals):
                indexed = sorted(range(len(vals)), key=lambda i: vals[i])
                ranks = [0.0] * len(vals)
                for rank_pos, idx in enumerate(indexed):
                    ranks[idx] = rank_pos
                return ranks
            r1, r2 = _rank(s1), _rank(s2)
            n = len(r1)
            mean_r1 = sum(r1) / n
            mean_r2 = sum(r2) / n
            cov = sum((r1[k] - mean_r1) * (r2[k] - mean_r2) for k in range(n))
            std1 = (sum((r1[k] - mean_r1) ** 2 for k in range(n))) ** 0.5
            std2 = (sum((r2[k] - mean_r2) ** 2 for k in range(n))) ** 0.5
            if std1 > 0 and std2 > 0:
                correlations.append(cov / (std1 * std2))
        reliability = sum(correlations) / len(correlations) if correlations else 0.5
        # Clamp to [0.1, 1.0] to avoid zero-weight judges
        judge_reliability[j1] = max(0.1, min(1.0, reliability))
        judge_stats[j1]["reliability"] = round(judge_reliability[j1], 4)

    # -- Step 3: Recompute per-pair agreement and weighted consensus --
    for i, r in enumerate(results):
        raw_scores = []
        z_pair = []
        z_weights = []
        for j, a in r.get("per_judge", {}).items():
            s = a.get("similarity_score")
            if s is not None:
                raw_scores.append(s)
                if j in z_scores and i in z_scores[j]:
                    z_pair.append(z_scores[j][i])
                    z_weights.append(judge_reliability.get(j, 0.5))

        if len(raw_scores) < 2:
            continue

        # 3-bin agreement (on raw scores for interpretability)
        bins = [_bin3(s) for s in raw_scores]
        from collections import Counter as _C
        bin_counts = _C(bins)
        _, majority_count = bin_counts.most_common(1)[0]
        majority_frac = majority_count / len(bins)

        if majority_frac >= 0.80:
            r["agreement_level"] = "high"
        elif majority_frac >= 0.60:
            r["agreement_level"] = "medium"
        elif majority_frac >= 0.50:
            r["agreement_level"] = "low"
        else:
            r["agreement_level"] = "disagreement"

        # Reliability-weighted z-score consensus (MACE-style)
        if z_pair and z_weights:
            w_total = sum(z_weights)
            z_consensus = sum(z * w for z, w in zip(z_pair, z_weights)) / w_total if w_total > 0 else sum(z_pair) / len(z_pair)
            r.setdefault("consensus", {})
            r["consensus"]["z_score"] = round(z_consensus, 4)

    return results, judge_stats


def _finalize(
    results: list[dict],
    game: str,
    path: Path,
    strategy: str = "random",
    meta_judge_resolved: int = 0,
    usage: UsageTracker | None = None,
) -> None:
    """Write final output JSON with summary stats."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Recompute agreement with 3-bin scheme + z-normalization
    results, judge_stats = _recompute_agreement(results)

    agreements = {}
    for r in results:
        level = r["agreement_level"]
        agreements[level] = agreements.get(level, 0) + 1

    consensus_scores = [r["consensus"]["similarity_score"] for r in results if r.get("consensus", {}).get("similarity_score") is not None]
    z_scores_all = [r["consensus"]["z_score"] for r in results if r.get("consensus", {}).get("z_score") is not None]
    alphas = [r["iaa_metrics"]["krippendorff_alpha"] for r in results if r.get("iaa_metrics")]

    prompt_versions = set()
    model_ids = set()
    for r in results:
        for judge_data in r.get("per_judge", {}).values():
            if judge_data.get("prompt_version"):
                prompt_versions.add(judge_data["prompt_version"])
            if judge_data.get("model_name"):
                model_ids.add(judge_data["model_name"])

    output = {
        "version": "multi_judge_v5",
        "game": game,
        "generated_at": datetime.now().isoformat(),
        "num_pairs": len(results),
        "strategy": strategy,
        "provenance": {
            "prompt_versions": sorted(prompt_versions),
            "models": sorted(model_ids),
        },
        "summary": {
            "agreement_distribution": agreements,
            "mean_alpha_raw": sum(alphas) / len(alphas) if alphas else 0,
            "mean_consensus_score": sum(consensus_scores) / len(consensus_scores) if consensus_scores else 0,
            "mean_z_consensus": sum(z_scores_all) / len(z_scores_all) if z_scores_all else 0,
            "meta_judge_resolved": meta_judge_resolved,
            "judge_calibration": judge_stats,
        },
        "labels": results,
    }
    if usage:
        output["usage"] = usage.to_dict()

    with open(path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _save_disagreement_manifest(disagreements: list[tuple[dict, object]], path: Path) -> None:
    """Save disagreement pairs for active learning."""
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "disagreement_manifest_v1",
        "generated_at": datetime.now().isoformat(),
        "num_pairs": len(disagreements),
        "pairs": [
            {
                "card1": entry["card1"],
                "card2": entry["card2"],
                "alpha": entry["iaa_metrics"].get("krippendorff_alpha", 0),
                "score_std": entry["iaa_metrics"].get("score_std", 0),
                "scores": {k: v["similarity_score"] for k, v in entry["per_judge"].items()},
            }
            for entry, _ in disagreements
        ],
    }
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run multi-judge annotation batch with smart selection and meta-judge resolution"
    )
    parser.add_argument("--game", default="yugioh", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--edgelist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--num-pairs", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=10, help="Max pairs in parallel")
    parser.add_argument(
        "--strategy", choices=["random", "smart", "focused", "curriculum", "hub"], default="random",
        help="Pair selection strategy: random, smart (Lift+embedding), focused (high-weight), curriculum (progressive difficulty), hub (multi-pair per card for large pools)",
    )
    parser.add_argument(
        "--resolve", action="store_true",
        help="Enable agentic meta-judge resolution for disagreements",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from checkpoint (skip already-completed pairs)",
    )
    parser.add_argument(
        "--finalize", action="store_true",
        help="Finalize from checkpoint (no new annotations, just write final JSON from checkpoint data)",
    )
    parser.add_argument(
        "--prior-annotations", type=Path, default=None,
        help="Prior annotation file for active learning re-annotation of disagreements",
    )
    parser.add_argument(
        "--format", type=str, default=None,
        help="Game format for ban list filtering (e.g., 'modern', 'commander', 'tcg'). "
             "Filters out pairs where either card is banned in the given format.",
    )
    parser.add_argument(
        "--banlist", type=Path, default=None,
        help="Path to ban list JSON (from scrape_banlists.py). "
             "Auto-detected from data/banlists/{game}_banlists.json if not specified.",
    )
    parser.add_argument(
        "--card-attrs", type=Path, default=None,
        help="CSV of card attributes (name,oracle_text,type_line,...) for dynamic context injection",
    )
    args = parser.parse_args()

    # --finalize: just convert checkpoint -> final JSON, no new annotations
    if args.finalize:
        results = _load_checkpoint(args.output)
        if not results:
            print(f"No checkpoint found for {args.output}", file=sys.stderr)
            return 1
        _finalize(results, args.game, args.output, args.strategy)
        print(f"Finalized {len(results)} pairs from checkpoint -> {args.output}")
        cp = _checkpoint_path(args.output)
        if cp.exists():
            cp.unlink()
            print(f"Cleaned up: {cp}")
        return 0

    if not args.edgelist.exists():
        print(f"Error: edgelist not found: {args.edgelist}", file=sys.stderr)
        return 1

    # Watchdog: pydantic-ai + httpx leave zombie connections that prevent
    # asyncio.run() from completing. All results are checkpointed incrementally,
    # so force-exit is safe. SIGALRM fires even when the event loop is stuck.
    def _alarm_handler(signum, frame):
        print("\n[watchdog] SIGALRM fired -- force-exiting (all data checkpointed)", flush=True)
        # Finalize from checkpoint before exiting
        try:
            results = _load_checkpoint(args.output)
            if results:
                _finalize(results, args.game, args.output, args.strategy)
                print(f"[watchdog] Finalized {len(results)} pairs from checkpoint", flush=True)
        except Exception as e:
            print(f"[watchdog] Finalize failed: {e}", flush=True)
        os._exit(0)

    signal.signal(signal.SIGALRM, _alarm_handler)
    # Budget: 75s per batch of concurrent pairs + 60s buffer for startup/finalization
    alarm_budget = int(75 * max(args.num_pairs / args.concurrency, 1) + 60)
    signal.alarm(alarm_budget)
    print(f"  Watchdog: SIGALRM in {alarm_budget}s")

    async def _main():
        result = await run_batch(
            game=args.game,
            edgelist_path=args.edgelist,
            output_path=args.output,
            num_pairs=args.num_pairs,
            seed=args.seed,
            concurrency=args.concurrency,
            strategy=args.strategy,
            resolve=args.resolve,
            prior_annotations=args.prior_annotations,
            card_attrs_path=args.card_attrs,
            resume=args.resume,
            format_filter=args.format,
            banlist_path=args.banlist,
        )
        # Cancel watchdog -- we completed normally
        signal.alarm(0)
        print(f"\nResult: {json.dumps(result, indent=2)}")
        os._exit(0)

    asyncio.run(_main())
    return 0


if __name__ == "__main__":
    sys.exit(main())
