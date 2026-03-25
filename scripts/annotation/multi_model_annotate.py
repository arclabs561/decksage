#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.26.0",
#     "python-dotenv>=1.0.0",
#     "requests>=2.28.0",
#     "scikit-learn>=1.3.0",
# ]
# ///
"""
Multi-model annotation pipeline with cascading, calibration, and QC.

Architecture (from research: PoLL, CARE, regression-aware inference):
  1. Pair selection (active learning: uncertainty + diversity)
  2. Tier 1: 2 cheap fast models, 3 samples each, mean per dimension
  3. Confidence gate: escalate uncertain pairs to Tier 2
  4. Tier 2: stronger model for escalated pairs
  5. Quality monitor: sentinel checks, distribution tests
  6. Isotonic calibration from ground truth

Usage:
    # Calibrate from IAA ground truth (run once)
    uv run scripts/annotation/multi_model_annotate.py calibrate --game magic

    # Annotate with cascading pipeline
    uv run scripts/annotation/multi_model_annotate.py annotate --game magic --budget 200

    # QC check on existing annotations
    uv run scripts/annotation/multi_model_annotate.py qc --game magic
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)  # explicit project .env, not parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
DATA_DIR = PROJECT_ROOT / "data"
CALIBRATION_DIR = DATA_DIR / "calibration"

logger = logging.getLogger("multi_model_annotate")

# ---------------------------------------------------------------------------
# Model pool
# ---------------------------------------------------------------------------

TIER1_MODELS = [
    {
        "name": "groq_llama_70b",
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "api_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "cost_per_1k_tok": 0.69,
        "samples": 2,
        "concurrency": 20,
    },
    {
        "name": "cerebras_qwen_235b",
        "provider": "cerebras",
        "model": "qwen-3-235b-a22b-instruct-2507",
        "api_url": "https://api.cerebras.ai/v1",
        "api_key_env": "CEREBRAS_API_KEY",
        "cost_per_1k_tok": 0.20,
        "samples": 2,
        "concurrency": 10,
    },
]

TIER2_MODELS = [
    {
        "name": "groq_qwen3_32b",
        "provider": "groq",
        "model": "qwen/qwen3-32b",
        "api_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "cost_per_1k_tok": 0.44,
        "samples": 1,
        "concurrency": 20,
    },
]

SCORE_DIMS = ["similarity_score", "functional_score", "synergy_score", "meta_relevance"]

# Enriched prompt with calibration anchors (research finding: highest-impact technique)
ANNOTATION_PROMPT = """Rate these {game} cards on similarity (0.0-1.0).

Card A: {card_a_context}

Card B: {card_b_context}

SCORING SCALE (use the FULL range):
- 0.00: Unrelated. Different functions, different archetypes.
- 0.15: Tangential. Same broad category but different targets/timing/cost.
- 0.40: Moderate. Same function AND similar cost, or strong co-occurrence.
- 0.65: Strong similarity. Competitive alternatives, similar efficiency.
- 0.80: Near-substitute. Functionally interchangeable, minor differences.
- 1.00: Functional reprint or strictly-better/worse pair.

CALIBRATION ANCHORS:
- Lightning Bolt vs Shock = 0.70 (same function, different damage)
- Path to Exile vs Swords to Plowshares = 0.80 (near-identical effect)
- Counterspell vs Mana Leak = 0.50 (same function, different late-game)
- Lightning Bolt vs Counterspell = 0.10 (both instants, different functions)
- Sol Ring vs Wrath of God = 0.05 (unrelated)

Think step by step in 1-2 sentences, then provide scores.

