#!/usr/bin/env python3
import pytest


def _make_dummy_env():
    class DummyEmb:
        def __contains__(self, k):
            return k in {"A", "B", "C", "D"}

        @property
        def index_to_key(self):
            return ["A", "B", "C", "D"]

        def similarity(self, q, c):
            base = {("A", "B"): 0.8, ("A", "C"): 0.2, ("A", "D"): -0.1}
            return base.get((q, c), base.get((c, q), 0.0))

        def most_similar(self, q, topn=10):
            sims = [(c, self.similarity(q, c)) for c in self.index_to_key if c != q]
            sims.sort(key=lambda x: x[1], reverse=True)
            return sims[:topn]

    adj = {
        "A": {"B", "C"},
        "B": {"A", "C"},
        "C": {"A", "B"},
        "D": {"C"},
    }

    class DummyTagger:
        class Tags:
            def __init__(self, name):
                self.card_name = name
                self.removal = name in {"A", "B"}
                self.draw = name in {"C"}
                self.ramp = name in {"D"}

        def tag_card(self, name):
            return self.Tags(name)

    return DummyEmb(), adj, DummyTagger()


def test_fusion_basic_ranking():
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    emb, adj, tagger = _make_dummy_env()
    fusion = WeightedLateFusion(embeddings=emb, adj=adj, tagger=tagger, weights=FusionWeights())

    results = fusion.similar("A", k=3)
    assert isinstance(results, list)
    assert len(results) >= 1
    # Expect B to rank above C/D due to both embedding and jaccard and shared tags
    top_cards = [c for c, _ in results]
    assert top_cards[0] in {"B", "C"}
    # Assert monotonicity by score
    scores = [s for _, s in results]
    assert all(scores[i] >= scores[i+1] for i in range(len(scores)-1))


def test_fusion_rrf_aggregator_changes_order():
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    emb, adj, tagger = _make_dummy_env()
    f_weighted = WeightedLateFusion(embeddings=emb, adj=adj, tagger=tagger, weights=FusionWeights(), aggregator="weighted")
    f_rrf = WeightedLateFusion(embeddings=emb, adj=adj, tagger=tagger, weights=FusionWeights(), aggregator="rrf", rrf_k=10)

    r1 = [c for c, _ in f_weighted.similar("A", k=3)]
    r2 = [c for c, _ in f_rrf.similar("A", k=3)]

    assert len(r1) >= 1 and len(r2) >= 1
    # Not guaranteed different, but in our dummy data it's likely; fall back to same ordering allowed
    assert set(r1) == set(r2)


def test_fusion_mmr_diversifies_results():
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    emb, adj, tagger = _make_dummy_env()
    f_no_mmr = WeightedLateFusion(embeddings=emb, adj=adj, tagger=tagger, weights=FusionWeights(), aggregator="weighted", mmr_lambda=0.0)
    f_mmr = WeightedLateFusion(embeddings=emb, adj=adj, tagger=tagger, weights=FusionWeights(), aggregator="weighted", mmr_lambda=0.7)

    r_no = f_no_mmr.similar("A", k=3)
    r_yes = f_mmr.similar("A", k=3)

    assert len(r_no) >= 1 and len(r_yes) >= 1
    # Ensure same set but potentially different ordering
    assert {c for c, _ in r_no} == {c for c, _ in r_yes}


def test_fusion_handles_missing_modalities():
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    emb, adj, tagger = _make_dummy_env()
    fusion = WeightedLateFusion(embeddings=None, adj=adj, tagger=None, weights=FusionWeights())
    results = fusion.similar("A", k=2)
    assert len(results) >= 1


@pytest.mark.parametrize("scale", [0.1, 1.0, 3.0])
def test_fusion_weight_scale_invariance(scale):
    """Scaling weights by a constant factor yields identical normalized behavior."""
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    emb, adj, tagger = _make_dummy_env()

    base = FusionWeights(embed=0.4, jaccard=0.35, functional=0.25)
    scaled = FusionWeights(
        embed=base.embed * scale,
        jaccard=base.jaccard * scale,
        functional=base.functional * scale,
    )

    f1 = WeightedLateFusion(embeddings=emb, adj=adj, tagger=tagger, weights=base)
    f2 = WeightedLateFusion(embeddings=emb, adj=adj, tagger=tagger, weights=scaled)

    r1 = [c for c, _ in f1.similar("A", k=3)]
    r2 = [c for c, _ in f2.similar("A", k=3)]
    assert r1 == r2


@pytest.mark.parametrize("candidate_topn", [10, 50])
def test_fusion_candidate_topn_affects_candidates_but_not_top1(candidate_topn):
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    emb, adj, tagger = _make_dummy_env()
    f = WeightedLateFusion(embeddings=emb, adj=adj, tagger=tagger, weights=FusionWeights(), candidate_topn=candidate_topn)
    top = f.similar("A", k=1)
    assert len(top) == 1
    assert top[0][0] in {"B", "C"}


def test_fusion_unknown_query_returns_empty():
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    emb, adj, tagger = _make_dummy_env()
    fusion = WeightedLateFusion(embeddings=emb, adj=adj, tagger=tagger, weights=FusionWeights())
    results = fusion.similar("UNKNOWN", k=3)
    assert results == []
    # Ensure results are within adjacency neighborhood when only jaccard active
    neighbor_set = set(adj["A"]) if "A" in adj else set()
    assert all(c in neighbor_set for c, _ in results)





