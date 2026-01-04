#!/usr/bin/env python3
import pytest


try:
    from fastapi.testclient import TestClient

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    TestClient = None

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")


def _setup_state_with_defaults():
    from ..api import api
    from ..similarity import fusion

    # Minimal dummy embeddings
    class DummyEmb:
        def __contains__(self, k):
            return k in {"A", "B", "C"}

        @property
        def index_to_key(self):
            return ["A", "B", "C"]

        @property
        def vector_size(self):
            return 3

        def most_similar(self, q, topn=10):
            return [(c, 0.9) for c in ["B", "C"] if c != q][:topn]

        def similarity(self, q, c):
            return 0.9 if (q, c) in [("A", "B"), ("A", "C")] else 0.0

    state = api.get_state()
    state.embeddings = DummyEmb()
    state.graph_data = {"adj": {"A": {"B", "C"}}, "weights": {}}
    state.model_info = {"methods": ["embedding", "jaccard"]}
    state.fusion_default_weights = fusion.FusionWeights(embed=0.2, jaccard=0.4, functional=0.4)
    return api.app


@pytest.fixture()
def client(api_client):
    _ = _setup_state_with_defaults()
    return api_client


def test_ready_includes_fusion_defaults(client):
    r = client.get("/ready")
    assert r.status_code == 200
    j = r.json()
    assert "fusion" in j.get("available_methods", [])
    assert "fusion_default_weights" in j
    w = j["fusion_default_weights"]
    assert pytest.approx(0.2, rel=1e-6) == w["embed"]
    assert pytest.approx(0.4, rel=1e-6) == w["jaccard"]
    assert pytest.approx(0.4, rel=1e-6) == w["functional"]


def test_fusion_mode_returns_results(client):
    payload = {"query": "A", "top_k": 2, "use_case": "substitute", "mode": "fusion"}
    r = client.post("/v1/similar", json=payload)
    assert r.status_code == 200
    j = r.json()
    assert j["query"] == "A"
    assert len(j["results"]) >= 1
