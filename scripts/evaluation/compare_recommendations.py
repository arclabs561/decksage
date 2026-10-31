#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.26.0",
#     "pydantic>=2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Pre-registered comparison of a baseline scorer against a candidate scorer.

The claim this exists for is: "learned representations improve deck building".
That claim is only decidable if the retrieval that produced the candidates, the
judged pairs and the depth are held fixed, so this harness holds them fixed and
refuses rather than reporting a number when it cannot.

What is fixed, and how it is checked
------------------------------------
- The test-set file, identified by SHA-256 in the result.
- The judged pairs: each query's relevance comes from the task's own annotation
  field (ADR-0001 via ``ml.contracts.annotations``); a pair annotated for another
  task is not read, and a missing score is never filled from another field.
- The candidate set: retrieved once, from the **baseline** arm, at ``--depth``.
  Both arms then score that same tuple. After each arm runs, the query's
  candidate digest is recomputed from the keys the arm actually scored; the two
  digests must be equal and equal to the retrieved one. The tuple identity passed
  to both arms is also recorded. A mismatch aborts the run.
- K, depth, the relevance threshold, the resample count and the seed.

The only thing that differs between arms is how an already-retrieved candidate is
scored. Arms share one interface (``Scorer.score``): the baseline is one source
with weight 1.0, the candidate is one or more sources with optional weights, so a
fused artefact or a late-fusion scorer plugs in through the command line without
editing this file. A source may be an embedding or a non-learned heuristic
(``--baseline heuristic:b1|b2``, see ``heuristic_scorers.py``); a heuristic is a
single source with weight 1.0 and is subject to the same candidate-set checks.

Verdicts
--------
``candidate_better`` / ``candidate_worse`` when the paired bootstrap 95% CI of the
per-query nDCG@10 delta excludes zero, ``no_difference`` when it does not, and
``insufficient_evidence`` when fewer than ``--min-queries`` paired queries are
usable. Nothing here decides whether either representation is *correct*: a
retrieval that only serves its own training queries wins this harness too.

Usage:
    uv run scripts/evaluation/compare_recommendations.py --game magic \
        --candidate-sources magic_v7_fused,text_e5 --dry-run
    uv run scripts/evaluation/compare_recommendations.py --game magic \
        --candidate-sources magic_v7_fused --output data/results/...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))
# The task -> score field table is shared with the canonical evaluators; see
# scripts/evaluation/task_labels.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from eval_per_mode import DEFAULT_EMBEDDINGS as DEFAULT_BASELINE
from task_labels import TASK_SCORE_FIELD, TASKS


SCHEMA = "decksage.recommendation_comparison/1"
VERDICTS = ("candidate_better", "no_difference", "candidate_worse", "insufficient_evidence")
PRIMARY_METRIC = "ndcg_at_10"
METRICS = (PRIMARY_METRIC, "recall_at_10")
CONFIDENCE = 0.95


class HarnessRefusal(RuntimeError):
    """The comparison cannot be run honestly; no verdict is reported."""


# ---------------------------------------------------------------------------
# Loading the fixed inputs
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_test_set_path(game: str, override: Path | None) -> Path:
    """The canonical test set for a game, or the explicit override."""
    path = override or DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not path.exists():
        raise HarnessRefusal(f"test set not found: {path}")
    return path


def load_canonical_test_set(path: Path) -> tuple[Any, dict[str, Any]]:
    """Load a v2 test set through the annotation contracts.

    Failed, synthetic and fallback judgments are dropped by
    ``curate_evaluation_data`` -- the same ingress rule the canonical evaluator
    uses -- and the count is carried into the result rather than discarded. What
    remains must validate as a ``TestSet``, or the run stops here.
    """
    from pydantic import ValidationError

    from ml.contracts.annotations import TestSet, curate_evaluation_data

    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise HarnessRefusal(f"{path.name} is not valid JSON: {exc}") from exc
    curated, excluded = curate_evaluation_data(raw)
    try:
        test_set = TestSet.model_validate(curated)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ()))
        raise HarnessRefusal(
            f"{path.name} breaks the annotation contract at {location}: {first.get('msg')}"
        ) from exc
    if not test_set.queries:
        raise HarnessRefusal(f"{path.name} contains no queries")
    info = {
        "path": str(path),
        "sha256": sha256_file(path),
        "version": test_set.version,
        "game": test_set.game,
        "num_queries": len(test_set.queries),
        "num_declared": test_set.num_queries,
        "excluded_records": excluded,
    }
    return test_set, info


def screen(path: Path, allow: bool, metadata_dir: Path | None) -> dict[str, Any]:
    """Screen labels with the shared gate and refuse when it blocks."""
    from ml.evaluation.label_gate import gate_or_refuse

    try:
        result = gate_or_refuse(path, allow=allow, metadata_dir=metadata_dir)
    except ValueError as exc:
        raise HarnessRefusal(str(exc)) from exc
    return gate_details(result)


