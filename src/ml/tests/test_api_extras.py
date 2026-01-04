#!/usr/bin/env python3
import pytest


try:
    from fastapi.testclient import TestClient

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    TestClient = None

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")


class _DummyEmb:
    def __init__(self, keys):
        self._keys = list(keys)
        self._set = set(self._keys)

    def __contains__(self, k):
        return k in self._set

    def __len__(self):
        return len(self._keys)

    @property
    def index_to_key(self):
        return list(self._keys)

    @property
    def vector_size(self):
        return 3

    def most_similar(self, q, topn=10):
        # Return others with dummy similarity
        return [(c, 0.9) for c in self._keys if c != q][:topn]


@pytest.fixture
def api_client():
    """Create a test client for the API."""
    from fastapi.testclient import TestClient

    from ..api.api import app

    return TestClient(app)


@pytest.fixture()
def client(api_client):
    return api_client


def test_ready_advertises_jaccard_faceted_when_attrs_loaded(client):
    from ..api import api as api_mod

    # Seed embeddings, graph and attributes
    state = api_mod.get_state()
    state.embeddings = _DummyEmb(["Bolt", "A", "B"])
    state.graph_data = {"adj": {"Bolt": {"A", "B"}, "A": {"Bolt"}, "B": {"Bolt"}}}
    state.card_attrs = {
        "Bolt": {"type_line": "Instant"},
        "A": {"type_line": "Instant"},
        "B": {"type_line": "Sorcery"},
    }

    r = client.get("/ready")
    assert r.status_code == 200
    available = r.json().get("available_methods", [])
    assert "fusion" in available
    assert "jaccard_faceted" in available


def test_cards_v1_pagination_invariants(client):
    from ..api import api as api_mod

    state = api_mod.get_state()
    state.embeddings = _DummyEmb(["A", "B", "C", "D", "E"])

    # Page 1
    r1 = client.get("/v1/cards", params={"limit": 2, "offset": 0})
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1["total"] == 5
    assert len(j1["items"]) == 2
    assert j1["next_offset"] == 2

    # Page 3 (tail)
    r2 = client.get("/v1/cards", params={"limit": 2, "offset": 4})
    assert r2.status_code == 200
    j2 = r2.json()
    assert len(j2["items"]) == 1
    assert j2["next_offset"] is None

    # Beyond total
    r3 = client.get("/v1/cards", params={"limit": 2, "offset": 10})
    assert r3.status_code == 200
    j3 = r3.json()
    assert j3["items"] == []
    assert j3["next_offset"] is None

    # Prefix filtering reduces total
    r4 = client.get("/v1/cards", params={"limit": 10, "offset": 0, "prefix": "A"})
    assert r4.status_code == 200
    j4 = r4.json()
    assert j4["total"] == 1
    assert j4["items"] == ["A"]

    # Property-like checks across a few offsets
    for off in (0, 1, 2, 3, 4, 5, 10):
        r = client.get("/v1/cards", params={"limit": 2, "offset": off})
        assert r.status_code == 200
        j = r.json()
        assert len(j["items"]) <= 2
        if j["next_offset"] is not None:
            assert j["next_offset"] >= off


def test_legacy_cards_endpoint_behavior(client):
    from ..api import api as api_mod

    state = api_mod.get_state()
    # Without embeddings => 503
    state.embeddings = None
    # If legacy endpoint not mounted, allow 404 and skip remaining assertions
    mounted_paths = {r.path for r in client.app.routes}
    r0 = client.get("/cards")
    if "/cards" not in mounted_paths:
        pytest.skip("legacy /cards endpoint not mounted in this build")
    assert r0.status_code == 503

    # With embeddings
    state.embeddings = _DummyEmb(["Alpha", "Beta", "Gamma"])
    r1 = client.get("/cards", params={"limit": 2})
    assert r1.status_code == 200
    assert len(r1.json()) == 2

    r2 = client.get("/cards", params={"prefix": "Ga"})
    assert r2.status_code == 200
    assert r2.json() == ["Gamma"]


def test_synergy_returns_404_when_query_missing(client):
    from ..api import api as api_mod

    state = api_mod.get_state()
    state.graph_data = {"adj": {"Bolt": {"A"}, "A": {"Bolt"}}}
    # embeddings not required for jaccard path
    r = client.get("/v1/cards/Unknown/similar", params={"mode": "synergy", "k": 5})
    assert r.status_code == 404
    assert "not in graph" in r.json().get("detail", "")


def test_ready_adopts_legacy_globals(client):
    # Set legacy globals after client creation to exercise adoption path
    from ..api import api as api_mod

    api_mod.embeddings = _DummyEmb(["A", "B"])  # legacy global
    api_mod.graph_data = None
    api_mod.model_info = {"methods": ["embedding"]}

    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json().get("status") == "ready"
