import sys

import pytest
from fastapi.testclient import TestClient

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
        # Embedding prefers B over C
        return [("B", 0.9), ("C", 0.2)]

    def similarity(self, q, c):
        if (q, c) == ("A", "B"):
            return 0.9
        if (q, c) == ("A", "C"):
            return 0.2
        return 0.0


def setup_state_for_fusion():
    api.embeddings = DummyEmb()
    api.model_info = {"methods": ["embedding", "jaccard", "fusion"]}
    # Jaccard prefers C over B: N(A)={B,C}, N(C)={A,B}, N(B)={}
    api.graph_data = {"adj": {"A": {"B", "C"}, "C": {"A", "B"}, "B": set()}}
    # Force update into FastAPI state
    st = api.get_state()
    st.embeddings = api.embeddings
    st.graph_data = api.graph_data


@pytest.mark.skipif("fastapi" not in sys.modules, reason="fastapi not installed")
def test_fusion_weight_effect():
    setup_state_for_fusion()
    client = TestClient(api.app)

    # Fusion with more weight on embedding -> B should rank higher
    r = client.post(
        "/v1/similar",
        json={
            "query": "A",
            "top_k": 2,
            "use_case": "substitute",
            "mode": "fusion",
            "weights": {"embed": 0.8, "jaccard": 0.2, "functional": 0.0},
        },
    )
    assert r.status_code == 200
    res1_items = r.json()["results"]
    res1 = [x["card"] for x in res1_items]
    assert res1, "Fusion result should not be empty"

    # Fusion with more weight on jaccard -> C should rank higher
    r = client.post(
        "/v1/similar",
        json={
            "query": "A",
            "top_k": 2,
            "use_case": "substitute",
            "mode": "fusion",
            "weights": {"embed": 0.2, "jaccard": 0.8, "functional": 0.0},
        },
    )
    assert r.status_code == 200
    res2_items = r.json()["results"]
    res2 = [x["card"] for x in res2_items]
    assert res2, "Fusion result should not be empty"

    # Compare relative ordering of B and C rather than only the top item
    def rank(lst, item):
        return next((i for i, x in enumerate(lst) if x == item), 999)

    r1B, r1C = rank(res1, "B"), rank(res1, "C")
    r2B, r2C = rank(res2, "B"), rank(res2, "C")
    assert r1B < r1C, f"Embedding-heavy should rank B over C: {res1}"
    assert r2C < r2B, f"Jaccard-heavy should rank C over B: {res2}"