def gate_details(result: Any) -> dict[str, Any]:
    if result.skipped:
        status = "not_applied"
    elif result.blocking:
        # Only reachable through --allow-contradictions: the gate refused and the
        # caller overrode it, and the result has to say so.
        status = "overridden"
    else:
        status = "passed"
    return {
        "status": status,
        "summary": result.summary(),
        "examined": result.examined,
        "counts": result.counts(),
        "blocking": len(result.blocking),
        "skipped": result.skipped,
    }


def resolve_embedding_path(spec: str) -> Path:
    """Resolve an embedding name or path to exactly one artefact."""
    given = Path(spec)
    if given.suffix in (".wv", ".npz") and given.exists():
        return given
    base = DATA_DIR / "embeddings" / spec
    candidates = [Path(f"{base}.npz"), Path(f"{base}.wv")]
    found = [path for path in candidates if path.exists()]
    if not found:
        raise HarnessRefusal(
            f"no embedding artefact for {spec!r}; tried "
            + ", ".join(str(path) for path in candidates)
        )
    if len(found) > 1:
        raise HarnessRefusal(
            f"{spec!r} is ambiguous ({', '.join(p.name for p in found)}); pass the full path"
        )
    return found[0]


def load_vectors(path: Path) -> Any:
    """Load a portable artifact (``.npz``) or a legacy vector artifact (``.wv``)."""
    if path.suffix == ".npz":
        from ml.similarity.named_vectors import NamedVectors

        return NamedVectors.load(path)
    try:
        from gensim.models import KeyedVectors
    except ImportError as exc:  # pragma: no cover - depends on the env extra
        raise HarnessRefusal(
            f"gensim is required to read {path.name}; install the 'embeddings' extra"
        ) from exc
    return KeyedVectors.load(str(path))


@dataclass(frozen=True)
class SourceIndex:
    """One embedding source, normalized once, cosine only."""

    name: str
    path: Path
    keys: tuple[str, ...]
    positions: Mapping[str, int]
    normed: np.ndarray

    @classmethod
    def build(cls, name: str, path: Path, vectors: Any) -> SourceIndex:
        keys = tuple(getattr(vectors, "index_to_key", ()))
        normed = np.asarray(vectors.get_normed_vectors())
        if normed.dtype.kind != "f":
            normed = normed.astype(np.float32)
        if not keys or normed.ndim != 2 or normed.shape[0] != len(keys):
            raise HarnessRefusal(f"{name} does not expose usable normalized vectors")
        if not np.isfinite(normed).all():
            raise HarnessRefusal(f"{name} exposes non-finite vectors")
        normed = normed.copy()
        normed.flags.writeable = False
        return cls(
            name=name,
            path=path,
            keys=keys,
            positions={key: index for index, key in enumerate(keys)},
            normed=normed,
        )

    @property
    def dim(self) -> int:
        return int(self.normed.shape[1])

    def __contains__(self, key: str) -> bool:
        return key in self.positions

    def cosines(self, query: str, candidates: Sequence[str]) -> np.ndarray:
        """Cosine between the query and each candidate, in candidate order."""
        if query not in self.positions:
            raise HarnessRefusal(f"{query!r} is not in source {self.name!r}")
        missing = [candidate for candidate in candidates if candidate not in self.positions]
        if missing:
            raise HarnessRefusal(
                f"source {self.name!r} lacks candidates {missing[:3]}"
                f"{'' if len(missing) <= 3 else f' (+{len(missing) - 3} more)'}"
            )
        rows = np.fromiter(
            (self.positions[candidate] for candidate in candidates),
            dtype=np.int64,
            count=len(candidates),
        )
        query_vector = self.normed[self.positions[query]]
        return (self.normed[rows] @ query_vector).astype(np.float64, copy=False)


@dataclass(frozen=True)
class Scorer:
    """Both arms are this type; only sources and weights differ."""

    arm: str
    sources: tuple[SourceIndex, ...]
    weights: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.sources:
            raise HarnessRefusal(f"arm {self.arm!r} has no sources")
        if len(self.sources) != len(self.weights):
            raise HarnessRefusal(f"arm {self.arm!r} needs one weight per source")
        if any(weight <= 0 for weight in self.weights):
            raise HarnessRefusal(f"arm {self.arm!r} weights must all be positive")

    @property
    def total_weight(self) -> float:
        return float(sum(self.weights))

    def describe(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "sources": [source.name for source in self.sources],
            "paths": [str(source.path) for source in self.sources],
            "weights": list(self.weights),
            "dim": [source.dim for source in self.sources],
            "vocabulary": [len(source.keys) for source in self.sources],
        }

    def score(self, query: str, candidates: Sequence[str]) -> dict[str, float]:
        """Score exactly ``candidates``, in the order given."""
        if not candidates:
            return {}
        accumulated = np.zeros(len(candidates), dtype=np.float64)
        for weight, source in zip(self.weights, self.sources, strict=True):
            accumulated += weight * source.cosines(query, candidates)
        normalized = accumulated / self.total_weight
        return {candidate: float(value) for candidate, value in zip(candidates, normalized)}


