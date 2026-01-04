#!/usr/bin/env python3
"""
Small, focused experiments to probe nuanced unsupported behaviors:
- API readiness/modes without embeddings/graph
- Jaccard land filtering behavior
- Fusion behavior with/without functional tagger
- Market data stubs and budget substitute logic

Tests are intentionally lightweight and avoid external APIs or large data.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest


def _stub_embeddings(keys: list[str]):
    class _E:
        def __init__(self, keys: list[str]):
            self.index_to_key = list(keys)
            self._set = set(keys)

        def __contains__(self, key: str) -> bool:
            return key in self._set

        def most_similar(self, query: str, topn: int = 10) -> list[tuple[str, float]]:
            return [(k, 0.5) for k in self.index_to_key[:topn] if k != query]

        @property
        def vector_size(self) -> int:
            return 64

        def __len__(self) -> int:
            return len(self.index_to_key)

    return _E(keys)


def test_api_readiness_and_live_without_models(api_client):
    """API should be live but not ready when no embeddings are loaded."""
    from ..api import api as api_mod

    # Reset state to ensure no embeddings are loaded
    # Clear the entire state object to ensure clean slate
    if hasattr(api_mod.app.state, "api"):
        delattr(api_mod.app.state, "api")

    # Clear legacy module-level globals that _adopt_legacy_globals() uses
    api_mod.embeddings = None
    api_mod.graph_data = None
    api_mod.model_info = {}

    # Get fresh state (will be empty)
    state = api_mod.get_state()
    assert state.embeddings is None, "State should be clean at test start"

    client = api_client
    # Live should be healthy regardless of models
    r_live = client.get("/live")
    assert r_live.status_code == 200
    assert r_live.json().get("status") == "live"

    # Ready should 503 until embeddings are loaded
    r_ready = client.get("/ready")
    assert r_ready.status_code == 503, (
        f"Expected 503, got {r_ready.status_code}. Response: {r_ready.json()}"
    )
    assert "not ready" in r_ready.json().get("detail", ""), (
        f"Expected 'not ready' in detail, got: {r_ready.json()}"
    )


def test_api_synergy_requires_graph_not_loaded_returns_503(api_client):
    """Synergy (Jaccard) mode requires graph; without it, expect 503."""
    from ..api import api as api_mod

    # Explicitly reset state and load embeddings but not graph
    state = api_mod.get_state()
    state.embeddings = _stub_embeddings(["Lightning Bolt"])  # Need embeddings to get past 404
    state.graph_data = None

    client = api_client
    r = client.get("/v1/cards/Lightning%20Bolt/similar", params={"mode": "synergy", "k": 5})
    assert r.status_code == 503
    assert "Graph data not loaded" in r.json().get("detail", "")


def test_api_embedding_unknown_name_returns_suggestions(api_client):
    """
    The internal implementation suggests close matches when an exact name is missing.
    We monkeypatch a minimal embeddings stub into the module globals.
    """
    from fastapi import HTTPException

    from ..api import api as api_mod

    class _StubEmbeddings:
        def __init__(self, keys: list[str]):
            self.index_to_key = list(keys)
            self._set = set(keys)

        def __contains__(self, key: str) -> bool:  # membership test
            return key in self._set

        def most_similar(self, query: str, topn: int = 10) -> list[tuple[str, float]]:
            # Return a simple, deterministic ordering
            return [(k, 0.5) for k in self.index_to_key[:topn] if k != query]

    # Inject stub embeddings into app state and clear graph
    state = api_mod.get_state()
    state.embeddings = _StubEmbeddings(["Lightning Bolt", "Chain Lightning", "Rift Bolt"])
    state.graph_data = None

    # Force an embedding call with a partial name to trigger suggestions
    req = api_mod.SimilarityRequest(
        query="Lightning", top_k=5, use_case=api_mod.UseCaseEnum.substitute
    )
    with pytest.raises(HTTPException) as exc:
        api_mod._similar_impl(req)

    msg = str(exc.value.detail)
    assert "Suggestions" in msg
    assert "Lightning Bolt" in msg


def test_jaccard_filters_lands_by_default(tmp_path):
    """Verify Jaccard similarity excludes lands by default."""
    pairs_content = "NAME_1,NAME_2\nCard A,Card B\nCard A,Island\n"
    pairs_csv = tmp_path / "pairs.csv"
    pairs_csv.write_text(pairs_content)
    from ..similarity.similarity_methods import jaccard_similarity, load_graph

    # Force CSV loading by passing csv_path and None for graph_db
    adj, _ = load_graph(csv_path=str(pairs_csv), graph_db=None, filter_lands=True)
    similar = jaccard_similarity("Card A", adj)
    names = [c for c, _ in similar]
    assert "Island" not in names
    assert "Card B" in names


def test_jaccard_can_include_lands(tmp_path):
    """Verify Jaccard similarity can include lands if configured."""
    pairs_content = "NAME_1,NAME_2\nCard A,Card B\nCard A,Island\n"
    pairs_csv = tmp_path / "pairs.csv"
    pairs_csv.write_text(pairs_content)

    from ..similarity.similarity_methods import jaccard_similarity, load_graph

    # Force CSV loading by passing csv_path and None for graph_db
    adj, _ = load_graph(csv_path=str(pairs_csv), graph_db=None, filter_lands=False)
    similar = jaccard_similarity("Card A", adj)
    names = [c for c, _ in similar]
    assert "Island" in names
    assert "Card B" in names


def test_fusion_functional_only_with_dummy_tagger():
    """
    With only functional weights active and a dummy tagger, fusion should rank the
    candidate sharing tags highest. We avoid gensim by not using embeddings.
    """
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    # Build small adjacency to seed candidate gathering
    adj: dict[str, set] = {
        "Bolt": {"A", "B"},
        "A": {"Bolt"},
        "B": {"Bolt"},
    }

    # Dummy tagger returns a dataclass-like object with boolean fields.
    class _Tags:
        def __init__(self, card_name: str):
            # One functional feature for A, none for B, some for query
            self.card_name = card_name
            self.creature_removal = card_name in {"Bolt", "A"}
            self.card_draw = False

    class _DummyTagger:
        def tag_card(self, name: str) -> Any:  # signature aligned with MTG tagger usage
            return _Tags(name)

    weights = FusionWeights(embed=0.0, jaccard=0.0, functional=1.0)
    fusion = WeightedLateFusion(embeddings=None, adj=adj, tagger=_DummyTagger(), weights=weights)

    ranked = fusion.similar("Bolt", k=2)
    assert [c for c, _ in ranked] == ["A", "B"], "Functional overlap should rank A before B"


def test_fusion_gracefully_handles_missing_tagger():
    """If tagger is None, fusion should still return candidates from adjacency."""
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    adj: dict[str, set] = {
        "Bolt": {"A", "B"},
        "A": {"Bolt"},
        "B": {"Bolt"},
    }

    weights = FusionWeights(embed=0.0, jaccard=1.0, functional=1.0)  # functional ignored
    fusion = WeightedLateFusion(embeddings=None, adj=adj, tagger=None, weights=weights)
    ranked = fusion.similar("Bolt", k=2)
    assert set(c for c, _ in ranked) == {"A", "B"}


def test_market_api_stubs_require_credentials():
    """External price API classes should refuse to initialize without credentials."""
    try:
        from ..enrichment.card_market_data import CardmarketAPI, TCGPlayerAPI
    except ImportError as e:
        pytest.skip(f"Could not import market API classes: {e}")

    # Unset env variables if present for the scope of this test
    os.environ.pop("TCGPLAYER_API_KEY", None)
    os.environ.pop("CARDMARKET_APP_TOKEN", None)
    os.environ.pop("CARDMARKET_APP_SECRET", None)

    with pytest.raises(ValueError):
        TCGPlayerAPI()
    with pytest.raises(ValueError):
        CardmarketAPI()


def test_budget_substitutes_basic_filtering():
    """Budget substitute finder should filter by max_price and sort by savings."""
    try:
        from ..enrichment.card_market_data import CardPrice, MarketDataManager
    except ImportError as e:
        pytest.skip(f"Could not import market data classes: {e}")

    manager = MarketDataManager(scryfall_card_dir=Path("/nonexistent"))
    # Inject a small in-memory price cache
    manager.price_cache = {
        "Force of Will": CardPrice(card_name="Force of Will", usd=80.0),
        "Counterspell": CardPrice(card_name="Counterspell", usd=0.25),
        "Mana Drain": CardPrice(card_name="Mana Drain", usd=40.0),
        "Daze": CardPrice(card_name="Daze", usd=6.0),
    }

    subs = manager.find_budget_substitutes(
        "Force of Will", ["Counterspell", "Mana Drain", "Daze"], max_price=5.0
    )

    names = [s["card_name"] for s in subs]
    assert names == ["Counterspell"], "Only <= $5 substitutes should remain"


def test_jaccard_faceted_type_filters_candidates(monkeypatch):
    """Facet-aware Jaccard should restrict to same type and still compute Jaccard."""

    from ..api import api as api_mod

    # Build small adj
    adj = {
        "Bolt": {"A", "B", "C"},
        "A": {"Bolt"},
        "B": {"Bolt"},
        "C": {"Bolt"},
    }
    # Attributes: only A and Bolt share type token 'Instant'
    attrs = {
        "Bolt": {"cmc": 1.0, "type_line": "Instant", "types": {"Instant"}},
        "A": {"cmc": 2.0, "type_line": "Instant", "types": {"Instant"}},
        "B": {"cmc": 1.0, "type_line": "Creature", "types": {"Creature"}},
        "C": {"cmc": 1.0, "type_line": "Sorcery", "types": {"Sorcery"}},
    }

    # Inject into API state
    state = api_mod.get_state()
    state.graph_data = {"adj": adj}
    state.card_attrs = attrs
    state.embeddings = None  # Ensure this is not used

    req = api_mod.SimilarityRequest(
        query="Bolt",
        top_k=2,
        use_case=api_mod.UseCaseEnum.synergy,
        mode="jaccard_faceted",
        facet="type",
    )
    resp = api_mod._similar_impl(req)
    names = [r.card for r in resp.results]
    assert names and names[0] == "A"
