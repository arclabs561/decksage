#!/usr/bin/env python3
"""
End-to-end API tests exercising readiness and major modes, including faceted Jaccard.

These run the FastAPI app in-process and inject minimal state to avoid heavy I/O.
"""

from __future__ import annotations

from typing import List, Tuple

from fastapi.testclient import TestClient


def _stub_embeddings(keys: List[str]):
    class _E:
        def __init__(self, keys: List[str]):
            self.index_to_key = list(keys)
            self._set = set(keys)

        def __contains__(self, key: str) -> bool:
            return key in self._set

        def most_similar(self, query: str, topn: int = 10) -> List[Tuple[str, float]]:
            return [(k, 0.5) for k in self.index_to_key[:topn] if k != query]

        @property
        def vector_size(self) -> int:
            return 64

        def __len__(self) -> int:
            return len(self.index_to_key)

    return _E(keys)


def test_ready_and_modes_advertised():
    from ..api import api as api_mod

    client = TestClient(api_mod.app)

    # Initially not ready
    r = client.get("/ready")
    assert r.status_code == 503

    # Inject embeddings and minimal graph + attrs
    state = api_mod.get_state()
    state.embeddings = _stub_embeddings(["Bolt", "A", "B"])
    state.graph_data = {"adj": {"Bolt": {"A"}, "A": {"Bolt"}}}
    state.card_attrs = {"Bolt": {"cmc": 1, "types": {"Instant"}}, "A": {"cmc": 1, "types": {"Instant"}}}

    r2 = client.get("/ready")
    assert r2.status_code == 200
    modes = r2.json().get("available_methods", [])
    assert "embedding" in modes and "jaccard" in modes and "fusion" in modes and "jaccard_faceted" in modes


def test_embedding_synergy_faceted_endpoints():
    from ..api import api as api_mod

    client = TestClient(api_mod.app)
    state = api_mod.get_state()
    state.embeddings = _stub_embeddings(["Bolt", "A", "B"])
    state.graph_data = {"adj": {"Bolt": {"A", "B"}, "A": {"Bolt"}, "B": {"Bolt"}}}
    state.card_attrs = {"Bolt": {"cmc": 1, "types": {"Instant"}}, "A": {"cmc": 1, "types": {"Instant"}}, "B": {"cmc": 2, "types": {"Creature"}}}

    # Embedding substitute
    r1 = client.post("/v1/similar", json={"query": "Bolt", "use_case": "substitute", "top_k": 2})
    assert r1.status_code == 200
    assert r1.json()["model_info"]["method_used"] == "embedding"

    # Synergy
    r2 = client.get("/v1/cards/Bolt/similar", params={"mode": "synergy", "k": 2})
    assert r2.status_code == 200
    assert r2.json()["model_info"]["method_used"] == "jaccard"

    # Faceted
    r3 = client.post("/v1/similar", json={"query": "Bolt", "mode": "jaccard_faceted", "facet": "type", "top_k": 2, "use_case": "synergy"})
    assert r3.status_code == 200
    data = r3.json()
    assert data["model_info"]["method_used"] == "jaccard_faceted"
    names = [r["card"] for r in data["results"]]
    assert names[0] == "A"