def build_arm(
    arm: str,
    specs: Sequence[str],
    weights: Sequence[float] | None,
    *,
    game: str | None = None,
    metadata: Path | None = None,
    heuristic_vocabulary: str | None = None,
    tag_data: Path | None = None,
    tag_cards: Path | None = None,
    reprint_cards: Path | None = None,
) -> Scorer:
    """One arm: an embedding source, or a non-learned heuristic source.

    A heuristic is a single source with weight 1.0 and gets the same treatment as
    an embedding everywhere else -- retrieval, scoring and the fixed-candidate-set
    assertion are unchanged. It must not be mixed with embeddings in one arm,
    because its scores are cosine-like but not on the same scale.
    """
    from heuristic_scorers import HeuristicError, build_heuristic, is_heuristic_spec

    heuristic_specs = [spec for spec in specs if is_heuristic_spec(spec)]
    if heuristic_specs:
        if len(specs) != 1 or weights:
            raise HarnessRefusal(
                f"arm {arm!r} names a heuristic ({heuristic_specs[0]!r}); a heuristic arm "
                "takes exactly one source and no weights"
            )
        if game is None:
            raise HarnessRefusal(f"arm {arm!r} needs a game to resolve heuristic metadata")
        allowed = None
        if heuristic_vocabulary:
            allowed = tuple(
                getattr(
                    load_vectors(resolve_embedding_path(heuristic_vocabulary)), "index_to_key", ()
                )
            )
            if not allowed:
                raise HarnessRefusal(
                    f"--heuristic-vocabulary {heuristic_vocabulary!r} exposes no keys"
                )
        try:
            source = build_heuristic(
                heuristic_specs[0],
                game,
                metadata,
                allowed,
                tag_data=tag_data,
                tag_cards=tag_cards or reprint_cards,
            )
        except HeuristicError as exc:
            raise HarnessRefusal(str(exc)) from exc
        return Scorer(arm=arm, sources=(source,), weights=(1.0,))
    paths = [resolve_embedding_path(spec) for spec in specs]
    indexes = [
        SourceIndex.build(spec, path, load_vectors(path))
        for spec, path in zip(specs, paths, strict=True)
    ]
    dims = {index.dim for index in indexes}
    if len(dims) != 1:
        raise HarnessRefusal(
            f"arm {arm!r} mixes embedding dimensions {sorted(dims)}; "
            "a mismatch is a refusal, not a silent degrade"
        )
    resolved = tuple(weights) if weights else tuple(1.0 for _ in specs)
    return Scorer(arm=arm, sources=tuple(indexes), weights=resolved)


# ---------------------------------------------------------------------------
# Judged pairs and the fixed candidate set
# ---------------------------------------------------------------------------


def judged_pairs(test_set: Any, task: str) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    """Per-query judged relevance for one task, from that task's own field.

    A pair carrying another task is not read (ADR-0001). A pair with no ``task``
    is legacy and is read through the historical task -> field mapping, exactly
    as ``eval_per_mode.py`` does.
    """
    field = TASK_SCORE_FIELD[task]
    judged: dict[str, dict[str, float]] = {}
    counters: dict[str, Any] = {
        "score_field": field.value,
        "legacy_pairs": 0,
        "other_task_pairs": 0,
        "missing_field_pairs": 0,
    }
    for query, entry in test_set.queries.items():
        relevance: dict[str, float] = {}
        for annotation in entry.annotations:
            if annotation.task is not None and str(annotation.task) != task:
                counters["other_task_pairs"] += 1
                continue
            score = annotation.score_for(task)
            if score is None:
                counters["missing_field_pairs"] += 1
                continue
            relevance[annotation.candidate] = float(score)
            if annotation.task is None:
                counters["legacy_pairs"] += 1
        judged[query] = relevance
    return judged, counters


def retrieve(scorer: Scorer, query: str, depth: int) -> tuple[str, ...]:
    """The candidate set: baseline cosine over the whole vocabulary."""
    source = scorer.sources[0]
    scores = source.cosines(query, source.keys)
    scores[source.positions[query]] = -np.inf
    order = np.argsort(-scores, kind="stable")[:depth]
    return tuple(source.keys[index] for index in order if np.isfinite(scores[index]))


def candidates_digest(candidates: Sequence[str]) -> str:
    payload = "\n".join(candidates).encode()
    return hashlib.sha256(payload).hexdigest()


def relevance_digest(relevance: Mapping[str, float]) -> str:
    payload = "\n".join(f"{name}={value:.6f}" for name, value in sorted(relevance.items()))
    return hashlib.sha256(payload.encode()).hexdigest()


