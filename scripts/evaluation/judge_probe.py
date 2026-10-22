#!/usr/bin/env python3
"""Stage 0 probes for a scalar similarity judge (docs/JUDGE-CALIBRATION.md).

Three cheap, label-free checks that decide whether a judge's 0-1 numbers are
worth calibrating:

1. ``resolution``   -- score spread, ties, zeros, effective distinct values.
   Score compression is the documented failure mode of scalar judges; low
   spread or one dominant 0.1 bin means fix the prompt before buying labels.
2. ``order-swap``   -- score A,B vs B,A. A symmetric judgment should not move;
   a large asymmetry rate means the judge reads position, not content.
3. ``rubric``       -- the same pairs under two rubric wordings. Keep a variant
   only if its variance drops without losing rank correlation to the anchors.

Every mode is a pure function over ``(query_text, candidate_text, variant) ->
score``, so the whole pipeline runs offline with a deterministic fake scorer.
The real path is one OpenRouter chat completion per scored string pair, with the
key read from ``OPENROUTER_API_KEY`` only (never from ``.env``, never logged).

Usage:
    # Offline: deterministic hash scorer, no network, no key
    uv run scripts/evaluation/judge_probe.py --pairs anchors.jsonl --dry-run

    # Real: OpenRouter flash tier, key resolved by the launcher
    #   (see the "Cheap calibration runs" recipe in docs/JUDGE-CALIBRATION.md)
    uv run scripts/evaluation/judge_probe.py --pairs data/audit/anchors.jsonl
    uv run scripts/evaluation/judge_probe.py --pairs anchors.jsonl --json --limit 50

Anchor file (JSONL, one object per line):
    {"query": "...", "candidate": "...",
     "query_text": "optional full rules text", "candidate_text": "optional",
     "human_score": 0.7}
``query``/``candidate`` are required identifiers; ``*_text`` default to them.
``human_score`` is optional and only used as the rubric-mode anchor guard.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY_ENV = "OPENROUTER_API_KEY"
MODEL_ENV = "OPENROUTER_MODEL"
MAX_OUTPUT_TOKENS = 256

# Thresholds transcribed from docs/JUDGE-CALIBRATION.md (Stage 0, Invariance).
SD_COMPRESSED = 0.05  # sd below this = compressed
TOP_BIN_COMPRESSED = 0.8  # one 0.1 bin holding more than this = compressed
TOP_BIN_CONCENTRATED = 0.6  # one 0.1 bin holding more than this = concentrated
ZERO_DEFLATED = 0.7  # zero share above this = deflated
ASYM_TOLERANCE = 0.01  # score deltas above this count as order-sensitive
ASYM_MAX_RATE = 0.05  # share of pairs allowed to move
ASYM_MAX_MEAN_DELTA = 0.01  # mean |delta| allowed across all pairs
RUBRIC_MIN_RANK_CORR = 0.9  # rank correlation a variant may not lose
RUBRIC_FLAT_SD_DELTA = 0.01  # below this the variance change is not measurable

# Two rubric wordings for the rubric-sensitivity probe. "a" is a bare scalar
# instruction, "b" names the criteria. Deliberately different in wording, not
# in what they ask for, so a rank change is attributable to the wording.
RUBRICS = {
    "a": (
        "Score how similar the two cards are for a deck-building decision. "
        "Answer with one number between 0 and 1, where 0 means unrelated and "
        "1 means interchangeable. Return only the number."
    ),
    "b": (
        "Rate substitutability between the query card and the candidate card on a 0-1 scale. "
        "0.0 = different role and cost; 0.5 = same role but material differences; "
        "1.0 = the candidate could replace the query card without changing the deck. "
        "Judge role first, then mana/energy cost, then card text. Return only the number."
    ),
}
VARIANTS = tuple(RUBRICS)


class ProbeError(RuntimeError):
    """A probe could not run (bad input, missing key, or a failed judge call)."""


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pair:
    """One anchor line: two cards and the optional texts/score to judge them by."""

    query: str
    candidate: str
    query_text: str
    candidate_text: str
    human_score: float | None = None
    line: int = 0


def _optional_float(value: Any, *, what: str, line: int) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProbeError(f"line {line}: {what} must be a number, got {type(value).__name__}")
    return float(value)


def parse_pairs(rows: Sequence[dict], *, start_line: int = 1) -> list[Pair]:
    """Validate anchor objects into ``Pair`` records, with line numbers on error."""
    pairs: list[Pair] = []
    for offset, row in enumerate(rows):
        line = start_line + offset
        if not isinstance(row, dict):
            raise ProbeError(f"line {line}: expected a JSON object, got {type(row).__name__}")
        query = row.get("query")
        candidate = row.get("candidate")
        if not isinstance(query, str) or not query.strip():
            raise ProbeError(f"line {line}: 'query' must be a non-empty string")
        if not isinstance(candidate, str) or not candidate.strip():
            raise ProbeError(f"line {line}: 'candidate' must be a non-empty string")
        query_text = row.get("query_text") or query
        candidate_text = row.get("candidate_text") or candidate
        if not isinstance(query_text, str) or not isinstance(candidate_text, str):
            raise ProbeError(f"line {line}: 'query_text'/'candidate_text' must be strings")
        pairs.append(
            Pair(
                query=query,
                candidate=candidate,
                query_text=query_text,
                candidate_text=candidate_text,
                human_score=_optional_float(row.get("human_score"), what="human_score", line=line),
                line=line,
            )
        )
    return pairs


def load_pairs(path: Path | str, *, limit: int | None = None) -> list[Pair]:
    """Read a JSONL anchor file (``-`` reads stdin). Blank lines are skipped."""
    if str(path) == "-":
        raw_lines = sys.stdin.read().splitlines()
        source = "<stdin>"
    else:
        anchor_path = Path(path)
        if not anchor_path.is_file():
            raise ProbeError(f"anchor file not found: {anchor_path}")
        raw_lines = anchor_path.read_text(encoding="utf-8").splitlines()
        source = str(anchor_path)

    rows: list[dict] = []
    for number, raw in enumerate(raw_lines, start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProbeError(f"{source} line {number}: invalid JSON ({exc.msg})") from exc
        rows.append(row)
        if limit is not None and len(rows) >= limit:
            break
    if not rows:
        raise ProbeError(f"{source}: no anchor pairs found")
    return parse_pairs(rows)


# ---------------------------------------------------------------------------
# Scorers
# ---------------------------------------------------------------------------

# (query_text, candidate_text, variant) -> score in [0, 1]
Scorer = Callable[[str, str, str], float]


def make_fake_scorer(
    *,
    seed: int = 0,
    position_bias: float = 0.0,
    variant_shrink: float = 0.8,
    variant_noise: float = 0.05,
) -> Scorer:
    """Deterministic offline scorer: hash-based, seeded, no network.

    Design (each term is reproducible from ``seed`` and the pair's texts):

    * base score is a uniform hash of the *unordered* pair, so a swap does not
      move it -- the default fake judge is symmetric by construction;
    * ``position_bias`` optionally adds a per-pair term whose sign follows which
      text sits in the query slot, so ``--fake-position-bias 0.1`` simulates a
      position-sensitive judge for the order-swap probe;
    * variant "b" shrinks the score toward 0.5 (``variant_shrink`` reduces the
      sd) and adds a small deterministic perturbation (``variant_noise``), which
      is the shape of a rubric that changes spread without being a monotone
      transform.

    Scores are rounded to 3 decimals to mimic a real judge's precision.
    """

    def unit(*parts: str) -> float:
        digest = hashlib.blake2b("\x1f".join(parts).encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") / float(2**64)

    def scorer(query_text: str, candidate_text: str, variant: str) -> float:
        low, high = sorted((query_text, candidate_text))
        base = unit("base", str(seed), low, high)
        score = base
        if position_bias:
            # Positive when the lexicographically smaller text is in the query
            # slot; the swapped call gets the opposite sign.
            sign = 1.0 if query_text <= candidate_text else -1.0
            score += sign * position_bias * unit("pos", str(seed), low, high)
        if variant == "b":
            score = 0.5 + (score - 0.5) * variant_shrink
            score += variant_noise * (unit("varb", str(seed), low, high) - 0.5) * 2
        elif variant != "a":
            raise ProbeError(f"unknown rubric variant: {variant!r}")
        return round(min(1.0, max(0.0, score)), 3)

    return scorer


_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


class OpenRouterScorer:
    """One chat completion per scored pair, using a flash-tier model."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        rubric: dict[str, str] | None = None,
        timeout: float = 60.0,
        retries: int = 2,
    ) -> None:
        if not api_key:
            raise ProbeError("missing API key")
        self.model = model
        self.rubric = rubric or RUBRICS
        self.retries = max(0, retries)
        # The key stays in the client's headers: not stored, not logged, not written.
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - httpx is a runtime dependency
            raise ProbeError("httpx is required for real scoring (uv sync)") from exc
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Title": "decksage judge probe",
            },
        )

    def messages(self, query_text: str, candidate_text: str, variant: str) -> list[dict]:
        rubric = self.rubric[variant]
        return [
            {
                "role": "system",
                "content": (
                    "You judge card pairs for a deck-building similarity search. "
                    "Reply with a single number and nothing else."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{rubric}\n\n"
                    f"Query card:\n{query_text}\n\n"
                    f"Candidate card:\n{candidate_text}\n\n"
                    "Score:"
                ),
            },
        ]

    def __call__(self, query_text: str, candidate_text: str, variant: str) -> float:
        payload = {
            "model": self.model,
            "messages": self.messages(query_text, candidate_text, variant),
            "temperature": 0.0,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        last_error = ""
        for attempt in range(self.retries + 1):
            try:
                response = self._client.post(OPENROUTER_URL, json=payload)
            except Exception as exc:  # network failure: same surface as a bad reply
                last_error = f"request failed ({type(exc).__name__})"
            else:
                if response.status_code == 200:
                    return parse_score(response.json())
                last_error = f"HTTP {response.status_code}"
                if response.status_code not in {429, 500, 502, 503, 504}:
                    break
            if attempt < self.retries:
                time.sleep(min(2**attempt, 8))
        raise ProbeError(f"judge call failed: {last_error}")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenRouterScorer:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def parse_score(body: dict) -> float:
    """Extract a single 0-1 score from a chat-completion body."""
    try:
        content = body["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ProbeError("judge reply had no choices[0].message.content") from exc
    match = _NUMBER.search(str(content))
    if match is None:
        snippet = str(content).strip().replace("\n", " ")[:80]
        raise ProbeError(f"judge reply contained no number: {snippet!r}")
    value = float(match.group(0))
    if not 0.0 <= value <= 1.0:
        raise ProbeError(f"judge score {value} outside [0, 1]")
    return value


class CountingScorer:
    """Memoizing wrapper: dedupes identical calls and counts the real ones.

    Resolution and rubric variant "a" score the same forward pairs, so without
    the cache the "all" mode would pay for them twice.
    """

    def __init__(self, scorer: Scorer) -> None:
        self._scorer = scorer
        self._cache: dict[tuple[str, str, str], float] = {}
        self.calls = 0

    def __call__(self, query_text: str, candidate_text: str, variant: str) -> float:
        key = (query_text, candidate_text, variant)
        if key in self._cache:
            return self._cache[key]
        self.calls += 1
        score = float(self._scorer(query_text, candidate_text, variant))
        if not 0.0 <= score <= 1.0:
            raise ProbeError(f"scorer returned {score} outside [0, 1]")
        self._cache[key] = score
        return score


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def bin_index(value: float) -> int:
    """0.1-bin index for a 0-1 score (1.0 lands in the top bin)."""
    return min(9, max(0, int(value * 10)))


def effective_distinct(values: Sequence[float]) -> float:
    """exp(entropy) of the exact-value distribution: distinct values, deduped."""
    if not values:
        return 0.0
    total = len(values)
    entropy = -sum((c / total) * math.log(c / total) for c in Counter(values).values())
    return round(math.exp(entropy), 3)


def resolution_verdict(sd: float, top_bin_share: float, zero_share: float) -> str:
    """Judge usability from the distribution, matching the doc's thresholds.

    Order matters: a compressed judge hides behind both low sd and a dominant
    bin, and a deflated one is recognisable only once compression is excluded.
    """
    if sd < SD_COMPRESSED or top_bin_share > TOP_BIN_COMPRESSED:
        return "compressed"
    if zero_share > ZERO_DEFLATED:
        return "deflated"
    if top_bin_share > TOP_BIN_CONCENTRATED:
        return "concentrated"
    return "usable"


def resolution_stats(values: Sequence[float]) -> dict:
    n = len(values)
    if n == 0:
        return {"n": 0, "status": "absent", "verdict": "absent"}
    bins = [0] * 10
    for value in values:
        bins[bin_index(value)] += 1
    counts = Counter(values)
    top_bin_share = max(bins) / n
    zero_share = sum(1 for value in values if value == 0.0) / n
    sd = statistics.pstdev(values) if n > 1 else 0.0
    return {
        "n": n,
        "status": "measured",
        "mean": round(statistics.fmean(values), 4),
        "sd": round(sd, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "distinct": len(counts),
        "effective_distinct": effective_distinct(values),
        "tie_rate": round(1 - len(counts) / n, 4),
        "zero_share": round(zero_share, 4),
        "top_bin_share": round(top_bin_share, 4),
        "top_bin": bins.index(max(bins)),
        "histogram": bins,
        "verdict": resolution_verdict(sd, top_bin_share, zero_share),
    }


def order_swap_verdict(asymmetry_rate: float, mean_abs_delta: float) -> str:
    """Symmetric scores should not move; the doc says asymmetry should be ~0."""
    if asymmetry_rate > ASYM_MAX_RATE or mean_abs_delta > ASYM_MAX_MEAN_DELTA:
        return "position_sensitive"
    return "invariant"


def order_swap_stats(
    forward: Sequence[float], swapped: Sequence[float], *, tolerance: float = ASYM_TOLERANCE
) -> dict:
    n = min(len(forward), len(swapped))
    if n == 0:
        return {"n": 0, "status": "absent", "verdict": "absent"}
    deltas = [b - a for a, b in zip(forward[:n], swapped[:n])]
    abs_deltas = [abs(delta) for delta in deltas]
    moved = sum(1 for delta in abs_deltas if delta > tolerance)
    asymmetry_rate = moved / n
    mean_abs_delta = statistics.fmean(abs_deltas)
    return {
        "n": n,
        "status": "measured",
        "tolerance": tolerance,
        "asymmetry_rate": round(asymmetry_rate, 4),
        "mean_abs_delta": round(mean_abs_delta, 4),
        "max_abs_delta": round(max(abs_deltas), 4),
        "mean_signed_delta": round(statistics.fmean(deltas), 4),
        "verdict": order_swap_verdict(asymmetry_rate, mean_abs_delta),
    }


def average_ranks(values: Sequence[float]) -> list[float]:
    """Ranks with ties averaged, so Spearman works on quantised scores."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = rank
        i = j + 1
    return ranks


def rank_correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    """Spearman rho as Pearson on average ranks; None when undefined."""
    n = min(len(left), len(right))
    if n < 3:
        return None
    x = average_ranks(left[:n])
    y = average_ranks(right[:n])
    mean_x = statistics.fmean(x)
    mean_y = statistics.fmean(y)
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    var_x = sum((a - mean_x) ** 2 for a in x)
    var_y = sum((b - mean_y) ** 2 for b in y)
    if var_x == 0 or var_y == 0:
        return None
    return round(cov / math.sqrt(var_x * var_y), 4)


def rubric_verdict(
    *,
    sd_a: float,
    sd_b: float,
    rank_corr: float | None,
    anchor_delta: float | None,
) -> str:
    """Keep the lower-variance variant only if ranking survives.

    The doc's gate is "variance drops without rank correlation to the anchor set
    dropping". ``anchor_delta`` is the best available anchor signal: the change
    in correlation with human scores when labels exist, otherwise 0.0 because
    the guard falls back to variant-to-variant rank correlation.
    """
    if rank_corr is None:
        return "insufficient"
    if rank_corr < RUBRIC_MIN_RANK_CORR:
        return "rank_unstable"
    if anchor_delta is not None and -anchor_delta > 1 - RUBRIC_MIN_RANK_CORR:
        return "rank_unstable"
    if abs(sd_b - sd_a) < RUBRIC_FLAT_SD_DELTA:
        return "flat"
    return "keep_b" if sd_b < sd_a else "keep_a"


def rubric_stats(
    pairs: Sequence[Pair], values_a: Sequence[float], values_b: Sequence[float]
) -> dict:
    n = min(len(pairs), len(values_a), len(values_b))
    if n == 0:
        return {"n": 0, "status": "absent", "verdict": "absent"}
    a = list(values_a[:n])
    b = list(values_b[:n])
    stats_a = resolution_stats(a)
    stats_b = resolution_stats(b)
    corr = rank_correlation(a, b)

    labelled = [i for i in range(n) if pairs[i].human_score is not None]
    human = [float(pairs[i].human_score) for i in labelled] if labelled else []
    human_corr: dict[str, float | None] = {"a": None, "b": None}
    anchor_delta: float | None = None
    if len(labelled) >= 3:
        human_corr["a"] = rank_correlation([a[i] for i in labelled], human)
        human_corr["b"] = rank_correlation([b[i] for i in labelled], human)
        if human_corr["a"] is not None and human_corr["b"] is not None:
            anchor_delta = round(human_corr["b"] - human_corr["a"], 4)

    sd_a = statistics.pstdev(a) if n > 1 else 0.0
    sd_b = statistics.pstdev(b) if n > 1 else 0.0
    return {
        "n": n,
        "status": "measured",
        "variant_a": stats_a,
        "variant_b": stats_b,
        "sd_delta": round(sd_b - sd_a, 4),
        "sd_ratio": round(sd_b / sd_a, 4) if sd_a else None,
        "variance_change_pct": round((sd_b - sd_a) / sd_a * 100, 1) if sd_a else None,
        "rank_corr": corr,
        "n_labelled": len(labelled),
        "human_rank_corr": human_corr,
        "anchor_guard": "human_labels" if anchor_delta is not None else "variant_correlation",
        "anchor_delta": anchor_delta,
        "verdict": rubric_verdict(sd_a=sd_a, sd_b=sd_b, rank_corr=corr, anchor_delta=anchor_delta),
    }


# ---------------------------------------------------------------------------
# Probe driver
# ---------------------------------------------------------------------------


def _score(
    scorer: Scorer, pairs: Sequence[Pair], variant: str, *, swap: bool = False
) -> list[float]:
    values: list[float] = []
    for pair in pairs:
        if swap:
            values.append(scorer(pair.candidate_text, pair.query_text, variant))
        else:
            values.append(scorer(pair.query_text, pair.candidate_text, variant))
    return values


def run_probe(
    pairs: Sequence[Pair],
    scorer: Scorer,
    *,
    modes: Sequence[str] = ("resolution", "order-swap", "rubric"),
    tolerance: float = ASYM_TOLERANCE,
    seed: int = 0,
    model: str | None = None,
    dry_run: bool = False,
    source: str = "-",
    limit: int | None = None,
    fake_position_bias: float = 0.0,
    metadata: dict | None = None,
) -> dict:
    """Run the requested probes over the pairs and return the JSON-ready report.

    All three probes start from the same forward scores, so they are computed
    once and the cache keeps a mode from paying twice. Each mode reports the
    calls it caused (``calls``) and the report reports the true total
    (``calls_total``).
    """
    counting = CountingScorer(scorer)
    requested = {"resolution", "order-swap", "rubric"} if "all" in modes else set(modes)
    unknown = requested - {"resolution", "order-swap", "rubric"}
    if unknown:
        raise ProbeError(f"unknown mode(s): {', '.join(sorted(unknown))}")
    order = [mode for mode in ("resolution", "order-swap", "rubric") if mode in requested]
    costs = dict.fromkeys(order, 0)

    report: dict[str, Any] = {
        "schema": "judge_probe.v1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "inputs": {
            "pairs": source,
            "n_pairs": len(pairs),
            "limit": limit,
            "modes": sorted(requested),
            "tolerance": tolerance,
            "dry_run": dry_run,
            "seed": seed if dry_run else None,
            "model": model,
            "n_labelled": sum(1 for pair in pairs if pair.human_score is not None),
            "fake_position_bias": fake_position_bias if dry_run else None,
            **(metadata or {}),
        },
        "modes": {},
    }

    forward_a = _score(counting, pairs, "a")
    if order:
        costs[order[0]] += counting.calls

    if "resolution" in requested:
        stats = resolution_stats(forward_a)
        report["modes"]["resolution"] = {**stats, "calls": costs["resolution"]}

    if "order-swap" in requested:
        before = counting.calls
        swapped_a = _score(counting, pairs, "a", swap=True)
        costs["order-swap"] += counting.calls - before
        stats = order_swap_stats(forward_a, swapped_a, tolerance=tolerance)
        report["modes"]["order_swap"] = {**stats, "calls": costs["order-swap"]}

    if "rubric" in requested:
        before = counting.calls
        forward_b = _score(counting, pairs, "b")
        costs["rubric"] += counting.calls - before
        stats = rubric_stats(pairs, forward_a, forward_b)
        report["modes"]["rubric"] = {**stats, "calls": costs["rubric"]}

    report["scorer"] = "dry-run" if dry_run else "openrouter"
    report["calls_total"] = counting.calls
    return report


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _num(value: float | None, spec: str = ".3f") -> str:
    return "-" if value is None else format(value, spec)


def format_table(report: dict) -> str:
    inputs = report["inputs"]
    scorer = report["scorer"]
    if scorer == "dry-run":
        who = f"dry-run(seed={inputs['seed']})"
    else:
        who = f"openrouter:{inputs['model']}"
    lines = [
        f"judge_probe  pairs={inputs['n_pairs']}  labelled={inputs['n_labelled']}  "
        f"scorer={who}  calls={report['calls_total']}",
    ]
    modes = report["modes"]

    if "resolution" in modes:
        st = modes["resolution"]
        lines += [
            "",
            f"resolution   n={st['n']}  calls={st.get('calls', 0)}  verdict={st['verdict']}",
            "  mean   sd     min    max    distinct  eff.distinct  ties  zero  top-bin",
        ]
        if st["n"]:
            lines.append(
                f"  {_num(st['mean'])}  {_num(st['sd'])}  {_num(st['min'])}  {_num(st['max'])}  "
                f"{st['distinct']:>8d}  {_num(st['effective_distinct'], '.2f'):>12}  "
                f"{st['tie_rate']:>4.2f}  {st['zero_share']:>4.2f}  {st['top_bin_share']:>7.2f}"
            )
            bins = st["histogram"]
            lines.append("  bins 0.0-0.9: " + " ".join(str(count) for count in bins))

    if "order_swap" in modes:
        st = modes["order_swap"]
        lines += [
            "",
            f"order-swap   n={st['n']}  calls={st.get('calls', 0)}  "
            f"tol={st.get('tolerance')}  verdict={st['verdict']}",
            "  asymmetry_rate  mean|delta|  max|delta|  mean_signed",
        ]
        if st["n"]:
            lines.append(
                f"  {st['asymmetry_rate']:>14.2f}  {st['mean_abs_delta']:>11.4f}  "
                f"{st['max_abs_delta']:>10.4f}  {st['mean_signed_delta']:>11.4f}"
            )

    if "rubric" in modes:
        st = modes["rubric"]
        lines += [
            "",
            f"rubric       n={st['n']}  calls={st.get('calls', 0)}  "
            f"guard={st['anchor_guard']}  verdict={st['verdict']}",
            "  variant  sd     mean   rank-vs-A  rank-vs-human",
        ]
        if st["n"]:
            corr = _num(st["rank_corr"])
            lines.append(
                f"  A        {_num(st['variant_a']['sd'])}  {_num(st['variant_a']['mean'])}  "
                f"{corr:>9}  {_num(st['human_rank_corr']['a']):>13}"
            )
            lines.append(
                f"  B        {_num(st['variant_b']['sd'])}  {_num(st['variant_b']['mean'])}  "
                f"{_num(st['rank_corr']):>9}  {_num(st['human_rank_corr']['b']):>13}"
            )
            lines.append(
                f"  sd delta {st['sd_delta']:+.4f}"
                + (f"  ({st['variance_change_pct']:+.1f}%)" if st["variance_change_pct"] else "")
                + (
                    f"  anchor delta {st['anchor_delta']:+.4f}"
                    if st["anchor_delta"] is not None
                    else ""
                )
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage 0 judge probes: resolution, order-swap, and rubric sensitivity",
    )
    parser.add_argument("--pairs", required=True, help="JSONL anchor file ('-' for stdin)")
    parser.add_argument(
        "--mode",
        choices=["resolution", "order-swap", "rubric", "all"],
        default="all",
        help="which probe to run (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="use the deterministic hash scorer; no network, no key",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of the table")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of pairs")
    parser.add_argument("--seed", type=int, default=0, help="dry-run scorer seed (default: 0)")
    parser.add_argument(
        "--fake-position-bias",
        type=float,
        default=0.0,
        help="dry-run only: simulate a position-biased judge (0-1 magnitude)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenRouter model (default: ${MODEL_ENV} or {DEFAULT_MODEL})",
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="per-call timeout in seconds")
    parser.add_argument("--retries", type=int, default=2, help="retries on 429/5xx (default: 2)")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=ASYM_TOLERANCE,
        help=f"|delta| above which a swap counts as moved (default: {ASYM_TOLERANCE})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.limit is not None and args.limit < 1:
        print("judge_probe: --limit must be >= 1", file=sys.stderr)
        return 2

    try:
        pairs = load_pairs(args.pairs, limit=args.limit)
    except ProbeError as exc:
        print(f"judge_probe: {exc}", file=sys.stderr)
        return 2

    model: str | None = None
    scorer: Scorer
    real: OpenRouterScorer | None = None
    if args.dry_run:
        scorer = make_fake_scorer(seed=args.seed, position_bias=args.fake_position_bias)
    else:
        model = args.model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL
        api_key = os.environ.get(API_KEY_ENV, "").strip()
        if not api_key:
            print(
                f"judge_probe: {API_KEY_ENV} is not set. Export it for this process "
                f"(see the 'Cheap calibration runs' recipe in docs/JUDGE-CALIBRATION.md), "
                f"or pass --dry-run to use the offline hash scorer.",
                file=sys.stderr,
            )
            return 2
        try:
            real = OpenRouterScorer(
                model=model, api_key=api_key, timeout=args.timeout, retries=args.retries
            )
        except ProbeError as exc:
            print(f"judge_probe: {exc}", file=sys.stderr)
            return 2
        scorer = real

    try:
        report = run_probe(
            pairs,
            scorer,
            modes=(args.mode,),
            tolerance=args.tolerance,
            seed=args.seed,
            model=model,
            dry_run=args.dry_run,
            source=str(args.pairs),
            limit=args.limit,
            fake_position_bias=args.fake_position_bias,
        )
    except ProbeError as exc:
        print(f"judge_probe: {exc}", file=sys.stderr)
        return 1
    finally:
        if real is not None:
            real.close()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
