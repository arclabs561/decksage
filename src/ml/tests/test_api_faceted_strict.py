from fastapi.testclient import TestClient
from importlib import import_module
from ..api import api


def setup_state():
    class D:
        def __len__(self): return len(self.index_to_key)
        def __contains__(self,k): return k in {'Lightning Bolt','Lava Spike'}
        @property
        def index_to_key(self): return ['Lightning Bolt','Lava Spike']
        @property
        def vector_size(self): return 3
        def most_similar(self, q, topn=10): return [('Lava Spike',0.9)]
    st = api.get_state()
    st.embeddings = D()
    st.model_info = {'methods':['embedding','jaccard','fusion']}
    st.graph_data = {'adj': {'Lightning Bolt': {'Lava Spike'}}, 'weights': {}}
    st.card_attrs = {'lightning bolt': {'cmc':1}, 'lava spike':{'cmc':1}}


def test_strict_size_enforced():
    setup_state()
    client = TestClient(api.app)
    deck={'deck_id':'ex','format':'Modern','partitions':[{'name':'Main','cards':[]}]}  # empty main deck
    body={'game':'magic','deck':deck,'patch':{'ops':[{'op':'add_card','partition':'Main','card':'Lava Spike','count':1}]}, 'strict_size': True}
    r = client.post('/v1/deck/apply_patch', json=body)
    assert r.status_code == 200
    j = r.json()
    assert j['is_valid'] is False
    assert any('requires at least' in e for e in j['errors'])


def test_faceted_routing():
    setup_state()
    client = TestClient(api.app)
    # The dynamic import and try/except was logically flawed.
    # The scorer is expected to be available in the test environment.
    # This test now correctly verifies the success path.
    r = client.post(
        "/v1/similar",
        json={
            "query": "Lightning Bolt",
            "top_k": 1,
            "use_case": "synergy",
            "mode": "jaccard_faceted",
            "facet": "cmc",
        },
    )
    # With attrs present and scorer available, faceted should be 200
    assert r.status_code == 200