def rank(candidates: Sequence[str], scores: Mapping[str, float]) -> list[str]:
    """Deterministic ordering: score descending, then candidate name."""
    return sorted(candidates, key=lambda candidate: (-scores[candidate], candidate))


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def dcg(relevances: Sequence[float], k: int) -> float:
    truncated = np.asarray(list(relevances)[:k], dtype=np.float64)
    if truncated.size == 0:
        return 0.0
    discounts = np.log2(np.arange(2, truncated.size + 2))
    return float(np.sum(truncated / discounts))


def ndcg_at_k(ranked: Sequence[str], relevance: Mapping[str, float], k: int) -> float:
    """Standard nDCG@k: an unjudged retrieved card counts as irrelevant."""
    ideal = dcg(sorted(relevance.values(), reverse=True), k)
    if ideal == 0.0:
        return 0.0
    return dcg([relevance.get(card, 0.0) for card in ranked[:k]], k) / ideal


def recall_at_k(
    ranked: Sequence[str],
    relevance: Mapping[str, float],
    candidates: Sequence[str],
    k: int,
    threshold: float,
) -> float:
    """Recall@k over judged candidates inside the fixed candidate set.

    The denominator is ``min(k, |relevant judged candidates|)`` so a query with
    two judged relevant cards can still reach 1.0. Unjudged cards are not
    negatives here; they are simply not in the judged set.
    """
    relevant = {card for card in candidates if relevance.get(card, 0.0) >= threshold}
    if not relevant:
        return 0.0
    denominator = min(k, len(relevant))
    return len(set(ranked[:k]) & relevant) / denominator


# ---------------------------------------------------------------------------
# Fixed-set assertion
# ---------------------------------------------------------------------------


