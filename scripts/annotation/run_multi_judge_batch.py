#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic-ai", "pydantic", "python-dotenv", "gensim", "numpy"]
# ///
"""
Run multi-judge annotation batch with smart selection and meta-judge resolution.

Pipeline:
1. Select pairs using smart strategies (Lift-weighted, uncertainty, embedding disagreement)
2. Run MultiAnnotatorIAA.annotate_pair_multi() on each pair (parallel)
3. Route high-disagreement pairs through AgenticMetaJudge for multi-round resolution
4. Save results + disagreement manifest for active learning feedback

Usage:
  PYTHONPATH=src uv run scripts/annotation/run_multi_judge_batch.py \
    --game magic --edgelist data/processed/pairs_large.edg \
    --output data/annotations/magic_multi_judge.json \
    --num-pairs 100 --strategy smart

Strategies:
  random   - Stratified random sampling across weight buckets (fast, baseline)
  smart    - Lift-weighted + embedding uncertainty + diversity (recommended)
  focused  - High-Lift pairs only (synergy signal, fewer unrelated)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import threading

from dotenv import load_dotenv

# Load API keys
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from ml.annotation.multi_annotator_iaa import MultiAnnotatorIAA  # noqa: E402


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

    def summary_line(self) -> str:
        with self.lock:
            done = self.completed + self.failed
            elapsed = time.monotonic() - self.t0
            rate = elapsed / max(done, 1)
            remaining = (self.total - done) * rate
            pct = 100 * done / self.total if self.total else 0
            agree = self.agreements.get("high", 0) + self.agreements.get("medium", 0)
            disagree = self.agreements.get("disagreement", 0) + self.agreements.get("low", 0)
            return (
                f"  Progress: {done}/{self.total} ({pct:.0f}%) | "
                f"{rate:.1f}s/pair | ETA {remaining:.0f}s | "
                f"agree={agree} disagree={disagree} fail={self.failed}"
            )

    def final_report(self) -> str:
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
        lines.append(f"{'='*60}")
        return "\n".join(lines)

# Optional: card attribute loading for dynamic context
try:
    from ml.annotation.graph_enricher import load_card_attributes  # noqa: E402
    HAS_GRAPH_ENRICHER = True
except ImportError:
    HAS_GRAPH_ENRICHER = False


def load_edgelist(path: Path) -> list[tuple[str, str, float]]:
    """Load edgelist from tab-separated (.edg) or CSV (.csv) format.

    TSV format: card1<TAB>card2<TAB>weight
    CSV format: NAME_1,NAME_2,...,COUNT,... (auto-detected by header or .csv extension)
    """
    edges = []
    is_csv = path.suffix == ".csv"
    with open(path) as f:
        first_line = f.readline().strip()
        if not first_line:
            return edges

        # Detect CSV by header row containing NAME_1 or comma-separated with known columns
        if is_csv or "NAME_1" in first_line or (
            "," in first_line and "\t" not in first_line and first_line.count(",") >= 2
        ):
            # CSV mode -- find column indices from header
            import csv
            f.seek(0)
            reader = csv.DictReader(f)
            name1_col = "NAME_1" if "NAME_1" in (reader.fieldnames or []) else None
            name2_col = "NAME_2" if "NAME_2" in (reader.fieldnames or []) else None
            count_col = "COUNT" if "COUNT" in (reader.fieldnames or []) else None
            if not name1_col or not name2_col:
                # Fall back: assume first two columns are card names
                f.seek(0)
                next(f)  # skip header
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) >= 2:
                        weight = float(parts[2]) if len(parts) > 2 else 1.0
                        edges.append((parts[0], parts[1], weight))
            else:
                for row in reader:
                    c1, c2 = row[name1_col], row[name2_col]
                    if c1 == c2:
                        continue  # skip self-loops
                    # Skip unresolved passcode IDs (e.g., Card_81439174)
                    if c1.startswith("Card_") or c2.startswith("Card_"):
                        continue
                    weight = float(row[count_col]) if count_col and row.get(count_col) else 1.0
                    edges.append((c1, c2, weight))
        else:
            # TSV mode
            parts = first_line.split("\t")
            if len(parts) >= 2:
                edges.append((parts[0], parts[1], float(parts[2]) if len(parts) > 2 else 1.0))
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                edges.append((parts[0], parts[1], float(parts[2]) if len(parts) > 2 else 1.0))
    return edges


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
        # Score all candidate pairs by model disagreement
        candidate_pool = [(c1, c2) for c1, c2, _ in edges if tuple(sorted([c1, c2])) not in seen]
        rng.shuffle(candidate_pool)
        candidate_pool = candidate_pool[:5000]  # bound computation

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
        # Fallback: medium-weight pairs
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
            (l["card1"], l["card2"])
            for l in prior.get("labels", [])
            if l.get("agreement_level") == "disagreement"
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
        # Auto-discover from data/embeddings/
        embed_dir = Path("data/embeddings")
        if embed_dir.exists():
            paths = sorted(embed_dir.glob("*.wv"))[:4]  # cap at 4 models
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
        # Richer structured output
        "functional_score": ann.functional_score,
        "synergy_score": ann.synergy_score,
        "key_similarities": ann.key_similarities,
        "key_differences": ann.key_differences,
        # Provenance fingerprint
        "model_name": ann.model_name,
        "model_params": ann.model_params,
        "prompt_version": ann.prompt_version,
        "prompt_hash": ann.prompt_hash,
        "timestamp": ann.timestamp,
    }
    return {k: v for k, v in entry.items() if v is not None}


def _result_entry(result, game: str) -> dict:
    """Convert a MultiAnnotatorResult to a serializable dict."""
    return {
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


async def annotate_one_pair(
    iaa: MultiAnnotatorIAA,
    card1: str,
    card2: str,
    game: str,
    idx: int,
    total: int,
    sem: asyncio.Semaphore,
    card_attrs: dict[str, dict] | None = None,
    progress: ProgressTracker | None = None,
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

            result = await iaa.annotate_pair_multi(card1, card2, card_context=card_context)
            entry = _result_entry(result, game)
            elapsed_pair = time.monotonic() - t_start
            alpha = result.iaa_metrics.get("krippendorff_alpha", 0)
            n_judges = len(result.annotations)
            scores = [f"{a.similarity_score:.2f}" for a in result.annotations.values()]

            print(
                f"    [{idx}] {result.agreement_level} "
                f"(alpha={alpha:.2f}, {n_judges} judges, scores=[{','.join(scores)}]) "
                f"{elapsed_pair:.1f}s"
            )
            if progress:
                progress.record(result.agreement_level, list(result.annotations.keys()), elapsed_pair)
                # Print running summary every 10 pairs
                if (progress.completed + progress.failed) % 10 == 0:
                    print(progress.summary_line(), flush=True)

            # Return raw result too for meta-judge routing
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

                # Update entry with resolution info
                entry["meta_judge"] = {
                    "action": action,
                    "rounds": rounds_used,
                    "final_consensus_score": (
                        final_round.consensus_decision.consensus_score
                        if final_round.consensus_decision else None
                    ),
                }

                # If revised annotations available, update per_judge and consensus
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
    """Load card attributes for dynamic context injection.

    Looks for Scryfall-style JSON or CSV card data in data-full or data/processed.
    Returns dict mapping card_name -> {oracle_text, type_line, mana_cost, ...}.
    """
    import csv

    # Try CSV attributes first (lightweight, pre-extracted)
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

    # Try Scryfall JSON (heavier but comprehensive)
    json_candidates = [
        Path(f"src/backend/data-full/games/{game}/scryfall/cards"),
    ]
    for json_dir in json_candidates:
        if json_dir.is_dir():
            attrs = {}
            import zstandard
            for jf in sorted(json_dir.glob("*.json.zst"))[:5]:  # cap files
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
            if attrs:
                print(f"  Loaded {len(attrs):,} card attributes from Scryfall ({json_dir})")
                return attrs

    # Try plain JSON
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
    concurrency: int = 5,
    strategy: str = "random",
    resolve: bool = False,
    prior_annotations: Path | None = None,
    card_attrs_path: Path | None = None,
) -> dict:
    """Run multi-judge annotation batch with smart selection and optional meta-judge resolution."""
    # Load edges
    print(f"Loading edgelist: {edgelist_path}")
    edges = load_edgelist(edgelist_path)
    print(f"  {len(edges):,} edges loaded")

    # Select pairs
    print(f"Selecting {num_pairs} pairs (strategy={strategy})...")
    if strategy == "smart":
        pairs = select_pairs_smart(edges, num_pairs, seed=seed, prior_annotations_path=prior_annotations)
    elif strategy == "focused":
        pairs = select_pairs_focused(edges, num_pairs, seed=seed)
    elif strategy == "curriculum":
        from curriculum_sampler import CurriculumSampler
        # Pre-load card attrs for difficulty classification
        _card_attrs = _load_card_attrs_for_game(game)
        sampler = CurriculumSampler(edges, card_attrs=_card_attrs, seed=seed)
        stats = sampler.stats()
        print(f"  Difficulty distribution: easy={stats['easy_pct']}, medium={stats['medium_pct']}, hard={stats['hard_pct']}")
        classified = sampler.sample(num_pairs, phase="auto")
        pairs = [(p.card1, p.card2) for p in classified]
        # Log difficulty breakdown of selected pairs
        from collections import Counter as _C
        diff_counts = _C(p.difficulty for p in classified)
        print(f"  Selected: easy={diff_counts['easy']}, medium={diff_counts['medium']}, hard={diff_counts['hard']}")
    else:
        pairs = select_pairs_random(edges, num_pairs, seed=seed)
    print(f"  Selected {len(pairs)} pairs")

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

    # Load game knowledge (ban lists, format context, archetypes)
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

    # Phase 1: Parallel annotation
    sem = asyncio.Semaphore(concurrency)
    t0 = time.monotonic()
    progress = ProgressTracker(len(pairs))

    tasks = [
        annotate_one_pair(iaa, c1, c2, game, i, len(pairs), sem, card_attrs=card_attrs, progress=progress)
        for i, (c1, c2) in enumerate(pairs, 1)
    ]
    raw_results = await asyncio.gather(*tasks)

    results = []
    disagreements = []
    for entry, raw_result in raw_results:
        if entry is not None:
            results.append(entry)
            if raw_result is not None:
                disagreements.append((entry, raw_result))

    print(progress.final_report())

    # Phase 2: Meta-judge resolution of disagreements (optional)
    n_disagree = len(disagreements)
    meta_judge_resolved = 0
    if resolve and disagreements:
        print(f"\nPhase 2: Meta-judge resolution for {n_disagree} disagreements...")
        meta_sem = asyncio.Semaphore(max(concurrency // 2, 1))  # lower concurrency for multi-round
        resolved = await resolve_disagreements(disagreements, iaa, meta_sem)
        meta_judge_resolved = len(resolved)
        print(f"  Resolved: {meta_judge_resolved}/{n_disagree}")

    elapsed = time.monotonic() - t0
    print(f"\nTotal: {len(results)} pairs in {elapsed:.0f}s ({elapsed/max(len(results),1):.1f}s/pair)")

    # Save results
    _save(results, game, output_path, strategy=strategy, meta_judge_resolved=meta_judge_resolved)
    print(f"Saved: {output_path}")

    # Save disagreement manifest for active learning
    if disagreements:
        manifest_path = output_path.with_suffix(".disagreements.json")
        _save_disagreement_manifest(disagreements, manifest_path)
        print(f"Disagreement manifest: {manifest_path} ({len(disagreements)} pairs)")

    return {"total": len(results), "elapsed_s": round(elapsed, 1), "disagreements": n_disagree}


def _save(results: list[dict], game: str, path: Path, strategy: str = "random", meta_judge_resolved: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    # Compute summary stats
    agreements = {}
    for r in results:
        level = r["agreement_level"]
        agreements[level] = agreements.get(level, 0) + 1

    consensus_scores = [r["consensus"]["similarity_score"] for r in results if r.get("consensus")]
    alphas = [r["iaa_metrics"]["krippendorff_alpha"] for r in results if r.get("iaa_metrics")]

    # Collect unique prompt versions and model IDs from annotations
    prompt_versions = set()
    model_ids = set()
    for r in results:
        for judge_data in r.get("per_judge", {}).values():
            if judge_data.get("prompt_version"):
                prompt_versions.add(judge_data["prompt_version"])
            if judge_data.get("model_name"):
                model_ids.add(judge_data["model_name"])

    with open(path, "w") as f:
        json.dump({
            "version": "multi_judge_v3",
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
                "mean_alpha": sum(alphas) / len(alphas) if alphas else 0,
                "mean_consensus_score": sum(consensus_scores) / len(consensus_scores) if consensus_scores else 0,
                "meta_judge_resolved": meta_judge_resolved,
            },
            "labels": results,
        }, f, indent=2)


def _save_disagreement_manifest(disagreements: list[tuple[dict, object]], path: Path) -> None:
    """Save disagreement pairs for active learning -- feed back into next batch via --prior-annotations."""
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
    parser.add_argument("--concurrency", type=int, default=5, help="Max pairs in parallel")
    parser.add_argument(
        "--strategy", choices=["random", "smart", "focused", "curriculum"], default="random",
        help="Pair selection strategy: random, smart (Lift+embedding), focused (single archetype), curriculum (progressive difficulty)",
    )
    parser.add_argument(
        "--resolve", action="store_true",
        help="Enable agentic meta-judge resolution for disagreements",
    )
    parser.add_argument(
        "--prior-annotations", type=Path, default=None,
        help="Prior annotation file for active learning re-annotation of disagreements",
    )
    parser.add_argument(
        "--card-attrs", type=Path, default=None,
        help="CSV of card attributes (name,oracle_text,type_line,...) for dynamic context injection",
    )
    args = parser.parse_args()

    if not args.edgelist.exists():
        print(f"Error: edgelist not found: {args.edgelist}", file=sys.stderr)
        return 1

    asyncio.run(run_batch(
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
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
