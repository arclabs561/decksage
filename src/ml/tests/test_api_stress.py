import threading

from fastapi.testclient import TestClient

from ..api import api


class DummyEmb:
    def __len__(self):
        return len(self.index_to_key)

    def __contains__(self, k):
        return k in {"Lightning Bolt", "Lava Spike", "Rift Bolt", "Boros Charm"}

    @property
    def index_to_key(self):
        return ["Lightning Bolt", "Lava Spike", "Rift Bolt", "Boros Charm"]

    @property
    def vector_size(self):
        return 3

    def most_similar(self, q, topn=10):
        cands = [("Lava Spike", 0.9), ("Rift Bolt", 0.85), ("Boros Charm", 0.8)]
        return [(c, s) for c, s in cands if c != q][:topn]


def setup_dummy_state():
    api.embeddings = DummyEmb()
    api.model_info = {"methods": ["embedding"]}
    api.graph_data = {
        "adj": {"Lightning Bolt": {"Lava Spike", "Rift Bolt"}},
        "weights": {},
    }
    api.get_state().card_attrs = {
        "lightning bolt": {"cmc": 1, "type": "Instant"},
        "lava spike": {"cmc": 1, "type": "Sorcery"},
        "rift bolt": {"cmc": 3, "type": "Sorcery"},
        "boros charm": {"cmc": 2, "type": "Instant"},
    }


def test_api_stress_suggest_and_complete():
    setup_dummy_state()
    client = TestClient(api.app)

    deck = {
        "deck_id": "ex",
        "format": "Modern",
        "partitions": [{"name": "Main", "cards": [{"name": "Lightning Bolt", "count": 4}]}],
    }

    results = []

    def worker(i: int):
        sug_body = {
            "game": "magic",
            "deck": deck,
            "top_k": 5,
            "coverage_weight": 0.2,
            "curve_weight": 0.1,
            "curve_target": {1: 0.6, 2: 0.2, 3: 0.2},
        }
        r = client.post("/v1/deck/suggest_actions", json=sug_body)
        assert r.status_code == 200
        j = r.json()
        assert "actions" in j and "metrics" in j
        comp_body = {
            "game": "magic",
            "deck": deck,
            "target_main_size": 6,
            "coverage_weight": 0.2,
        }
        r2 = client.post("/v1/deck/complete", json=comp_body)
        assert r2.status_code == 200
        results.append((j["metrics"], r2.json()["metrics"]))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Simple sanity on metrics
    assert len(results) == 8
    for sug_m, comp_m in results:
        assert "elapsed_ms" in sug_m and "elapsed_ms" in comp_m
