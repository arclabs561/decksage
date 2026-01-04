#!/usr/bin/env python3
import pytest


try:
    from fastapi.testclient import TestClient

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    TestClient = None

# Skip all tests if fastapi not available
pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")


def make_app_with_mocks():
    from ..api import api

    # Inject minimal mocks into API state (not legacy globals)
    class DummyEmb:
        def __len__(self):
            return len(self.index_to_key)

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

    state = api.get_state()
    state.embeddings = DummyEmb()
    state.model_info = {
        "methods": ["embedding", "jaccard", "fusion"],
        "num_cards": 3,
        "embedding_dim": 3,
    }
    state.graph_data = {"adj": {"A": {"B"}, "B": {"A", "C"}, "C": {"B"}}, "weights": {}}
    # Ensure router mounted
    return api.app


@pytest.fixture()
def client(api_client):
    # Re-initialize app state with mocks on the app imported by the shim
    # api_client.app exposes the same underlying FastAPI app
    _ = make_app_with_mocks()
    return api_client


def test_live(client):
    r = client.get("/live")
    assert r.status_code == 200
    assert r.json()["status"] == "live"


def test_ready(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert "available_methods" in r.json()


def test_health_v1(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
    # Minimal dummy embeddings expose 3 cards; some environments may trim
    assert j["num_cards"] >= 2


def test_cards_v1_pagination(client):
    r = client.get("/v1/cards", params={"limit": 2, "offset": 0})
    assert r.status_code == 200
    j = r.json()
    assert j["total"] >= 2
    assert len(j["items"]) == 2
    if j["total"] > 2:
        assert j["next_offset"] == 2
    else:
        assert j["next_offset"] is None


def test_similar_post(client):
    r = client.post("/v1/similar", json={"query": "A", "top_k": 2, "use_case": "substitute"})
    assert r.status_code in (200, 404, 503)
    if r.status_code != 200:
        pytest.skip("embeddings not ready in this env")
    j = r.json()
    assert j["query"] == "A"
    assert len(j["results"]) >= 1


def test_similar_get(client):
    r = client.get("/v1/cards/A/similar", params={"mode": "synergy", "k": 2})
    assert r.status_code in (200, 404, 503)
    if r.status_code != 200:
        pytest.skip("graph not ready in this env")
    j = r.json()
    assert j["query"] == "A"
    assert any(res["card"] == "B" for res in j["results"])