Respond ONLY with JSON:
{{"similarity_score": 0.0, "functional_score": 0.0, "synergy_score": 0.0, "meta_relevance": 0.0}}"""


# ---------------------------------------------------------------------------
# API calling
# ---------------------------------------------------------------------------


async def call_model(
    model_cfg: dict,
    card_a: str,
    card_b: str,
    card_a_ctx: str,
    card_b_ctx: str,
    game: str,
    temperature: float = 0.3,
) -> dict | None:
    """Call a single model and return parsed scores."""
    api_key = os.environ.get(model_cfg["api_key_env"], "")
    if not api_key:
        logger.warning(f"No API key for {model_cfg['name']} ({model_cfg['api_key_env']})")
        return None

    prompt = ANNOTATION_PROMPT.format(
        game=game.upper(),
        card_a_context=card_a_ctx,
        card_b_context=card_b_ctx,
    )

    session = requests.Session()
    session.trust_env = False
    try:
        resp = await asyncio.to_thread(
            session.post,
            f"{model_cfg['api_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_cfg["model"],
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a card game expert. Respond with JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": 500,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1].lstrip("json\n")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(content[start:end])
            else:
                return None

        # Extract scores
        scores = {}
        for dim in SCORE_DIMS:
            val = parsed.get(dim)
            if val is not None:
                scores[dim] = float(val)
        scores["_model"] = model_cfg["name"]
        return scores
    except Exception as e:
        logger.debug(f"  {model_cfg['name']} failed for {card_a} vs {card_b}: {e}")
        return None


# ---------------------------------------------------------------------------
# Multi-sample aggregation
# ---------------------------------------------------------------------------


async def tier1_annotate(
    card_a: str,
    card_b: str,
    card_a_ctx: str,
    card_b_ctx: str,
    game: str,
) -> dict:
    """Run Tier 1: multiple cheap models, multiple samples, mean aggregation."""
    all_scores = []

    for model_cfg in TIER1_MODELS:
        api_key = os.environ.get(model_cfg["api_key_env"], "")
        if not api_key:
            continue

        tasks = []
        for _ in range(model_cfg["samples"]):
            tasks.append(
                call_model(model_cfg, card_a, card_b, card_a_ctx, card_b_ctx, game, temperature=0.5)
            )
        results = await asyncio.gather(*tasks)
        for r in results:
            if r is not None:
                all_scores.append(r)

    if not all_scores:
        return {"scores": {}, "confidence": 0, "n_samples": 0, "needs_escalation": True}

    # Mean aggregation per dimension (research: Bayes-optimal for MSE)
    aggregated = {}
    per_dim_std = {}
    for dim in SCORE_DIMS:
        vals = [s[dim] for s in all_scores if dim in s]
        if vals:
            aggregated[dim] = statistics.mean(vals)
            per_dim_std[dim] = statistics.stdev(vals) if len(vals) > 1 else 0
        else:
            aggregated[dim] = 0.0
            per_dim_std[dim] = 1.0

    # Confidence gate (research: self-consistency variance)
    avg_std = statistics.mean(per_dim_std.values()) if per_dim_std else 1.0
    sim_score = aggregated.get("similarity_score", 0.5)
    in_uncertain_zone = 0.25 < sim_score < 0.65  # scores in middle are ambiguous

    needs_escalation = avg_std > 0.12 or in_uncertain_zone
    confidence = max(0, 1.0 - avg_std * 3)

    return {
        "scores": aggregated,
        "per_dim_std": per_dim_std,
        "confidence": confidence,
        "n_samples": len(all_scores),
        "needs_escalation": needs_escalation,
        "model_breakdown": [
            {dim: s.get(dim) for dim in SCORE_DIMS if dim in s} | {"_model": s["_model"]}
            for s in all_scores
        ],
    }


async def tier2_annotate(
    card_a: str,
    card_b: str,
    card_a_ctx: str,
    card_b_ctx: str,
    game: str,
) -> dict | None:
    """Run Tier 2: stronger model, single call."""
    if not TIER2_MODELS:
        return None
    model_cfg = TIER2_MODELS[0]
    return await call_model(
        model_cfg, card_a, card_b, card_a_ctx, card_b_ctx, game, temperature=0.3
    )


# ---------------------------------------------------------------------------
# Cascading pipeline
# ---------------------------------------------------------------------------


def _load_isotonic(game: str):
    """Load isotonic calibration as an interpolation function."""
    cal_path = CALIBRATION_DIR / f"{game}_calibration.json"
    if not cal_path.exists():
        return None
    try:
        with open(cal_path) as f:
            cal = json.load(f)
        from scipy.interpolate import interp1d

        f_cal = interp1d(
            cal["iso_x"],
            cal["iso_y"],
            bounds_error=False,
            fill_value=(cal["iso_y"][0], cal["iso_y"][-1]),
        )
        return f_cal
    except Exception:
        return None


_isotonic_cache: dict = {}


def get_isotonic(game: str):
    """Get cached isotonic calibrator for a game."""
    if game not in _isotonic_cache:
        _isotonic_cache[game] = _load_isotonic(game)
    return _isotonic_cache[game]


async def annotate_pair(
    card_a: str,
    card_b: str,
    card_a_ctx: str,
    card_b_ctx: str,
    game: str,
) -> dict:
    """Full cascading annotation for one pair."""
    t1 = await tier1_annotate(card_a, card_b, card_a_ctx, card_b_ctx, game)

    final_scores = t1["scores"]
    tier_used = "tier1"
    t2_scores = None

    if t1["needs_escalation"] and t1["n_samples"] > 0:
        t2 = await tier2_annotate(card_a, card_b, card_a_ctx, card_b_ctx, game)
        if t2 is not None:
            t2_scores = {dim: t2.get(dim, 0) for dim in SCORE_DIMS}
            # Blend: weight Tier 2 higher (0.6) since it's a stronger model
            for dim in SCORE_DIMS:
                t1_val = t1["scores"].get(dim, 0)
                t2_val = t2_scores.get(dim, 0)
                final_scores[dim] = 0.4 * t1_val + 0.6 * t2_val
            tier_used = "tier1+tier2"

    # Apply isotonic calibration to similarity_score if available
    calibrated = False
    iso = get_isotonic(game)
    if iso is not None and "similarity_score" in final_scores:
        raw_sim = final_scores["similarity_score"]
        try:
            cal_sim = float(np.clip(iso(raw_sim), 0.0, 1.0))
            final_scores["similarity_score_raw"] = raw_sim
            final_scores["similarity_score"] = cal_sim
            calibrated = True
        except Exception:
            pass

    return {
        "query": card_a,
        "candidate": card_b,
        "similarity_score": final_scores.get("similarity_score", 0),
        "functional_score": final_scores.get("functional_score", 0),
        "synergy_score": final_scores.get("synergy_score", 0),
        "meta_relevance": final_scores.get("meta_relevance", 0),
        "confidence": t1["confidence"],
        "n_samples": t1["n_samples"],
        "tier_used": tier_used,
        "needs_escalation": t1["needs_escalation"],
        "model_name": "multi_model_cascade_v1",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "_provenance": {
            "backend": "multi_model_cascade",
            "tier1_models": [m["name"] for m in TIER1_MODELS],
            "tier2_models": [m["name"] for m in TIER2_MODELS] if tier_used == "tier1+tier2" else [],
            "tier1_samples": t1["n_samples"],
            "tier_used": tier_used,
            "confidence": t1["confidence"],
            "per_dim_std": t1.get("per_dim_std", {}),
            "prompt_version": "enriched_cascade_v1",
            "temperature_tier1": 0.5,
            "temperature_tier2": 0.3,
            "game": game,
            "calibrated": calibrated,
            "script": "multi_model_annotate.py",
        },
    }


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def run_calibration(game: str, n_pairs: int = 100):
    """Run calibration against IAA ground truth."""
    # Load IAA data
    iaa_path = DATA_DIR / "annotations" / f"{game}_2000_v4.json"
    if not iaa_path.exists():
        print(f"No IAA data at {iaa_path}")
        return

    with open(iaa_path) as f:
        iaa_data = json.load(f)

    labels = iaa_data.get("labels", [])
    # Filter to high-agreement pairs
    high_agreement = [lab for lab in labels if lab.get("agreement_level") == "high"]
    print(f"High-agreement pairs: {len(high_agreement)} / {len(labels)}")

    # Sample across score range for calibration
    # Sort by consensus similarity score
    for item in high_agreement:
        consensus = item.get("consensus", {})
        item["_consensus_sim"] = float(consensus.get("similarity_score", 0))

    high_agreement.sort(key=lambda x: x["_consensus_sim"])

    # Stratified sample: equal from each quintile
    per_quintile = n_pairs // 5
    calibration_set = []
    for i in range(5):
        start = int(i * len(high_agreement) / 5)
        end = int((i + 1) * len(high_agreement) / 5)
        quintile = high_agreement[start:end]
        calibration_set.extend(quintile[:per_quintile])

    print(f"Calibration set: {len(calibration_set)} pairs (stratified by score)")

    # Load card context
    from annotation_convergence import load_card_context

    card_context = load_card_context(game)

    # Run Tier 1 on calibration set
    print("\nRunning Tier 1 on calibration set...")
    t1_results = []

    async def run_all():
        sem = asyncio.Semaphore(10)

        async def one(label):
            async with sem:
                card_a = label.get("card1", "")
                card_b = label.get("card2", "")
                ctx_a = card_context.get(card_a, card_a)
                ctx_b = card_context.get(card_b, card_b)
                result = await tier1_annotate(card_a, card_b, ctx_a, ctx_b, game)
                result["_ground_truth"] = label["_consensus_sim"]
                result["_card_a"] = card_a
                result["_card_b"] = card_b
                return result

        return await asyncio.gather(*[one(item) for item in calibration_set])

    t1_results = asyncio.run(run_all())
    valid = [r for r in t1_results if r["n_samples"] > 0]
    print(f"Got {len(valid)} valid results")

    # Compute calibration metrics
    predicted = [r["scores"].get("similarity_score", 0) for r in valid]
    truth = [r["_ground_truth"] for r in valid]

    from sklearn.isotonic import IsotonicRegression

    # Fit isotonic regression
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(predicted, truth)

    # Before/after calibration
    pred_arr = np.array(predicted)
    truth_arr = np.array(truth)
    calibrated = iso.predict(pred_arr)

    mae_before = np.mean(np.abs(pred_arr - truth_arr))
    mae_after = np.mean(np.abs(calibrated - truth_arr))
    corr_before = np.corrcoef(pred_arr, truth_arr)[0, 1] if len(pred_arr) > 2 else 0

    print("\nCalibration results:")
    print(f"  MAE before: {mae_before:.4f}")
    print(f"  MAE after:  {mae_after:.4f}")
    print(f"  Correlation: {corr_before:.4f}")

    # Escalation analysis
    escalated = sum(1 for r in valid if r["needs_escalation"])
    print(f"\n  Escalation rate: {escalated}/{len(valid)} ({escalated / len(valid) * 100:.0f}%)")

    # Per-model breakdown
    print("\n  Per-model scores on calibration set:")
    model_scores = {}
    for r in valid:
        for breakdown in r.get("model_breakdown", []):
            model = breakdown.get("_model", "?")
            sim = breakdown.get("similarity_score")
            if sim is not None:
                model_scores.setdefault(model, []).append(sim)

    for model, scores in sorted(model_scores.items()):
        pred = np.array(scores[: len(truth)])
        gt = truth_arr[: len(pred)]
        if len(pred) == len(gt) and len(pred) > 2:
            corr = np.corrcoef(pred, gt)[0, 1]
            mae = np.mean(np.abs(pred - gt))
            print(f"    {model:30s}: corr={corr:.3f} mae={mae:.3f} mean={np.mean(pred):.3f}")

    # Save calibration data
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    cal_path = CALIBRATION_DIR / f"{game}_calibration.json"
    cal_data = {
        "game": game,
        "n_pairs": len(valid),
        "mae_before": float(mae_before),
        "mae_after": float(mae_after),
        "correlation": float(corr_before),
        "escalation_rate": escalated / len(valid) if valid else 0,
        "iso_x": [float(x) for x in iso.X_thresholds_],
        "iso_y": [float(y) for y in iso.y_thresholds_],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    }
    with open(cal_path, "w") as f:
        json.dump(cal_data, f, indent=2)
    print(f"\n  Saved calibration to {cal_path}")


# ---------------------------------------------------------------------------
# Quality control
# ---------------------------------------------------------------------------


def run_sentinel_check(game: str):
    """Run sentinel pairs through Tier 1 and check calibration."""
    sentinel_path = CALIBRATION_DIR / f"{game}_sentinels.json"
    if not sentinel_path.exists():
        print(f"No sentinels at {sentinel_path}. Run calibrate first to generate.")
        return

    with open(sentinel_path) as f:
        sentinels = json.load(f)

    from annotation_convergence import load_card_context

    card_context = load_card_context(game)

    print(f"Running {len(sentinels)} sentinel pairs through Tier 1...")

    async def run_all():
        sem = asyncio.Semaphore(5)

        async def one(s):
            async with sem:
                ctx_a = card_context.get(s["card1"], s["card1"])
                ctx_b = card_context.get(s["card2"], s["card2"])
                result = await tier1_annotate(s["card1"], s["card2"], ctx_a, ctx_b, game)
                return {
                    "card1": s["card1"],
                    "card2": s["card2"],
                    "expected": s["consensus_sim"],
                    "predicted": result["scores"].get("similarity_score", 0),
                    "n_samples": result["n_samples"],
                    "std": result.get("per_dim_std", {}).get("similarity_score", 0),
                }

        return await asyncio.gather(*[one(s) for s in sentinels])

    results = asyncio.run(run_all())

    print("\nSentinel check results:")
    print(f"{'Card A':25s} {'Card B':25s} {'Expected':>8s} {'Got':>8s} {'Error':>8s} {'Std':>6s}")
    print("-" * 80)

    errors = []
    for r in results:
        err = abs(r["predicted"] - r["expected"])
        errors.append(err)
        flag = " FAIL" if err > 0.20 else ""
        print(
            f"{r['card1']:25s} {r['card2']:25s} "
            f"{r['expected']:8.3f} {r['predicted']:8.3f} {err:8.3f} {r['std']:6.3f}{flag}"
        )

    mae = np.mean(errors)
    max_err = max(errors)
    n_fail = sum(1 for e in errors if e > 0.20)
    print(
        f"\nSentinel MAE: {mae:.3f}, Max error: {max_err:.3f}, Failures (>0.20): {n_fail}/{len(sentinels)}"
    )

    if n_fail > len(sentinels) * 0.3:
        print("WARNING: >30% sentinel failures. Model calibration may have drifted.")
    elif mae > 0.15:
        print("WARNING: Sentinel MAE > 0.15. Consider re-calibrating.")
    else:
        print("PASS: Sentinel check within tolerance.")


def run_qc(game: str):
    """Run quality checks on existing annotations."""
    test_set_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    with open(test_set_path) as f:
        ts = json.load(f)

    # Collect per-model score distributions
    model_scores = {}
    for qdata in ts.get("queries", {}).values():
        for ann in qdata.get("annotations", []):
            model = ann.get("llm_model", ann.get("model_name", "unknown"))
            for dim in SCORE_DIMS:
                val = ann.get(dim)
                if val is not None:
                    model_scores.setdefault(model, {}).setdefault(dim, []).append(float(val))

    print(f"QC Report for {game}")
    print(f"{'=' * 70}")
    for model, dims in sorted(model_scores.items()):
        sim_scores = dims.get("similarity_score", [])
        if len(sim_scores) < 5:
            continue
        mean_s = statistics.mean(sim_scores)
        std_s = statistics.stdev(sim_scores) if len(sim_scores) > 1 else 0
        zero_frac = sum(1 for s in sim_scores if s == 0.0) / len(sim_scores)
        print(f"\n  {model} (n={len(sim_scores)})")
        print(f"    sim: mean={mean_s:.3f} std={std_s:.3f} zero%={zero_frac * 100:.0f}%")

        # Flag issues
        if std_s < 0.05:
            print("    WARNING: score compression (std < 0.05)")
        if zero_frac > 0.5:
            print("    WARNING: >50% zero scores -- prompt issue or model failure")
        if mean_s > 0.6:
            print("    WARNING: high mean score (>0.6) -- possible inflation")
        if mean_s < 0.1:
            print("    WARNING: very low mean score (<0.1) -- possible deflation")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Multi-model annotation pipeline")
    parser.add_argument("command", choices=["calibrate", "annotate", "qc", "sentinel"])
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--budget", type=int, default=100)
    parser.add_argument("--n-cal", type=int, default=100, help="Calibration pairs count")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "calibrate":
        run_calibration(args.game, n_pairs=args.n_cal)
    elif args.command == "qc":
        run_qc(args.game)
    elif args.command == "sentinel":
        run_sentinel_check(args.game)
    elif args.command == "annotate":
        print("Multi-model annotation is wired into annotation_convergence.py.")
        print("Use: uv run scripts/annotation/annotation_convergence.py --model multi")


if __name__ == "__main__":
    raise SystemExit(main())
