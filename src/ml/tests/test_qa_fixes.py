#!/usr/bin/env python3
"""Tests for QA run 2 bug fixes.

Covers:
1. YGO/Pokemon deck normalization: legacy "Main" key -> "Main Deck"
2. Meta mode resolves to jaccard (not fusion)
3. Zero-score synergy filtering in contextual discovery
4. Search 503 on backend errors
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ml.utils.path_setup import setup_project_paths


setup_project_paths()

from ml.api.api import SimilarityRequest, UseCaseEnum, _normalize_deck_format, _resolve_method
from ml.deck_building.contextual_discovery import ContextualCardDiscovery


# ---------------------------------------------------------------------------
# 1. Deck normalization: legacy "Main" key -> game-specific partition name
# ---------------------------------------------------------------------------


class TestNormalizeDeckFormat:
    def test_yugioh_main_becomes_main_deck(self):
        deck = {"Main": ["Blue-Eyes White Dragon"]}
        result = _normalize_deck_format(deck, "yugioh")
        assert result["partitions"][0]["name"] == "Main Deck"

    def test_magic_main_stays_main(self):
        deck = {"Main": ["Lightning Bolt"]}
        result = _normalize_deck_format(deck, "magic")
        assert result["partitions"][0]["name"] == "Main"

    def test_pokemon_main_becomes_main_deck(self):
        deck = {"Main": ["Pikachu V"]}
        result = _normalize_deck_format(deck, "pokemon")
        assert result["partitions"][0]["name"] == "Main Deck"

    def test_sideboard_key_preserved(self):
        deck = {"Main": ["Lightning Bolt"], "Sideboard": ["Pyroblast"]}
        result = _normalize_deck_format(deck, "magic")
        names = {p["name"] for p in result["partitions"]}
        assert "Main" in names
        assert "Sideboard" in names

    def test_partitions_format_passes_through(self):
        deck = {"partitions": [{"name": "Main Deck", "cards": [{"name": "X", "count": 1}]}]}
        assert _normalize_deck_format(deck, "yugioh") is deck

    def test_card_entries_from_strings(self):
        deck = {"Main": ["Card A", "Card B"]}
        result = _normalize_deck_format(deck, "magic")
        cards = result["partitions"][0]["cards"]
        assert cards == [{"name": "Card A", "count": 1}, {"name": "Card B", "count": 1}]

    def test_card_entries_from_dicts(self):
        deck = {"Main": [{"name": "Card A", "count": 4}]}
        result = _normalize_deck_format(deck, "magic")
        cards = result["partitions"][0]["cards"]
        assert cards == [{"name": "Card A", "count": 4}]


# ---------------------------------------------------------------------------
# 2. Meta mode -> jaccard
# ---------------------------------------------------------------------------


class TestResolveMethod:
    def test_meta_uses_meta(self):
        req = SimilarityRequest(query="X", game="magic", use_case=UseCaseEnum.meta)
        assert _resolve_method(req) == "meta"

    def test_substitute_uses_embedding(self):
        req = SimilarityRequest(query="X", game="magic", use_case=UseCaseEnum.substitute)
        assert _resolve_method(req) == "embedding"

    def test_synergy_uses_jaccard(self):
        req = SimilarityRequest(query="X", game="magic", use_case=UseCaseEnum.synergy)
        assert _resolve_method(req) == "jaccard"

    def test_explicit_mode_overrides_use_case(self):
        req = SimilarityRequest(query="X", game="magic", use_case=UseCaseEnum.meta, mode="fusion")
        assert _resolve_method(req) == "fusion"

    def test_default_is_embedding(self):
        req = SimilarityRequest(query="X", game="magic")
        assert _resolve_method(req) == "embedding"


# ---------------------------------------------------------------------------
# 3. Zero-score synergy filtering
# ---------------------------------------------------------------------------


class TestZeroScoreSynergyFiltering:
    def _make_discovery(self, adj: dict[str, set[str]]) -> ContextualCardDiscovery:
        """Build a ContextualCardDiscovery with a mock fusion that has the given adj graph."""
        fusion = MagicMock()
        fusion.adj = adj
        fusion.similar.side_effect = KeyError("no embeddings")
        return ContextualCardDiscovery(fusion=fusion)

    def test_filters_zero_scores(self):
        # Card A connects to B (shared neighbor) and C (no shared neighbors -> score 0)
        adj = {
            "A": {"B", "C"},
            "B": {"A", "C"},
            "C": set(),  # no neighbors -> Jaccard with A's neighborhood = 0
        }
        discovery = self._make_discovery(adj)
        synergies = discovery.find_synergies("A", top_k=10)
        synergy_cards = {s.card for s in synergies}
        # C should be filtered out (score 0.0 because C has no neighbors)
        assert "C" not in synergy_cards or all(s.score > 0.0 for s in synergies if s.card == "C")

    def test_keeps_nonzero_scores(self):
        # A and B share neighbor C -> nonzero Jaccard
        adj = {
            "A": {"B", "C"},
            "B": {"A", "C"},
            "C": {"A", "B"},
        }
        discovery = self._make_discovery(adj)
        synergies = discovery.find_synergies("A", top_k=10)
        assert len(synergies) > 0
        assert all(s.score > 0.0 for s in synergies)


# ---------------------------------------------------------------------------
# 4. Search 503 on backend error
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 5. Color identity filtering
# ---------------------------------------------------------------------------


class TestColorIdentityFiltering:
    def test_extract_deck_colors_magic(self):
        from ml.api.api import _extract_deck_colors

        deck = {
            "partitions": [
                {
                    "name": "Main",
                    "cards": [
                        {"name": "Lightning Bolt", "count": 4},
                        {"name": "Goblin Guide", "count": 4},
                    ],
                }
            ]
        }
        metadata = {
            "Lightning Bolt": {"color_identity_str": "R"},
            "Goblin Guide": {"color_identity_str": "R"},
        }
        colors = _extract_deck_colors(deck, "magic", metadata)
        assert colors == {"R"}

    def test_extract_deck_colors_multicolor(self):
        from ml.api.api import _extract_deck_colors

        deck = {
            "partitions": [
                {
                    "name": "Main",
                    "cards": [
                        {"name": "Lightning Bolt", "count": 4},
                        {"name": "Counterspell", "count": 4},
                    ],
                }
            ]
        }
        metadata = {
            "Lightning Bolt": {"color_identity_str": "R"},
            "Counterspell": {"color_identity_str": "U"},
        }
        colors = _extract_deck_colors(deck, "magic", metadata)
        assert colors == {"R", "U"}

    def test_extract_deck_colors_non_magic(self):
        from ml.api.api import _extract_deck_colors

        deck = {"partitions": [{"name": "Main Deck", "cards": [{"name": "X", "count": 1}]}]}
        assert _extract_deck_colors(deck, "yugioh", {}) is None

    def test_wrap_cand_fn_filters_offcolor(self):
        from ml.api.api import _wrap_cand_fn_color_filter

        def cand_fn(card, k):
            return [("Red Card", 0.9), ("Green Card", 0.8), ("Red Card 2", 0.7)]

        metadata = {
            "Red Card": {"color_identity_str": "R"},
            "Green Card": {"color_identity_str": "G"},
            "Red Card 2": {"color_identity_str": "R"},
        }
        filtered = _wrap_cand_fn_color_filter(cand_fn, {"R"}, metadata)
        results = filtered("test", 5)
        cards = [c for c, _ in results]
        assert "Green Card" not in cards
        assert "Red Card" in cards
        assert "Red Card 2" in cards

    def test_wrap_cand_fn_allows_colorless(self):
        from ml.api.api import _wrap_cand_fn_color_filter

        def cand_fn(card, k):
            return [("Sol Ring", 0.9), ("Green Card", 0.8)]

        metadata = {
            "Sol Ring": {"color_identity_str": ""},
            "Green Card": {"color_identity_str": "G"},
        }
        filtered = _wrap_cand_fn_color_filter(cand_fn, {"R"}, metadata)
        results = filtered("test", 5)
        cards = [c for c, _ in results]
        # Colorless cards (empty identity) should pass - empty set is subset of any set
        assert "Sol Ring" in cards
        assert "Green Card" not in cards

    def test_wrap_cand_fn_allows_unknown_cards(self):
        from ml.api.api import _wrap_cand_fn_color_filter

        def cand_fn(card, k):
            return [("Unknown Card", 0.9)]

        filtered = _wrap_cand_fn_color_filter(cand_fn, {"R"}, {})
        results = filtered("test", 5)
        # Cards not in metadata should pass through (no data to filter on)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# 6. Score normalization (frontend logic, tested via pure function extraction)
# ---------------------------------------------------------------------------


class TestScoreNormalization:
    """Test the normalization logic used in the frontend."""

    def _normalize(self, scores):
        """Mirror the frontend normalization logic."""
        max_score = max(scores) if scores else 1
        needs_norm = max_score > 0 and max_score < 0.1
        if needs_norm:
            return [(s / max_score) * 0.95 for s in scores]
        return scores

    def test_fusion_scores_normalized(self):
        """Fusion scores (0.007-0.009) should be normalized to readable range."""
        raw = [0.009, 0.008, 0.007, 0.006]
        normed = self._normalize(raw)
        assert normed[0] == pytest.approx(0.95, abs=0.01)
        assert all(n > 0.5 for n in normed)

    def test_normal_scores_unchanged(self):
        """Normal scores (0.3-0.9) should not be modified."""
        raw = [0.9, 0.7, 0.5, 0.3]
        normed = self._normalize(raw)
        assert normed == raw


class TestSearch503OnBackendError:
    def test_search_raises_503_on_client_error(self):
        """When client.search() raises, the API should return 503, not 500."""
        from fastapi.testclient import TestClient

        from ml.api.api import app

        client = TestClient(app, raise_server_exceptions=False)

        # Mock _get_search_client to return a client that raises on search()
        mock_search_client = MagicMock()
        mock_search_client.search.side_effect = ConnectionError("Meilisearch down")

        with patch("ml.api.api._get_search_client", return_value=mock_search_client):
            resp = client.post(
                "/v1/search",
                json={"query": "test", "game": "magic", "limit": 5},
            )
            assert resp.status_code == 503
            assert "Search backend error" in resp.json()["detail"]

    def test_search_returns_503_when_client_none(self):
        """When no search backend is available, the API should return 503."""
        from fastapi.testclient import TestClient

        from ml.api.api import app

        client = TestClient(app, raise_server_exceptions=False)

        with patch("ml.api.api._get_search_client", return_value=None):
            resp = client.post(
                "/v1/search",
                json={"query": "test", "game": "magic", "limit": 5},
            )
            assert resp.status_code == 503
