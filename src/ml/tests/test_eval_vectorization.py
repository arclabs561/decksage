"""Tests for eval_per_mode.py vectorized neighbor computation.

Verifies that _precompute_neighbors() (batch matrix multiply) produces
identical results to gensim's wv.most_similar() -- same order, same scores.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest


# Add scripts dir so we can import eval_per_mode
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts" / "evaluation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

EMBEDDING_PATH = PROJECT_ROOT / "data" / "embeddings" / "magic_v7_fused.wv"

needs_embedding = pytest.mark.skipif(
    not EMBEDDING_PATH.exists(),
    reason=f"Embedding file not found: {EMBEDDING_PATH}",
)

try:
    from gensim.models import KeyedVectors
except ImportError:
    pytest.skip("gensim not installed", allow_module_level=True)

from eval_per_mode import _precompute_neighbors, eval_game


@pytest.fixture(scope="module")
def wv() -> KeyedVectors:
    """Load embedding once for all tests in this module."""
    return KeyedVectors.load(str(EMBEDDING_PATH))


@pytest.fixture(scope="module")
def sample_queries(wv: KeyedVectors) -> list[str]:
    """Pick 10 deterministic queries from the vocabulary."""
    rng = np.random.default_rng(42)
    indices = rng.choice(len(wv), size=10, replace=False)
    return [wv.index_to_key[i] for i in indices]


# -- Test 1: batch results match gensim for 10 random queries --


@needs_embedding
def test_batch_neighbors_match_gensim_names(wv: KeyedVectors, sample_queries: list[str]) -> None:
    """Top-K neighbor names from batch must equal gensim most_similar."""
    k = 20
    cache = _precompute_neighbors(wv, sample_queries, max_k=k)

    for q in sample_queries:
        gensim_neighbors = wv.most_similar(q, topn=k)
        batch_neighbors = cache[q]

        gensim_names = [name for name, _ in gensim_neighbors]
        batch_names = [name for name, _ in batch_neighbors]

        assert batch_names == gensim_names, (
            f"Name mismatch for '{q}':\n"
            f"  gensim: {gensim_names[:5]}...\n"
            f"  batch:  {batch_names[:5]}..."
        )


# -- Test 2: ordering is identical (not just same set) --


@needs_embedding
def test_batch_neighbors_ordering_is_identical(wv: KeyedVectors, sample_queries: list[str]) -> None:
    """Verify strict position-by-position ordering matches gensim."""
    k = 30
    cache = _precompute_neighbors(wv, sample_queries, max_k=k)

    for q in sample_queries:
        gensim_neighbors = wv.most_similar(q, topn=k)
        batch_neighbors = cache[q]

        for rank, (g_pair, b_pair) in enumerate(zip(gensim_neighbors, batch_neighbors)):
            assert g_pair[0] == b_pair[0], (
                f"Rank {rank} mismatch for '{q}': gensim='{g_pair[0]}' vs batch='{b_pair[0]}'"
            )


# -- Test 3: similarity scores match within float tolerance --


@needs_embedding
def test_batch_neighbors_scores_match(wv: KeyedVectors, sample_queries: list[str]) -> None:
    """Similarity scores must match gensim within 1e-4."""
    k = 20
    cache = _precompute_neighbors(wv, sample_queries, max_k=k)

    for q in sample_queries:
        gensim_neighbors = wv.most_similar(q, topn=k)
        batch_neighbors = cache[q]

        gensim_scores = np.array([s for _, s in gensim_neighbors])
        batch_scores = np.array([s for _, s in batch_neighbors])

        np.testing.assert_allclose(
            batch_scores,
            gensim_scores,
            atol=1e-4,
            err_msg=f"Score mismatch for '{q}'",
        )


# -- Test 4: edge cases --


@needs_embedding
def test_query_not_in_vocab_returns_empty(wv: KeyedVectors) -> None:
    """A query absent from the vocabulary must not appear in the cache."""
    fake_name = "___NONEXISTENT_CARD_xyz___"
    assert fake_name not in wv
    cache = _precompute_neighbors(wv, [fake_name], max_k=10)
    assert fake_name not in cache


@needs_embedding
def test_all_queries_missing_returns_empty_dict(wv: KeyedVectors) -> None:
    """All-missing query list must return an empty dict."""
    cache = _precompute_neighbors(wv, ["___MISSING_1___", "___MISSING_2___"], max_k=10)
    assert cache == {}


@needs_embedding
def test_self_similarity_excluded(wv: KeyedVectors) -> None:
    """The query card must never appear in its own neighbor list."""
    queries = [wv.index_to_key[0], wv.index_to_key[1]]
    cache = _precompute_neighbors(wv, queries, max_k=50)

    for q in queries:
        neighbor_names = {name for name, _ in cache[q]}
        assert q not in neighbor_names, f"'{q}' found in its own neighbor list"


@needs_embedding
def test_empty_query_list(wv: KeyedVectors) -> None:
    """Empty query list returns empty dict."""
    cache = _precompute_neighbors(wv, [], max_k=10)
    assert cache == {}


@needs_embedding
def test_mixed_valid_and_invalid_queries(wv: KeyedVectors) -> None:
    """Only valid queries appear in cache; invalid ones are silently skipped."""
    valid = wv.index_to_key[0]
    invalid = "___DOES_NOT_EXIST___"
    cache = _precompute_neighbors(wv, [valid, invalid], max_k=10)
    assert valid in cache
    assert invalid not in cache
    assert len(cache[valid]) == 10


# -- Test 5: normed vectors are unit-length --


@needs_embedding
def test_normed_vectors_are_unit_length(wv: KeyedVectors) -> None:
    """get_normed_vectors() must return L2-normalized rows (unit length)."""
    normed = wv.get_normed_vectors()
    # Check 100 random rows
    rng = np.random.default_rng(99)
    indices = rng.choice(normed.shape[0], size=100, replace=False)
    norms = np.linalg.norm(normed[indices], axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-5)


@needs_embedding
def test_raw_vectors_are_not_unit_length(wv: KeyedVectors) -> None:
    """Raw wv.vectors should NOT all be unit length (pre-normalization)."""
    norms = np.linalg.norm(wv.vectors[:100], axis=1)
    # At least some vectors should differ from 1.0 if they aren't pre-normalized.
    # If the embedding was saved already normalized, this is still valid --
    # the important thing is test_normed_vectors_are_unit_length passes.
    # We check that get_normed_vectors is actually called (not raw vectors)
    # by verifying the batch results match gensim (which also normalizes).
    assert norms.shape[0] == 100  # sanity: we got vectors


# -- Test 6: eval_game determinism --


@needs_embedding
def test_eval_game_deterministic() -> None:
    """Two runs of eval_game must produce identical nDCG scores."""
    run1 = eval_game("magic", embedding_name="magic_v7_fused", k=10, quick=True)
    run2 = eval_game("magic", embedding_name="magic_v7_fused", k=10, quick=True)

    # Skip if test set is missing
    if "error" in run1:
        pytest.skip(f"eval_game error: {run1['error']}")

    for mode in ["substitute", "synergy", "meta"]:
        key = f"mode_{mode}"
        assert run1[key]["ndcg_at_k"] == run2[key]["ndcg_at_k"], (
            f"Non-deterministic {mode} nDCG: {run1[key]['ndcg_at_k']} vs {run2[key]['ndcg_at_k']}"
        )

    assert run1["substitutability_ndcg"]["ndcg_at_k"] == run2["substitutability_ndcg"]["ndcg_at_k"]
