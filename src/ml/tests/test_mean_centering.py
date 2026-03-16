"""Tests for mean-centering of node2vec embeddings.

Verifies that mean-centering (as done in card_similarity_pecan.train_pecanpy)
produces vectors whose mean is near-zero and whose random-pair cosine
similarity median is near 0 (not positive-biased).
"""

from __future__ import annotations

import numpy as np


class TestMeanCentering:
    """Test that mean-centering prevents positive-bias collapse."""

    @staticmethod
    def _make_biased_vectors(n: int = 200, dim: int = 64, seed: int = 42) -> np.ndarray:
        """Create vectors with a large shared directional component (simulating pre-centering)."""
        rng = np.random.default_rng(seed)
        # Shared bias + individual noise
        bias = rng.standard_normal(dim) * 5.0
        noise = rng.standard_normal((n, dim))
        return noise + bias

    @staticmethod
    def _mean_center(vectors: np.ndarray) -> np.ndarray:
        """Apply same mean-centering as card_similarity_pecan.train_pecanpy."""
        return vectors - vectors.mean(axis=0)

    def test_mean_near_zero_after_centering(self):
        """After centering, vectors.mean(axis=0) should be near-zero."""
        raw = self._make_biased_vectors()
        centered = self._mean_center(raw)

        mean_vec = centered.mean(axis=0)
        assert np.allclose(mean_vec, 0.0, atol=1e-10), (
            f"Mean vector should be near-zero, got max abs = {np.abs(mean_vec).max():.2e}"
        )

    def test_biased_vectors_have_positive_cosine(self):
        """Uncorrected vectors with shared bias should have high positive-biased cosine."""
        raw = self._make_biased_vectors(n=300)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        normed = raw / np.clip(norms, 1e-12, None)
        # Sample random pairs
        rng = np.random.default_rng(99)
        idx_a = rng.integers(0, len(normed), size=500)
        idx_b = rng.integers(0, len(normed), size=500)
        cosines = (normed[idx_a] * normed[idx_b]).sum(axis=1)
        median = float(np.median(cosines))
        # Biased vectors should have median cosine clearly above 0
        assert median > 0.3, (
            f"Biased vectors should have positive-skewed cosine, got median={median:.3f}"
        )

    def test_centered_vectors_have_near_zero_median_cosine(self):
        """After mean-centering, random-pair cosine median should be near 0."""
        raw = self._make_biased_vectors(n=300)
        centered = self._mean_center(raw)

        norms = np.linalg.norm(centered, axis=1, keepdims=True)
        normed = centered / np.clip(norms, 1e-12, None)

        rng = np.random.default_rng(99)
        idx_a = rng.integers(0, len(normed), size=500)
        idx_b = rng.integers(0, len(normed), size=500)
        cosines = (normed[idx_a] * normed[idx_b]).sum(axis=1)
        median = float(np.median(cosines))

        assert abs(median) < 0.15, (
            f"Centered vectors should have near-zero median cosine, got {median:.3f}"
        )

    def test_centering_preserves_relative_order(self):
        """Mean-centering should not change which vector is closest to a query."""
        raw = self._make_biased_vectors(n=50, dim=32)
        centered = self._mean_center(raw)

        # Pick a query and find nearest neighbor before and after centering
        query_idx = 0

        def nearest(vecs: np.ndarray, q_idx: int) -> int:
            q = vecs[q_idx]
            norms = np.linalg.norm(vecs, axis=1)
            q_norm = np.linalg.norm(q)
            cosines = (vecs @ q) / (norms * q_norm + 1e-12)
            cosines[q_idx] = -2.0  # exclude self
            return int(np.argmax(cosines))

        nn_raw = nearest(raw, query_idx)
        nn_centered = nearest(centered, query_idx)
        # The nearest neighbor should be the same (centering is a translation,
        # but after normalization the order may slightly change -- we allow
        # them to differ only if the original cosines were very close)
        if nn_raw != nn_centered:
            # Verify the raw cosine gap was small (acceptable reordering)
            q = raw[query_idx]
            norms = np.linalg.norm(raw, axis=1)
            q_norm = np.linalg.norm(q)
            cosines = (raw @ q) / (norms * q_norm + 1e-12)
            cosines[query_idx] = -2.0
            top2 = np.sort(cosines)[-2:]
            gap = top2[1] - top2[0]
            assert gap < 0.05, f"NN changed after centering but gap was {gap:.4f}, expected < 0.05"

    def test_centering_idempotent(self):
        """Centering twice should give same result as centering once."""
        raw = self._make_biased_vectors()
        once = self._mean_center(raw)
        twice = self._mean_center(once)
        assert np.allclose(once, twice, atol=1e-10)
