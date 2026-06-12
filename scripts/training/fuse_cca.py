#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "numpy<2.0.0", "scikit-learn"]
# ///
"""
CCA (Canonical Correlation Analysis) fusion of two embedding streams.

Stream A: structural co-occurrence (PecanPy on graph)
Stream B: functional similarity (Word2Vec on deck lists, ns_exponent=-0.5)

CCA maximizes cross-view correlation over the shared vocabulary, then projects
both views into a shared latent space. For cards in both views, the fused
embedding is the average of the two CCA projections. For cards in only one
view, the single-view CCA projection is used directly.

Usage:
    uv run scripts/training/fuse_cca.py \
        --stream-a data/embeddings/magic_cleaned_v4.wv \
        --stream-b data/embeddings/magic_ns-0.5_128d.wv \
        --output data/embeddings/magic_cca_fused.wv \
        --components 64
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors
from sklearn.cross_decomposition import CCA
from sklearn.preprocessing import normalize


QUALITY_PAIRS = [
    # (card_a, card_b, label, min_threshold)
    ("Lightning Bolt", "Fireball", "co-occurrence", 0.50),
    ("Lightning Bolt", "Chain Lightning", "functional", 0.30),
    ("Sol Ring", "Arcane Signet", "co-occurrence", 0.50),
    ("Swords to Plowshares", "Path to Exile", "functional", 0.30),
    ("Counterspell", "Mana Leak", "functional", 0.20),
    ("Dark Ritual", "Cabal Ritual", "functional", 0.40),
    # Negative control
    ("Lightning Bolt", "Island", "negative", None),
]

NEGATIVE_THRESHOLD = 0.20

RELEVANCE_GRADES = {
    "highly_relevant": 3,
    "relevant": 2,
    "somewhat_relevant": 1,
    "marginally_relevant": 0.5,
    "irrelevant": 0,
}


def evaluate_quality(kv: KeyedVectors, label: str) -> dict[str, float]:
    """Evaluate quality pairs and return {pair_label: similarity}."""
    results = {}
    n_pass = 0
    n_total = 0
    print(f"\n  Quality pairs ({label}):")
    for card_a, card_b, kind, threshold in QUALITY_PAIRS:
        if card_a not in kv or card_b not in kv:
            tag = "MISSING"
            sim = float("nan")
        else:
            sim = float(kv.similarity(card_a, card_b))
            n_total += 1
            if kind == "negative":
                passed = sim < NEGATIVE_THRESHOLD
            elif threshold is not None:
                passed = sim >= threshold
            else:
                passed = True
            tag = "PASS" if passed else "FAIL"
            if passed:
                n_pass += 1
        pair_key = f"{card_a} <-> {card_b}"
        results[pair_key] = sim
        thresh_str = (
            f" (>={threshold:.2f})"
            if threshold
            else f" (<{NEGATIVE_THRESHOLD:.2f})"
            if kind == "negative"
            else ""
        )
        print(f"    {tag:7s} {sim:+.4f}  {card_a} <-> {card_b}{thresh_str}")
    print(f"    Score: {n_pass}/{n_total}")
    return results


def evaluate_ndcg(kv: KeyedVectors, test_set_path: Path, label: str) -> tuple[float, float, int]:
    """Evaluate nDCG@5 and nDCG@10 on annotated test set."""
    if not test_set_path.exists():
        print(f"\n  nDCG ({label}): SKIPPED (no test set)")
        return 0.0, 0.0, 0

    data = json.load(open(test_set_path))
    queries = data.get("queries", data)

    def dcg(scores, k):
        return sum(s / math.log2(i + 2) for i, s in enumerate(scores[:k]))

    def ndcg(rels, k):
        d = dcg(rels, k)
        ideal = dcg(sorted(rels, reverse=True), k)
        return d / ideal if ideal > 0 else 0.0

    scores5, scores10 = [], []
    n_miss = 0
    for q, labels in queries.items():
        if q not in kv:
            n_miss += 1
            continue
        try:
            neighbors = kv.most_similar(q, topn=20)
        except Exception:
            n_miss += 1
            continue
        rels = []
        for card, _ in neighbors:
            grade = 0.0
            for level, w in RELEVANCE_GRADES.items():
                if card in labels.get(level, []):
                    grade = w
                    break
            rels.append(grade)
        scores5.append(ndcg(rels, 5))
        scores10.append(ndcg(rels, 10))

    n = len(scores5)
    m5 = sum(scores5) / n if n else 0
    m10 = sum(scores10) / n if n else 0
    total = n + n_miss
    print(f"  nDCG ({label}): @5={m5:.3f}  @10={m10:.3f}  ({n}/{total} queries)")
    return m5, m10, n


def fuse_cca(
    kv_a: KeyedVectors,
    kv_b: KeyedVectors,
    shared: list[str],
    only_a: list[str],
    only_b: list[str],
    n_components: int,
) -> tuple[list[str], np.ndarray]:
    """Fuse via CCA alignment of shared vocabulary, then project all cards."""
    X_a = np.array([kv_a[k] for k in shared], dtype=np.float64)
    X_b = np.array([kv_b[k] for k in shared], dtype=np.float64)

    # Fit CCA on shared vocab
    n_comp = min(n_components, X_a.shape[1], X_b.shape[1], len(shared))
    print(f"\nFitting CCA: n_components={n_comp} on {len(shared)} shared cards")
    print(f"  Stream A dim={X_a.shape[1]}, Stream B dim={X_b.shape[1]}")

    cca = CCA(n_components=n_comp, max_iter=2000, tol=1e-6)
    X_a_cca, X_b_cca = cca.fit_transform(X_a, X_b)

    # Correlation per component
    corrs = [np.corrcoef(X_a_cca[:, i], X_b_cca[:, i])[0, 1] for i in range(n_comp)]
    print(f"  Canonical correlations (first 10): {[f'{c:.3f}' for c in corrs[:10]]}")
    print(f"  Mean correlation: {np.mean(corrs):.3f}")

    # Fused shared = average of CCA-aligned views
    fused_shared = ((X_a_cca + X_b_cca) / 2).astype(np.float32)

    all_keys = list(shared)
    all_vecs = [fused_shared]

    # Project A-only cards via the learned CCA X-transform
    # CCA.transform(X) computes: (X - _x_mean) / _x_std @ x_weights_
    if only_a:
        X_oa = np.array([kv_a[k] for k in only_a], dtype=np.float64)
        X_oa_cca = cca.transform(X_oa)
        all_keys.extend(only_a)
        all_vecs.append(X_oa_cca.astype(np.float32))
        print(f"  Projected {len(only_a)} A-only cards via CCA X-transform")

    # Project B-only cards via the learned CCA Y-transform
    # CCA.transform(X, y) returns (x_scores, y_scores) but we only have Y.
    # Manual Y-side projection: (Y - _y_mean) / _y_std @ y_rotations_
    if only_b:
        X_ob = np.array([kv_b[k] for k in only_b], dtype=np.float64)
        X_ob_cca = (X_ob - cca._y_mean) / cca._y_std @ cca.y_rotations_
        all_keys.extend(only_b)
        all_vecs.append(X_ob_cca.astype(np.float32))
        print(f"  Projected {len(only_b)} B-only cards via CCA Y-transform")

    all_vecs_arr = np.vstack(all_vecs)
    return all_keys, all_vecs_arr


def run_sweep(
    kv_a: KeyedVectors,
    kv_b: KeyedVectors,
    shared: list[str],
    only_a: list[str],
    only_b: list[str],
    components_list: list[int],
    test_set_path: Path,
    output_dir: Path,
) -> None:
    """Sweep over n_components values and report comparison."""
    print("\n" + "=" * 70)
    print("Component sweep")
    print("=" * 70)

    results = []
    for nc in components_list:
        nc_eff = min(nc, kv_a.vector_size, kv_b.vector_size, len(shared))
        print(f"\n--- n_components={nc_eff} ---")
        keys, vecs = fuse_cca(kv_a, kv_b, shared, only_a, only_b, nc)

        kv = KeyedVectors(vector_size=vecs.shape[1])
        kv.add_vectors(keys, vecs)

        # Quality pairs
        n_pass = 0
        n_total = 0
        for card_a, card_b, kind, threshold in QUALITY_PAIRS:
            if card_a not in kv or card_b not in kv:
                continue
            sim = float(kv.similarity(card_a, card_b))
            n_total += 1
            if kind == "negative":
                if sim < NEGATIVE_THRESHOLD:
                    n_pass += 1
            elif threshold is not None and sim >= threshold:
                n_pass += 1

        # nDCG
        m5, m10, _n_q = evaluate_ndcg(kv, test_set_path, f"CCA-{nc_eff}D")

        # Random baseline
        vecs_norm = normalize(vecs, norm="l2")
        rng = np.random.default_rng(42)
        n_sample = min(5_000, len(keys) * (len(keys) - 1) // 2)
        sims = []
        for _ in range(n_sample):
            i, j = rng.choice(len(keys), 2, replace=False)
            sims.append(np.dot(vecs_norm[i], vecs_norm[j]))
        rand_mean = np.mean(sims)

        results.append(
            {
                "components": nc_eff,
                "quality": f"{n_pass}/{n_total}",
                "ndcg5": m5,
                "ndcg10": m10,
                "rand_mean": rand_mean,
                "vocab": len(keys),
            }
        )

    print("\n" + "=" * 70)
    print(f"{'Dim':>5} {'Quality':>8} {'nDCG@5':>8} {'nDCG@10':>8} {'RandMean':>9} {'Vocab':>7}")
    print("-" * 70)
    for r in results:
        print(
            f"  {r['components']:>3} {r['quality']:>8} "
            f"{r['ndcg5']:>8.3f} {r['ndcg10']:>8.3f} "
            f"{r['rand_mean']:>+9.4f} {r['vocab']:>7}"
        )
    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="CCA fusion of two embedding streams")
    parser.add_argument("--stream-a", type=Path, required=True, help="Structural embedding .wv")
    parser.add_argument("--stream-b", type=Path, required=True, help="Functional embedding .wv")
    parser.add_argument("--output", type=Path, required=True, help="Output .wv file")
    parser.add_argument(
        "--components",
        type=int,
        default=64,
        help="Number of CCA components (default: 64)",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Sweep n_components=[32, 64, 128] and report comparison",
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("data/test_set_annotated_magic.json"),
        help="Annotated test set for nDCG evaluation",
    )
    args = parser.parse_args()

    # Resolve paths relative to project root
    project_root = Path(__file__).resolve().parent.parent.parent
    stream_a = args.stream_a if args.stream_a.is_absolute() else project_root / args.stream_a
    stream_b = args.stream_b if args.stream_b.is_absolute() else project_root / args.stream_b
    output = args.output if args.output.is_absolute() else project_root / args.output
    test_set = args.test_set if args.test_set.is_absolute() else project_root / args.test_set

    # Load streams
    print(f"Loading stream A (structural): {stream_a}")
    kv_a = KeyedVectors.load(str(stream_a))
    print(f"  {len(kv_a)} cards, dim={kv_a.vector_size}")

    print(f"Loading stream B (functional): {stream_b}")
    kv_b = KeyedVectors.load(str(stream_b))
    print(f"  {len(kv_b)} cards, dim={kv_b.vector_size}")

    # Vocab sets (filter Card_XXXX noise)
    numeric_id = re.compile(r"^Card_\d+$")
    vocab_a = {k for k in kv_a.key_to_index if not numeric_id.match(k)}
    vocab_b = {k for k in kv_b.key_to_index if not numeric_id.match(k)}
    shared = sorted(vocab_a & vocab_b)
    only_a = sorted(vocab_a - vocab_b)
    only_b = sorted(vocab_b - vocab_a)

    n_filt = (len(kv_a) - len(vocab_a)) + (len(kv_b) - len(vocab_b))
    if n_filt:
        print(f"  Filtered {n_filt} Card_XXXX IDs")

    overlap_pct = len(shared) / len(vocab_a | vocab_b) * 100
    print(
        f"\nVocab: {len(shared)} shared ({overlap_pct:.1f}%), "
        f"{len(only_a)} A-only, {len(only_b)} B-only, "
        f"{len(vocab_a | vocab_b)} union"
    )

    if len(shared) < 100:
        print("Error: too few shared cards for CCA", file=sys.stderr)
        return 1

    # Sweep mode
    if args.sweep:
        run_sweep(kv_a, kv_b, shared, only_a, only_b, [32, 64, 128], test_set, output.parent)

    # Primary fusion
    print("\n" + "=" * 60)
    print(f"Primary CCA fusion: {args.components} components")
    print("=" * 60)
    all_keys, all_vecs = fuse_cca(kv_a, kv_b, shared, only_a, only_b, args.components)

    # Save
    output.parent.mkdir(parents=True, exist_ok=True)
    kv_out = KeyedVectors(vector_size=all_vecs.shape[1])
    kv_out.add_vectors(all_keys, all_vecs)
    kv_out.save(str(output))
    print(f"\nSaved {len(all_keys)} embeddings (dim={all_vecs.shape[1]}) to {output}")

    # === Evaluation ===
    print("\n" + "=" * 60)
    print(f"Evaluation: CCA fusion ({args.components}D)")
    print("=" * 60)

    # Quality pairs -- all three views
    results_a = evaluate_quality(kv_a, "Stream A (structural)")
    results_b = evaluate_quality(kv_b, "Stream B (functional)")
    results_fused = evaluate_quality(kv_out, "CCA fused")

    # Summary table
    print("\n" + "=" * 70)
    print(f"{'Pair':<45} {'Struct':>7} {'Func':>7} {'CCA':>7}")
    print("-" * 70)
    for pair_key in results_a:
        sa = results_a[pair_key]
        sb = results_b[pair_key]
        sf = results_fused[pair_key]
        sa_s = f"{sa:+.3f}" if not np.isnan(sa) else "   N/A"
        sb_s = f"{sb:+.3f}" if not np.isnan(sb) else "   N/A"
        sf_s = f"{sf:+.3f}" if not np.isnan(sf) else "   N/A"
        print(f"  {pair_key:<43} {sa_s:>7} {sb_s:>7} {sf_s:>7}")
    print("=" * 70)

    # nDCG evaluation
    print("\n" + "=" * 60)
    print("nDCG evaluation")
    print("=" * 60)
    evaluate_ndcg(kv_a, test_set, "Stream A (structural)")
    evaluate_ndcg(kv_b, test_set, "Stream B (functional)")
    evaluate_ndcg(kv_out, test_set, "CCA fused")

    # Random-pair baseline
    combined_norm = normalize(all_vecs, norm="l2")
    rng = np.random.default_rng(42)
    n_sample = min(10_000, len(all_keys) * (len(all_keys) - 1) // 2)
    sims = []
    for _ in range(n_sample):
        i, j = rng.choice(len(all_keys), 2, replace=False)
        sims.append(np.dot(combined_norm[i], combined_norm[j]))
    sims_arr = np.array(sims)
    print(f"\nRandom-pair cosine sim: mean={sims_arr.mean():.4f}, std={sims_arr.std():.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
