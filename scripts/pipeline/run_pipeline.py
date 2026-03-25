#!/usr/bin/env python3
"""
Unified DeckSage pipeline: diagnostics -> build -> train -> eval.

Orchestrates the full pipeline with mandatory sanity checks at each stage.
Replaces ad-hoc manual invocation of individual scripts.

Stages:
  1. DIAGNOSE  -- dataset_diagnostics.py (catches duplication, imbalance, gaps)
  2. PREFLIGHT -- preflight_check.py (catches invisible edge sources)
  3. BUILD     -- build_unified_graph.py (graph construction)
  4. TRAIN     -- train_all_embeddings.py (PecanPy + fusion)
  5. SPECTRAL  -- spectral propagation post-processing (deterministic improvement)
  6. EVAL      -- eval_per_mode.py (canonical nDCG evaluation)

Usage:
    # Full pipeline for one game
    uv run python scripts/pipeline/run_pipeline.py --game magic

    # Skip build (reuse existing graph)
    uv run python scripts/pipeline/run_pipeline.py --game magic --skip-build

    # Eval only (no training)
    uv run python scripts/pipeline/run_pipeline.py --game magic --eval-only

    # All games
    uv run python scripts/pipeline/run_pipeline.py --all-games

    # Dry run
    uv run python scripts/pipeline/run_pipeline.py --game magic --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PYTHON = str(PROJECT_ROOT / ".venv/bin/python")

GAME_ATTRS = {
    "magic": "data/processed/card_attributes_enriched.csv",
    "pokemon": "data/processed/card_attributes_pokemon.csv",
    "yugioh": "data/processed/card_attributes_yugioh.csv",
}


def run_cmd(cmd: list[str], label: str, dry_run: bool = False) -> int:
    """Run a command and return exit code."""
    cmd_str = " ".join(str(c) for c in cmd)
    if dry_run:
        print(f"  [DRY RUN] {cmd_str}")
        return 0
    print(f"  $ {cmd_str}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f"  FAILED ({label}) exit={result.returncode} ({elapsed:.0f}s)")
    else:
        print(f"  OK ({elapsed:.0f}s)")
    return result.returncode


def stage_diagnose(game: str, dry_run: bool) -> bool:
    """Stage 1: Dataset diagnostics. Returns True if clean."""
    print(f"\n[1/6] DIAGNOSE: dataset sanity checks")
    ret = run_cmd(
        [PYTHON, "scripts/evaluation/dataset_diagnostics.py", "--game", game],
        "diagnostics", dry_run,
    )
    if ret != 0 and not dry_run:
        print("  WARNING: diagnostics reported issues. Review output above.")
    return True  # diagnostics are advisory, not blocking


def stage_preflight(game: str, dry_run: bool) -> bool:
    """Stage 2: Preflight checks. Returns True if passed."""
    print(f"\n[2/6] PREFLIGHT: edge source quality gates")
    ret = run_cmd(
        [PYTHON, "scripts/training/preflight_check.py", "--game", game],
        "preflight", dry_run,
    )
    if ret != 0 and not dry_run:
        print("  WARNING: preflight checks found issues.")
    return True  # preflight is advisory


def stage_build(game: str, dry_run: bool) -> bool:
    """Stage 3: Build unified graph."""
    print(f"\n[3/6] BUILD: unified graph construction")
    ret = run_cmd(
        [PYTHON, "scripts/training/build_unified_graph.py", "--game", game],
        "build", dry_run,
    )
    return ret == 0


def stage_train(game: str, dry_run: bool, skip_build: bool = False) -> str | None:
    """Stage 4: Train embeddings. Returns path to best embedding or None."""
    print(f"\n[4/6] TRAIN: PecanPy + attribute fusion")
    args = [PYTHON, "scripts/training/train_all_embeddings.py", "--game", game]
    if skip_build:
        args.append("--skip-build")
    ret = run_cmd(args, "train", dry_run)
    if ret != 0:
        return None
    # The pipeline produces {game}_pecanpy_merged_fused.wv
    return f"data/embeddings/{game}_pecanpy_merged_fused.wv"


def stage_spectral(game: str, input_emb: str, edg_path: str, dry_run: bool) -> str | None:
    """Stage 5: Spectral propagation post-processing."""
    from gensim.models import KeyedVectors
    from scipy import sparse

    output_path = input_emb.replace("_fused.wv", "_spectral.wv")
    print(f"\n[5/6] SPECTRAL: propagation (mu=0.3, 10 steps)")

    if dry_run:
        print(f"  [DRY RUN] {input_emb} -> {output_path}")
        return output_path

    if not Path(PROJECT_ROOT / input_emb).exists():
        print(f"  SKIP: {input_emb} not found")
        return None

    kv = KeyedVectors.load(str(PROJECT_ROOT / input_emb))
    vocab = list(kv.key_to_index.keys())
    vectors = kv.vectors.copy()
    card_to_idx = {c: i for i, c in enumerate(vocab)}

    # Build adjacency from edgelist
    edg_full = PROJECT_ROOT / edg_path
    if not edg_full.exists():
        # Try the v7 enriched edgelist as fallback
        edg_full = PROJECT_ROOT / f"data/embeddings/{game}_v7_enriched_merged.edg"
    if not edg_full.exists():
        print(f"  SKIP: no edgelist found for spectral propagation")
        return None

    edges = []
    with open(edg_full) as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                c1, c2, w = parts[0], parts[1], float(parts[2])
                if c1 in card_to_idx and c2 in card_to_idx:
                    i, j = card_to_idx[c1], card_to_idx[c2]
                    edges.append((i, j, w))
                    edges.append((j, i, w))

    N = len(vocab)
    A = sparse.csr_matrix(
        ([e[2] for e in edges], ([e[0] for e in edges], [e[1] for e in edges])),
        shape=(N, N),
    )
    degrees = np.array(A.sum(axis=1)).flatten()
    degrees[degrees == 0] = 1
    D_inv_sqrt = sparse.diags(1.0 / np.sqrt(degrees))
    L_norm = D_inv_sqrt @ A @ D_inv_sqrt

    H = vectors.copy()
    H_orig = vectors.copy()
    mu = 0.3
    for _ in range(10):
        H = (1 - mu) * (L_norm @ H) + mu * H_orig

    norms = np.linalg.norm(H, axis=1, keepdims=True)
    norms[norms == 0] = 1
    H = (H / norms).astype(np.float32)

    out = KeyedVectors(vectors.shape[1])
    out.add_vectors(vocab, H)
    out_full = str(PROJECT_ROOT / output_path)
    out.save(out_full)
    print(f"  Saved {output_path} ({len(vocab)} cards)")
    return output_path


def stage_eval(game: str, embedding_names: list[str], dry_run: bool) -> None:
    """Stage 6: Canonical evaluation."""
    print(f"\n[6/6] EVAL: canonical per-mode nDCG")

    # Always run diagnostics before eval
    if not dry_run:
        print("  Pre-eval diagnostics check...")
        subprocess.run(
            [PYTHON, "scripts/evaluation/dataset_diagnostics.py", "--game", game],
            cwd=str(PROJECT_ROOT), capture_output=True,
        )

    for emb_name in embedding_names:
        # Strip path prefix and .wv suffix for eval_per_mode
        name = emb_name.replace("data/embeddings/", "").replace(".wv", "")
        if dry_run:
            print(f"  [DRY RUN] eval {name}")
            continue

        result = subprocess.run(
            [PYTHON, "scripts/evaluation/eval_per_mode.py",
             "--game", game, "--embedding", name, "--json"],
            cwd=str(PROJECT_ROOT), capture_output=True,
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                r = data[0]
                sub = r["mode_substitute"]["ndcg_at_k"]
                syn = r["mode_synergy"]["ndcg_at_k"]
                overall = r["overall_ndcg"]["ndcg_at_k"]
                hit10 = r.get("hit_at_k", {}).get("10", {}).get("rate", "?")
                mrr = r.get("mrr_relevant", {}).get("mrr", "?")
                ann_density = r.get("annotation_density", {}).get("mean_annotated_per_query", "?")
                print(f"  {name}: sub={sub:.4f} syn={syn:.4f} overall={overall:.4f} "
                      f"Hit@10={hit10} MRR={mrr} ann/q={ann_density}")
            except (json.JSONDecodeError, KeyError, IndexError):
                print(f"  {name}: eval parse error")
        else:
            print(f"  {name}: eval failed (exit {result.returncode})")


def run_game(game: str, args: argparse.Namespace) -> None:
    """Run the full pipeline for one game."""
    print(f"\n{'=' * 60}")
    print(f"  PIPELINE: {game.upper()}")
    print(f"{'=' * 60}")

    t0 = time.time()

    if args.eval_only:
        # Just evaluate existing embeddings
        embs = []
        emb_dir = PROJECT_ROOT / "data" / "embeddings"
        # Find latest fused and spectral embeddings
        for pattern in [f"{game}_*_spectral*.wv", f"{game}_*_fused.wv", f"{game}_v7_fused.wv"]:
            for p in sorted(emb_dir.glob(pattern)):
                name = p.stem
                if name not in embs:
                    embs.append(name)
        if not embs:
            embs = [f"{game}_v7_fused"]
        stage_eval(game, embs[:5], args.dry_run)
    else:
        # Full pipeline
        stage_diagnose(game, args.dry_run)
        stage_preflight(game, args.dry_run)

        if not args.skip_build:
            if not stage_build(game, args.dry_run):
                print("  BUILD FAILED. Aborting.")
                return

        emb_path = stage_train(game, args.dry_run, skip_build=True)
        if not emb_path and not args.dry_run:
            print("  TRAIN FAILED. Evaluating existing embeddings.")
            emb_path = f"data/embeddings/{game}_v7_fused.wv"

        # Spectral post-processing
        edg_path = f"data/graphs/{game}_merged_all.edg"
        spectral_path = None
        if emb_path:
            spectral_path = stage_spectral(game, emb_path, edg_path, args.dry_run)

        # Evaluate all variants
        eval_embs = []
        if spectral_path:
            eval_embs.append(spectral_path)
        if emb_path:
            eval_embs.append(emb_path)
        # Also compare against deployed
        eval_embs.append(f"data/embeddings/{game}_v7_fused.wv")
        stage_eval(game, eval_embs, args.dry_run)

    elapsed = time.time() - t0
    print(f"\n  Pipeline complete for {game} ({elapsed:.0f}s)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified DeckSage pipeline")
    parser.add_argument("--game", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--skip-build", action="store_true", help="Reuse existing unified graph")
    parser.add_argument("--eval-only", action="store_true", help="Only run evaluation")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.all_games:
        games = ["magic", "pokemon", "yugioh"]
    elif args.game:
        games = [args.game]
    else:
        parser.error("Specify --game or --all-games")
        return 1

    for game in games:
        run_game(game, args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