def assert_fixed_candidate_sets(observations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Prove the arms saw one candidate set per query.

    Each observation records, per arm, the digest of the candidates the arm
    actually scored, whether the keys matched the retrieved list, and the number
    of candidates. Raising here is the point: a silently different candidate set
    turns the comparison into two unrelated measurements.
    """
    checks = {
        "one retrieved candidate list per query": True,
        "both arms scored the same list object": True,
        "candidate digests equal across arms": True,
        "arm keys match the retrieved candidates in order": True,
        "candidate counts equal across arms": True,
        "query excluded from its own candidate set": True,
        "judged pairs identical across arms": True,
    }
    combined = hashlib.sha256()
    for observation in observations:
        arms = observation["arms"]
        if len({item["list_object"] for item in arms.values()}) != 1:
            checks["both arms scored the same list object"] = False
        if len({item["digest"] for item in arms.values()}) != 1:
            checks["candidate digests equal across arms"] = False
        if any(item["digest"] != observation["retrieved_digest"] for item in arms.values()):
            checks["candidate digests equal across arms"] = False
        if any(not item["keys_match"] for item in arms.values()):
            checks["arm keys match the retrieved candidates in order"] = False
        if len({item["count"] for item in arms.values()}) != 1:
            checks["candidate counts equal across arms"] = False
        if observation["query"] in observation["candidates"]:
            checks["query excluded from its own candidate set"] = False
        if len({item["relevance_digest"] for item in arms.values()}) != 1:
            checks["judged pairs identical across arms"] = False
        combined.update(observation["retrieved_digest"].encode())
    record = {
        "identical": all(checks.values()),
        "queries_checked": len(observations),
        "combined_candidate_set_sha256": combined.hexdigest(),
        "checks": [
            {"check": name, "result": "pass" if ok else "FAIL"} for name, ok in checks.items()
        ],
    }
    if not record["identical"]:
        failed = [name for name, ok in checks.items() if not ok]
        raise HarnessRefusal(f"candidate sets are not fixed between arms: {failed}")
    return record


def evaluate_query(
    baseline: Scorer,
    candidate: Scorer,
    query: str,
    candidates: tuple[str, ...],
    relevance: Mapping[str, float],
    k: int,
    threshold: float,
) -> dict[str, Any]:
    """Score one query with both arms over the same candidates."""
    observations: dict[str, dict[str, Any]] = {}
    per_arm: dict[str, dict[str, float]] = {}
    ranked: dict[str, list[str]] = {}
    for scorer in (baseline, candidate):
        scores = scorer.score(query, candidates)
        keys = tuple(scores)
        observations[scorer.arm] = {
            "digest": candidates_digest(keys),
            "keys_match": keys == candidates,
            "count": len(keys),
            "list_object": id(candidates),
            "relevance_digest": relevance_digest(relevance),
        }
        per_arm[scorer.arm] = scores
        ranked[scorer.arm] = rank(candidates, scores)
    assertion_input = {
        "query": query,
        "candidates": candidates,
        "retrieved_digest": candidates_digest(candidates),
        "arms": observations,
    }
    metrics = {
        arm: {
            "ndcg_at_10": ndcg_at_k(ranked[arm], relevance, k),
            "recall_at_10": recall_at_k(ranked[arm], relevance, candidates, k, threshold),
        }
        for arm in per_arm
    }
    return {
        "query": query,
        "candidate_count": len(candidates),
        "candidate_set_sha256": candidates_digest(candidates),
        "judged_candidates": len(relevance),
        "arms": metrics,
        "delta": {
            metric: metrics[candidate.arm][metric] - metrics[baseline.arm][metric]
            for metric in METRICS
        },
        "assertion": assertion_input,
    }


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def paired_bootstrap(
    deltas: Sequence[float], resamples: int, seed: int, confidence: float = CONFIDENCE
) -> dict[str, Any]:
    """Percentile bootstrap over queries, resampling paired deltas together."""
    values = np.asarray(deltas, dtype=np.float64)
    if values.size == 0:
        raise HarnessRefusal("no paired deltas to resample")
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, values.size, size=(resamples, values.size))
    means = values[draws].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    low, high = np.percentile(means, [100 * alpha, 100 * (1 - alpha)])
    return {
        "mean_delta": float(values.mean()),
        "ci_low": float(low),
        "ci_high": float(high),
        "confidence": confidence,
        "resamples": resamples,
        "seed": seed,
        "excludes_zero": bool(low > 0 or high < 0),
        "direction": "candidate_better" if low > 0 else ("candidate_worse" if high < 0 else "none"),
    }


def decide_verdict(
    usable_queries: int, min_queries: int, interval: Mapping[str, Any]
) -> tuple[str, str]:
    """The pre-registered decision rule, applied once."""
    if usable_queries < min_queries:
        return (
            "insufficient_evidence",
            f"{usable_queries} usable queries is below the pre-registered floor of "
            f"{min_queries}; no verdict is reported",
        )
    if interval["ci_low"] > 0:
        return (
            "candidate_better",
            f"paired 95% CI for the {PRIMARY_METRIC} delta is "
            f"[{interval['ci_low']:+.4f}, {interval['ci_high']:+.4f}], above zero",
        )
    if interval["ci_high"] < 0:
        return (
            "candidate_worse",
            f"paired 95% CI for the {PRIMARY_METRIC} delta is "
            f"[{interval['ci_low']:+.4f}, {interval['ci_high']:+.4f}], below zero",
        )
    return (
        "no_difference",
        f"paired 95% CI for the {PRIMARY_METRIC} delta is "
        f"[{interval['ci_low']:+.4f}, {interval['ci_high']:+.4f}], which contains zero",
    )


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def parse_weights(raw: str | None, count: int) -> tuple[float, ...] | None:
    if raw is None or not raw.strip():
        return None
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) != count:
        raise HarnessRefusal(f"--candidate-weights needs {count} values, got {len(parts)}")
    try:
        weights = tuple(float(part) for part in parts)
    except ValueError as exc:
        raise HarnessRefusal(f"--candidate-weights is not numeric: {raw!r}") from exc
    return weights


def parse_sources(raw: str) -> tuple[str, ...]:
    specs = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not specs:
        raise HarnessRefusal("--candidate-sources needs at least one source")
    return specs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a baseline and a candidate scorer on one fixed candidate set "
            "and one fixed set of judged pairs."
        )
    )
    parser.add_argument("--game", required=True, help="game key, e.g. magic")
    parser.add_argument("--test-set", type=Path, default=None, help="override the canonical path")
    parser.add_argument("--task", default="substitute", choices=[str(task) for task in TASKS])
    parser.add_argument(
        "--depth", type=int, default=50, help="retrieval depth, shared by both arms"
    )
    parser.add_argument("--k", type=int, default=10, help="cutoff for nDCG@k and recall@k")
    parser.add_argument(
        "--relevance-threshold",
        type=float,
        default=0.5,
        help="graded relevance at or above this counts as relevant for recall",
    )
    parser.add_argument("--min-queries", type=int, default=30, help="refuse a verdict below this")
    parser.add_argument("--bootstrap-resamples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument(
        "--baseline",
        default=None,
        help=(
            "baseline embedding name or path (default: the game's deployed "
            "embedding); 'heuristic:b1' or 'heuristic:b2' names a non-learned "
            "baseline from scripts/evaluation/heuristic_scorers.py"
        ),
    )
    parser.add_argument(
        "--candidate-sources",
        required=True,
        help="comma-separated embedding sources for the candidate arm",
    )
    parser.add_argument(
        "--candidate-weights",
        default=None,
        help="comma-separated weights, one per candidate source (default: equal)",
    )
    parser.add_argument(
        "--metadata-dir", type=Path, default=None, help="card metadata for the gate"
    )
    parser.add_argument(
        "--heuristic-metadata",
        type=Path,
        default=None,
        help=(
            "enriched attribute table for a heuristic arm "
            "(default: data/processed/card_attributes_<game>_enriched.csv)"
        ),
    )
    parser.add_argument(
        "--heuristic-vocabulary",
        default=None,
        help=(
            "embedding name or path whose keys define a heuristic arm's vocabulary; "
            "intersects the heuristic's cards with the embedding's keys so the "
            "heuristic can be measured as a retriever"
        ),
    )
    parser.add_argument(
        "--tag-data",
        type=Path,
        default=None,
        help=(
            "Scryfall Oracle Tags JSONL(.gz) for the tag:jaccard heuristic "
            "(default: data-local/label-anchor-20261030/oracle-tags.jsonl.gz)"
        ),
    )
    parser.add_argument(
        "--tag-cards",
        type=Path,
        default=None,
        help="Scryfall oracle-cards.json used to map card names to oracle ids",
    )
    parser.add_argument(
        "--reprint-cards",
        type=Path,
        default=None,
        help="Scryfall oracle-cards.json for the reprint:exact heuristic",
    )
    parser.add_argument(
        "--allow-contradictions",
        action="store_true",
        help="record an explicit override and score labels the gate blocks",
    )
    parser.add_argument(
        "--allow-unapplied-gate",
        action="store_true",
        help="continue when the gate could not be applied (metadata or tool missing)",
    )
    parser.add_argument(
        "--exclude-pairs",
        type=Path,
        default=None,
        help=(
            "JSON list of [query, candidate] pairs to drop from relevance "
            "before scoring. Use for pairs whose label is definitionally "
            "impossible (e.g. identical reprints scored 0)."
        ),
    )
    parser.add_argument(
        "--allow-sparse-labels",
        action="store_true",
        help=(
            "score even when the median judged pool is below k. nDCG counts "
            "unjudged candidates as 0, so a sparse pool biases the comparison "
            "against any arm that moves away from the annotated neighbourhood."
        ),
    )
    parser.add_argument(
        "--judged-only",
        action="store_true",
        help=(
            "restrict both arms to candidates that carry a label. nDCG counts "
            "an unjudged candidate as 0, so an arm that promotes one records a "
            "loss by construction; this removes that bias and reports the "
            "judged pool size per query."
        ),
    )
    parser.add_argument("--output", type=Path, default=None, help="result JSON path")
    parser.add_argument(
        "--dry-run", action="store_true", help="resolve and print the plan without scoring"
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> tuple[str, ...]:
    if args.depth < 1:
        parser.error("--depth must be at least 1")
    if args.k < 1:
        parser.error("--k must be at least 1")
    if not 0.0 < args.relevance_threshold <= 1.0:
        parser.error("--relevance-threshold must be in (0, 1]")
    if args.min_queries < 1:
        parser.error("--min-queries must be at least 1")
    if args.bootstrap_resamples < 1:
        parser.error("--bootstrap-resamples must be at least 1")
    sources = parse_sources(args.candidate_sources)
    parse_weights(args.candidate_weights, len(sources))
    return sources


def resolve_inputs(args: argparse.Namespace) -> dict[str, Any]:
    """Everything that must be fixed before a single query is scored."""
    test_set_path = resolve_test_set_path(args.game, args.test_set)
    gate = screen(test_set_path, args.allow_contradictions, args.metadata_dir)
    if gate["status"] == "not_applied" and not args.allow_unapplied_gate:
        raise HarnessRefusal(
            f"label gate could not be applied to {test_set_path.name}: {gate['summary']}; "
            "pass --allow-unapplied-gate to record that explicitly"
        )
    test_set, test_set_info = load_canonical_test_set(test_set_path)
    sources = parse_sources(args.candidate_sources)
    weights = parse_weights(args.candidate_weights, len(sources))
    baseline_spec = args.baseline or DEFAULT_BASELINE.get(args.game)
    if not baseline_spec:
        raise HarnessRefusal(f"no default baseline embedding for {args.game!r}; pass --baseline")
    baseline = build_arm(
        "baseline",
        (baseline_spec,),
        None,
        game=args.game,
        metadata=args.heuristic_metadata,
        heuristic_vocabulary=args.heuristic_vocabulary,
        tag_data=args.tag_data,
        tag_cards=args.tag_cards,
        reprint_cards=args.reprint_cards,
    )
    candidate = build_arm(
        "candidate",
        sources,
        weights,
        game=args.game,
        metadata=args.heuristic_metadata,
        heuristic_vocabulary=args.heuristic_vocabulary,
        tag_data=args.tag_data,
        tag_cards=args.tag_cards,
        reprint_cards=args.reprint_cards,
    )
    judged, label_counters = judged_pairs(test_set, args.task)
    return {
        "test_set_path": test_set_path,
        "test_set": test_set,
        "test_set_info": test_set_info,
        "gate": gate,
        "baseline": baseline,
        "candidate": candidate,
        "judged": judged,
        "label_counters": label_counters,
    }


def usability(
    judged: Mapping[str, dict[str, float]],
    baseline: Scorer,
    candidate: Scorer,
    threshold: float,
) -> tuple[list[str], list[dict[str, str]]]:
    """Queries scored by both arms, and why the rest are excluded.

    Exclusions are decided from vocabulary and judged pairs, before retrieval, so
    the query list does not depend on which arm scored better.
    """
    usable: list[str] = []
    excluded: list[dict[str, str]] = []
    required = list(baseline.sources) + list(candidate.sources)
    for query, relevance in judged.items():
        reason = None
        if any(query not in source for source in required):
            lacking = sorted({source.name for source in required if query not in source})
            reason = f"query missing from {', '.join(lacking)}"
        elif not relevance:
            reason = "no judged pairs for this task"
        elif not any(value >= threshold for value in relevance.values()):
            reason = f"no judged candidate reaches relevance {threshold:g}"
        if reason is None:
            usable.append(query)
        else:
            excluded.append({"query": query, "reason": reason})
    return usable, excluded


def reason_bucket(reason: str) -> str:
    """Group exclusions by cause, without embedding names in the key."""
    for prefix in ("query missing from", "candidate missing from"):
        if reason.startswith(prefix):
            return f"{prefix} a required embedding"
    return reason


def reason_counts(excluded: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts: Counter[str] = Counter(reason_bucket(item["reason"]) for item in excluded)
    return dict(counts.most_common())


def arm_scale(scorer: Scorer) -> str:
    """How to describe an arm's score space in the plan printout."""
    source = scorer.sources[0]
    if getattr(source, "dim", 0) == 0:
        return f"heuristic, {len(source.keys)} cards"
    return f"dim {source.dim}"


def plan_lines(
    resolved: Mapping[str, Any],
    args: argparse.Namespace,
    usable: list[str],
    excluded: Sequence[Mapping[str, str]],
) -> list[str]:
    info = resolved["test_set_info"]
    baseline = resolved["baseline"]
    candidate = resolved["candidate"]
    lines = [
        f"pre-registered comparison: {args.game} / {args.task}",
        f"  test set    {info['path']}",
        f"              sha256={info['sha256']} queries={info['num_queries']} "
        f"excluded_records={info['excluded_records']}",
        f"  gate        {resolved['gate']['status']}: {resolved['gate']['summary']}",
        f"  baseline    {' + '.join(f'{s.name}*{w:g}' for s, w in zip(baseline.sources, baseline.weights, strict=True))}"
        f" ({arm_scale(baseline)})",
        f"  candidate   {' + '.join(f'{s.name}*{w:g}' for s, w in zip(candidate.sources, candidate.weights, strict=True))}"
        f" ({arm_scale(candidate)})",
        f"  retrieval   depth {args.depth} from the baseline, shared by both arms",
        f"  metrics     nDCG@{args.k} and recall@{args.k}, relevant at >= {args.relevance_threshold:g}",
        f"  stats       paired bootstrap {args.bootstrap_resamples} resamples, seed {args.seed}",
        f"  labels      {resolved['label_counters']}",
        f"  usable queries {len(usable)} of {len(resolved['judged'])} (floor {args.min_queries})",
    ]
    if excluded:
        rendered = "; ".join(
            f"{count} {reason}" for reason, count in reason_counts(excluded).items()
        )
        lines.append(f"  excluded    {rendered}")
    if len(usable) < args.min_queries:
        lines.append(
            f"  verdict     would be insufficient_evidence: only {len(usable)} usable "
            f"queries, below the floor of {args.min_queries}"
        )
    return lines


def run(args: argparse.Namespace, argv: Sequence[str]) -> int:
    resolved = resolve_inputs(args)
    if args.exclude_pairs:
        dropped = 0
        for entry in json.loads(args.exclude_pairs.read_text(encoding="utf-8")):
            query, candidate = (
                entry if isinstance(entry, (list, tuple)) else (entry["query"], entry["candidate"])
            )
            if recovered := resolved["judged"].get(query):
                if candidate in recovered:
                    recovered.pop(candidate)
                    dropped += 1
        print(f"  excluded pairs {dropped} from {args.exclude_pairs}")
    usable, excluded = usability(
        resolved["judged"], resolved["baseline"], resolved["candidate"], args.relevance_threshold
    )
    print("\n".join(plan_lines(resolved, args, usable, excluded)))

    if args.dry_run:
        print("  dry run: nothing scored, no result written")
        print(f"  rerun without --dry-run to score {len(usable)} queries")
        return 0

    baseline = resolved["baseline"]
    candidate = resolved["candidate"]
    judged = resolved["judged"]
    per_query: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = list(excluded)
    started = time.time()
    for query in usable:
        candidates = retrieve(baseline, query, args.depth)
        if args.judged_only:
            candidates = tuple(card for card in candidates if card in judged[query])
            if len(candidates) < 2:
                skipped.append(
                    {"query": query, "reason": "fewer than 2 judged candidates in the pool"}
                )
                continue
        if not candidates:
            skipped.append({"query": query, "reason": "empty candidate set"})
            continue
        uncovered = sorted(
            {
                source.name
                for arm in (baseline, candidate)
                for source in arm.sources
                for item in (*candidates, query)
                if item not in source
            }
        )
        if uncovered:
            skipped.append(
                {"query": query, "reason": f"candidate missing from {', '.join(uncovered)}"}
            )
            continue
        record = evaluate_query(
            baseline,
            candidate,
            query,
            candidates,
            judged[query],
            args.k,
            args.relevance_threshold,
        )
        observations.append(record.pop("assertion"))
        record["judged_in_pool"] = sum(1 for card in candidates if card in judged[query])
        per_query.append(record)

    pool_sizes = [record["judged_in_pool"] for record in per_query]
    coverage = {
        "median_judged_in_pool": float(np.median(pool_sizes)) if pool_sizes else 0.0,
        "min_judged_in_pool": int(min(pool_sizes)) if pool_sizes else 0,
    }
    threshold = max(args.k, args.depth // 2)
    coverage["required_judged_in_pool"] = threshold
    if (
        pool_sizes
        and coverage["median_judged_in_pool"] < threshold
        and not args.judged_only
        and not args.allow_sparse_labels
    ):
        raise HarnessRefusal(
            f"median judged pool {coverage['median_judged_in_pool']:.0f} of "
            f"{args.depth} candidates (need {threshold}): nDCG counts every "
            "unjudged candidate as 0, so an arm that moves away from the "
            "annotated neighbourhood loses by construction. Rerun with "
            "--judged-only, or pass --allow-sparse-labels to record the biased "
            "comparison explicitly."
        )
    assertion = assert_fixed_candidate_sets(observations)
    print(
        f"  candidate set fixed: PASS — {assertion['queries_checked']} queries, one "
        f"retrieved list each, arms scored the same tuples"
    )

    means = {
        arm: {
            metric: float(np.mean([record["arms"][arm][metric] for record in per_query]))
            for metric in METRICS
        }
        for arm in ("baseline", "candidate")
    }
    intervals = {
        metric: paired_bootstrap(
            [record["delta"][metric] for record in per_query],
            args.bootstrap_resamples,
            args.seed,
        )
        for metric in METRICS
    }
    verdict, verdict_reason = decide_verdict(
        len(per_query), args.min_queries, intervals[PRIMARY_METRIC]
    )
    for line in (
        f"  mean nDCG@{args.k}   baseline {means['baseline']['ndcg_at_10']:.4f}  "
        f"candidate {means['candidate']['ndcg_at_10']:.4f}  "
        f"delta {intervals['ndcg_at_10']['mean_delta']:+.4f}",
        f"  mean recall@{args.k} baseline {means['baseline']['recall_at_10']:.4f}  "
        f"candidate {means['candidate']['recall_at_10']:.4f}  "
        f"delta {intervals['recall_at_10']['mean_delta']:+.4f}",
        f"  nDCG@{args.k} delta 95% CI "
        f"[{intervals['ndcg_at_10']['ci_low']:+.4f}, {intervals['ndcg_at_10']['ci_high']:+.4f}]",
        f"  verdict: {verdict} — {verdict_reason}",
    ):
        print(line)

    result = {
        "schema": SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "command_line": command_line(argv),
        "game": args.game,
        "task": args.task,
        "dry_run": False,
        "config": {
            "depth": args.depth,
            "k": args.k,
            "relevance_threshold": args.relevance_threshold,
            "min_queries": args.min_queries,
            "bootstrap_resamples": args.bootstrap_resamples,
            "seed": args.seed,
            "allow_contradictions": args.allow_contradictions,
            "primary_metric": PRIMARY_METRIC,
            "metrics": list(METRICS),
        },
        "test_set": resolved["test_set_info"],
        "gate": resolved["gate"],
        "labels": resolved["label_counters"],
        "arms": {"baseline": baseline.describe(), "candidate": candidate.describe()},
        "candidate_set_assertion": assertion,
        "queries_usable": len(per_query),
        "queries_skipped": skipped,
        "skipped_by_reason": reason_counts(skipped),
        "per_query": per_query,
        "coverage": coverage,
        "summary": {
            "mean": means,
            "mean_delta": {metric: intervals[metric]["mean_delta"] for metric in METRICS},
            "elapsed_seconds": round(time.time() - started, 2),
        },
        "bootstrap": intervals,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
    }
    output = args.output or default_output_path(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"  result written to {output}")
    return 0


def command_line(argv: Sequence[str]) -> str:
    """The exact invocation, script path included, as it should be re-run."""
    try:
        script = Path(__file__).resolve().relative_to(PROJECT_ROOT)
    except ValueError:  # pragma: no cover - the script lives in the repo
        script = Path(__file__)
    return " ".join(shlex.quote(str(part)) for part in ("uv", "run", script, *argv))


def default_output_path(args: argparse.Namespace) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return DATA_DIR / "results" / f"compare_recommendations_{args.game}_{args.task}_{stamp}.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    validate_args(parser, args)
    resolved_argv = list(argv) if argv is not None else sys.argv[1:]
    try:
        return run(args, resolved_argv)
    except HarnessRefusal as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
