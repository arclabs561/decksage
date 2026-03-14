"""Unit tests for HybridSearch class.

All external services (MeiliSearch, Qdrant) are mocked -- no running instances needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ml.search.hybrid_search import HybridSearch, SearchResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mock_embeddings(vocab: dict[str, list[float]] | None = None) -> MagicMock:
    """Return a KeyedVectors-like mock with __contains__ and __getitem__."""
    if vocab is None:
        vocab = {
            "Lightning Bolt": [0.1] * 128,
            "Counterspell": [0.2] * 128,
        }
    emb = MagicMock()
    emb.vector_size = 128
    emb.__contains__ = lambda self, k: k in vocab
    emb.__getitem__ = lambda self, k: np.array(vocab[k], dtype=np.float32)
    emb.most_similar = MagicMock(return_value=[])
    return emb


def _make_meili_hit(name: str, score: float = 0.9) -> dict:
    return {
        "name": name,
        "_rankingScore": score,
        "image_url": f"http://img/{name}.png",
        "ref_url": f"http://ref/{name}",
    }


def _make_scored_point(name: str, score: float = 0.1) -> MagicMock:
    """Qdrant ScoredPoint mock. score = cosine distance (lower = more similar)."""
    pt = MagicMock()
    pt.score = score
    pt.payload = {
        "name": name,
        "image_url": f"http://img/{name}.png",
        "ref_url": f"http://ref/{name}",
    }
    return pt


def _build_search(
    meili_enabled: bool = True,
    qdrant_enabled: bool = True,
    embeddings: MagicMock | None = "default",
    meili_hits: list | None = None,
    qdrant_points: list | None = None,
) -> HybridSearch:
    """Build a HybridSearch with mocked clients, bypassing real connections.

    Sets meilisearch/qdrant attributes directly on the instance after
    constructing with both disabled (clients=None via patching), then
    re-enables whichever backends are requested.
    """
    if embeddings == "default":
        embeddings = _make_mock_embeddings()

    # Patch module-level client classes to None so __init__ skips connection
    with (
        patch("ml.search.hybrid_search.MeilisearchClient", None),
        patch("ml.search.hybrid_search.QdrantClient", None),
    ):
        hs = HybridSearch(embeddings=embeddings)

    # Wire up mock clients post-init
    if meili_enabled:
        mock_index = MagicMock()
        mock_index.search.return_value = {
            "hits": meili_hits if meili_hits is not None else [],
        }
        mock_index.fetch_info.return_value = None
        mock_meili = MagicMock()
        mock_meili.index.return_value = mock_index
        hs.meilisearch = mock_meili
    else:
        hs.meilisearch = None

    if qdrant_enabled:
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = (
            qdrant_points if qdrant_points is not None else []
        )
        hs.qdrant = mock_qdrant
    else:
        hs.qdrant = None

    return hs


# ---------------------------------------------------------------------------
# TestHybridSearchInit
# ---------------------------------------------------------------------------

class TestHybridSearchInit:
    """Initialization and graceful degradation on connection failure."""

    def test_both_clients_enabled(self):
        mock_meili_cls = MagicMock()
        mock_meili_instance = MagicMock()
        mock_meili_cls.return_value = mock_meili_instance
        mock_index = MagicMock()
        mock_meili_instance.index.return_value = mock_index

        mock_qdrant_cls = MagicMock()
        mock_qdrant_instance = MagicMock()
        mock_qdrant_cls.return_value = mock_qdrant_instance
        collections = MagicMock()
        collections.collections = [MagicMock(name="cards")]
        mock_qdrant_instance.get_collections.return_value = collections

        with (
            patch("ml.search.hybrid_search.MeilisearchClient", mock_meili_cls),
            patch("ml.search.hybrid_search.QdrantClient", mock_qdrant_cls),
            patch("ml.search.hybrid_search.models", MagicMock()),
        ):
            hs = HybridSearch(
                meilisearch_url="http://localhost:7700",
                qdrant_url="http://localhost:6333",
                embeddings=_make_mock_embeddings(),
            )

        assert hs.meilisearch is not None
        assert hs.qdrant is not None

    def test_meilisearch_unavailable(self):
        """Connection refused during init -> meilisearch disabled, qdrant ok."""
        mock_meili_cls = MagicMock()
        mock_meili_instance = MagicMock()
        mock_meili_cls.return_value = mock_meili_instance
        mock_index = MagicMock()
        mock_index.fetch_info.side_effect = ConnectionError("Connection refused")
        mock_meili_instance.index.return_value = mock_index

        mock_qdrant_cls = MagicMock()
        mock_qdrant_instance = MagicMock()
        mock_qdrant_cls.return_value = mock_qdrant_instance
        collections = MagicMock()
        collections.collections = [MagicMock(name="cards")]
        mock_qdrant_instance.get_collections.return_value = collections

        with (
            patch("ml.search.hybrid_search.MeilisearchClient", mock_meili_cls),
            patch("ml.search.hybrid_search.QdrantClient", mock_qdrant_cls),
            patch("ml.search.hybrid_search.models", MagicMock()),
        ):
            hs = HybridSearch(embeddings=_make_mock_embeddings())

        assert hs.meilisearch is None  # disabled after connection failure
        assert hs.qdrant is not None

    def test_qdrant_unavailable(self):
        """Qdrant connection failure -> qdrant disabled, meilisearch ok."""
        mock_meili_cls = MagicMock()
        mock_meili_instance = MagicMock()
        mock_meili_cls.return_value = mock_meili_instance
        mock_index = MagicMock()
        mock_meili_instance.index.return_value = mock_index

        mock_qdrant_cls = MagicMock()
        mock_qdrant_instance = MagicMock()
        mock_qdrant_cls.return_value = mock_qdrant_instance
        mock_qdrant_instance.get_collections.side_effect = ConnectionError("refused")

        with (
            patch("ml.search.hybrid_search.MeilisearchClient", mock_meili_cls),
            patch("ml.search.hybrid_search.QdrantClient", mock_qdrant_cls),
            patch("ml.search.hybrid_search.models", MagicMock()),
        ):
            hs = HybridSearch(embeddings=_make_mock_embeddings())

        assert hs.meilisearch is not None
        assert hs.qdrant is None

    def test_both_unavailable(self):
        """Both backends down -> both disabled, search returns empty."""
        mock_meili_cls = MagicMock()
        mock_meili_instance = MagicMock()
        mock_meili_cls.return_value = mock_meili_instance
        mock_index = MagicMock()
        mock_index.fetch_info.side_effect = ConnectionError("refused")
        mock_meili_instance.index.return_value = mock_index

        mock_qdrant_cls = MagicMock()
        mock_qdrant_instance = MagicMock()
        mock_qdrant_cls.return_value = mock_qdrant_instance
        mock_qdrant_instance.get_collections.side_effect = ConnectionError("refused")

        with (
            patch("ml.search.hybrid_search.MeilisearchClient", mock_meili_cls),
            patch("ml.search.hybrid_search.QdrantClient", mock_qdrant_cls),
            patch("ml.search.hybrid_search.models", MagicMock()),
        ):
            hs = HybridSearch(embeddings=_make_mock_embeddings())

        assert hs.meilisearch is None
        assert hs.qdrant is None
        assert hs.search("anything") == []


# ---------------------------------------------------------------------------
# TestHybridSearchSearch
# ---------------------------------------------------------------------------

class TestHybridSearchSearch:
    """Core hybrid search method."""

    def test_both_backends_merge(self):
        """Results from both backends are merged and sorted by combined score."""
        hs = _build_search(
            meili_hits=[_make_meili_hit("Lightning Bolt", 0.9)],
            qdrant_points=[_make_scored_point("Counterspell", 0.1)],
        )
        # Query must be in embeddings vocab for qdrant path to fire
        results = hs.search("Lightning Bolt", limit=10, text_weight=0.5, vector_weight=0.5)
        names = [r.card_name for r in results]
        assert "Lightning Bolt" in names
        assert "Counterspell" in names

    def test_deduplication_hybrid_source(self):
        """Card in both backends gets combined score and source='hybrid'."""
        hs = _build_search(
            meili_hits=[_make_meili_hit("Lightning Bolt", 0.8)],
            qdrant_points=[_make_scored_point("Lightning Bolt", 0.2)],
        )
        results = hs.search("Lightning Bolt", limit=10, text_weight=0.5, vector_weight=0.5)
        bolt_results = [r for r in results if r.card_name == "Lightning Bolt"]
        assert len(bolt_results) == 1
        assert bolt_results[0].source == "hybrid"
        # text contribution: 0.8 * 0.5 = 0.4, vector: 0.2 * 0.5 = 0.1
        assert bolt_results[0].score == pytest.approx(0.5, abs=0.01)

    def test_text_weight_one_only_meili(self):
        """text_weight=1.0, vector_weight=0.0 -> only meilisearch queried."""
        hs = _build_search(
            meili_hits=[_make_meili_hit("Bolt", 0.9)],
            qdrant_points=[_make_scored_point("Counter", 0.1)],
        )
        results = hs.search("bolt", text_weight=1.0, vector_weight=0.0)
        names = [r.card_name for r in results]
        assert "Bolt" in names
        # Qdrant should NOT be queried (vector_weight=0)
        hs.qdrant.search.assert_not_called()

    def test_vector_weight_one_only_qdrant(self):
        """text_weight=0.0, vector_weight=1.0 -> only qdrant queried."""
        hs = _build_search(
            meili_hits=[_make_meili_hit("Bolt", 0.9)],
            qdrant_points=[_make_scored_point("Counterspell", 0.1)],
        )
        # Query must be in embeddings vocab for qdrant to fire
        results = hs.search("Counterspell", text_weight=0.0, vector_weight=1.0)
        # Meili should NOT be queried
        hs.meilisearch.index.return_value.search.assert_not_called()
        names = [r.card_name for r in results]
        assert "Counterspell" in names

    def test_returns_search_result_objects(self):
        hs = _build_search(meili_hits=[_make_meili_hit("Bolt", 0.9)])
        results = hs.search("bolt", text_weight=1.0, vector_weight=0.0)
        assert len(results) >= 1
        r = results[0]
        assert isinstance(r, SearchResult)
        assert isinstance(r.card_name, str)
        assert isinstance(r.score, float)
        assert r.source in ("meilisearch", "qdrant", "hybrid")
        assert r.metadata is not None

    def test_empty_query_returns_empty_or_handles(self):
        """Empty string query should not crash."""
        hs = _build_search(meili_hits=[], qdrant_points=[])
        results = hs.search("", limit=10)
        assert isinstance(results, list)

    def test_limit_respected(self):
        """Results are truncated to limit."""
        hits = [_make_meili_hit(f"Card{i}", 0.9 - i * 0.01) for i in range(20)]
        hs = _build_search(meili_hits=hits)
        results = hs.search("card", limit=5, text_weight=1.0, vector_weight=0.0)
        assert len(results) <= 5


# ---------------------------------------------------------------------------
# TestHybridSearchTextOnly
# ---------------------------------------------------------------------------

class TestHybridSearchTextOnly:
    def test_text_only_queries_meili(self):
        hs = _build_search(
            meili_hits=[_make_meili_hit("Bolt", 0.85)],
            qdrant_points=[_make_scored_point("Counter", 0.1)],
        )
        results = hs.search_text_only("bolt")
        assert len(results) >= 1
        assert results[0].card_name == "Bolt"
        # Qdrant must not be touched
        hs.qdrant.search.assert_not_called()

    def test_text_only_meili_disabled(self):
        hs = _build_search(meili_enabled=False)
        results = hs.search_text_only("bolt")
        assert results == []


# ---------------------------------------------------------------------------
# TestHybridSearchVectorOnly
# ---------------------------------------------------------------------------

class TestHybridSearchVectorOnly:
    def test_vector_only_queries_qdrant(self):
        hs = _build_search(
            meili_hits=[_make_meili_hit("Bolt", 0.9)],
            qdrant_points=[_make_scored_point("Counter", 0.15)],
        )
        results = hs.search_vector_only("Lightning Bolt")
        assert len(results) >= 1
        # Meili must not be queried
        hs.meilisearch.index.return_value.search.assert_not_called()

    def test_vector_only_qdrant_disabled(self):
        hs = _build_search(qdrant_enabled=False)
        results = hs.search_vector_only("bolt")
        assert results == []

    def test_vector_only_query_not_in_embeddings(self):
        """Query not in embeddings vocab and most_similar returns [] -> empty."""
        vocab = {"Lightning Bolt": [0.1] * 128}
        emb = _make_mock_embeddings(vocab)
        emb.most_similar.return_value = []
        hs = _build_search(
            embeddings=emb,
            qdrant_points=[_make_scored_point("X", 0.1)],
        )
        results = hs.search_vector_only("Unknown Card")
        assert results == []


# ---------------------------------------------------------------------------
# TestHybridSearchDegradation
# ---------------------------------------------------------------------------

class TestHybridSearchDegradation:
    """Runtime exceptions during search degrade gracefully."""

    def test_meili_exception_falls_back(self):
        """Meilisearch raises during search -> qdrant results still returned."""
        hs = _build_search(
            qdrant_points=[_make_scored_point("Counterspell", 0.1)],
        )
        # Make meili raise
        hs.meilisearch.index.return_value.search.side_effect = RuntimeError("meili down")
        # Query must be in embeddings vocab for qdrant path
        results = hs.search("Counterspell", text_weight=0.5, vector_weight=0.5)
        assert len(results) >= 1
        assert results[0].card_name == "Counterspell"

    def test_qdrant_exception_falls_back(self):
        """Qdrant raises during search -> meilisearch results still returned."""
        hs = _build_search(
            meili_hits=[_make_meili_hit("Lightning Bolt", 0.9)],
        )
        hs.qdrant.search.side_effect = RuntimeError("qdrant down")
        results = hs.search("Lightning Bolt", text_weight=0.5, vector_weight=0.5)
        assert len(results) >= 1
        assert results[0].card_name == "Lightning Bolt"

    def test_both_raise_returns_empty(self):
        """Both backends raise -> empty list, no crash."""
        hs = _build_search()
        hs.meilisearch.index.return_value.search.side_effect = RuntimeError("down")
        hs.qdrant.search.side_effect = RuntimeError("also down")
        results = hs.search("Lightning Bolt", text_weight=0.5, vector_weight=0.5)
        assert results == []
