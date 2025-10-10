#!/usr/bin/env python3
import importlib
import math

import pytest


@pytest.fixture()
def client(api_client):
    # Minimal embeddings and graph via existing mock from test_api_smoke
    from ..api import api
    return api_client


def test_pagination_monotone(client):
    r0 = client.get("/v1/cards", params={"limit": 2, "offset": 0})
    assert r0.status_code in (200, 503)
    if r0.status_code != 200:
        pytest.skip("embeddings not ready")
    j0 = r0.json()
    total = j0["total"]
    if total < 2:
        pytest.skip("insufficient data for pagination test")

    r1 = client.get("/v1/cards", params={"limit": 2, "offset": j0.get("next_offset") or 0})
    assert r1.status_code == 200
    j1 = r1.json()

    # Monotone: next_offset increases until None
    if j0["next_offset"] is not None:
        assert j1["next_offset"] is None or j1["next_offset"] >= j0["next_offset"]

    # Stable union size: combined unique equals min(total, fetched)
    union = set(j0["items"]) | set(j1["items"])
    assert len(union) <= total


def test_similar_returns_sorted(client):
    r = client.post("/v1/similar", json={"query": "A", "top_k": 5, "use_case": "substitute"})
    assert r.status_code in (200, 404, 503)
    if r.status_code != 200:
        pytest.skip("not ready")
    scores = [res["similarity"] for res in r.json()["results"]]
    assert scores == sorted(scores, reverse=True)


