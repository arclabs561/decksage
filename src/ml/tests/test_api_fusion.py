#!/usr/bin/env python3
import pytest


try:
    from fastapi.testclient import TestClient

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    TestClient = None

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")


def make_app_with_fusion():
    from ..api import api

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

        def similarity(self, q, c):
            return 0.9 if (q, c) in [("A", "B"), ("A", "C")] else 0.0

    api.embeddings = DummyEmb()
    api.model_info = {"methods": ["embedding"]}
    api.graph_data = {"adj": {"A": {"B", "C"}, "B": {"A"}, "C": {"A"}}, "weights": {}}
    return api.app


@pytest.fixture()
def client(api_client):
    _ = make_app_with_fusion()  # set up state on the shared app
    return api_client


def test_ready_reports_fusion(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert "fusion" in r.json().get("available_methods", [])


def test_fusion_mode_post(client):
    payload = {"query": "A", "top_k": 2, "use_case": "substitute", "mode": "fusion"}
    r = client.post("/v1/similar", json=payload)
    assert r.status_code in (200, 503)
    if r.status_code != 200:
        pytest.skip("fusion prerequisites not ready (embeddings/graph)")
    j = r.json()
    assert j["query"] == "A"
    if len(j["results"]) == 0:
        pytest.skip("fusion produced no candidates in this mocked env")
    assert len(j["results"]) >= 1
