"""Tests for OT-based deck completion."""

from __future__ import annotations

import numpy as np
import pytest

from ml.deck_building.ot_completion import (
    OTCompletionConfig,
    _round_transport_plan,
    build_cost_matrix,
    compute_reference_distribution,
    deck_to_distribution,
    ot_complete_deck,
)


# ---------------------------------------------------------------------------
# Helpers: fake KeyedVectors-like object for testing without gensim
# ---------------------------------------------------------------------------


class FakeKeyedVectors:
    """Minimal mock of gensim.models.KeyedVectors for testing."""

    def __init__(self, data: dict[str, np.ndarray]):
        self._data = data
        self.vector_size = next(iter(data.values())).shape[0] if data else 8

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> np.ndarray:
        return self._data[key]

    def most_similar(self, key: str, topn: int = 10) -> list[tuple[str, float]]:
        if key not in self._data:
            raise KeyError(key)
        vec = self._data[key]
        norm = np.linalg.norm(vec)
        if norm == 0:
            return []
        vec = vec / norm
        results = []
        for name, other in self._data.items():
            if name == key:
                continue
            other_norm = np.linalg.norm(other)
            if other_norm == 0:
                continue
            sim = float(vec @ (other / other_norm))
            results.append((name, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:topn]


def _make_embeddings(n: int = 20, dim: int = 8, seed: int = 42) -> tuple[FakeKeyedVectors, list[str]]:
    """Create fake embeddings for n cards."""
    rng = np.random.RandomState(seed)
    names = [f"Card_{i}" for i in range(n)]
    data = {name: rng.randn(dim).astype(np.float64) for name in names}
    return FakeKeyedVectors(data), names


def _make_deck(card_names: list[str], game: str = "magic") -> dict:
    """Create a deck in partitions format."""
    part_name = "Main" if game == "magic" else "Main Deck"
    cards = [{"name": name, "count": 1} for name in card_names]
    return {"partitions": [{"name": part_name, "cards": cards}]}


# ---------------------------------------------------------------------------
# Tests: deck_to_distribution
# ---------------------------------------------------------------------------


class TestDeckToDistribution:
    def test_basic(self):
        deck = _make_deck(["Card_0", "Card_1", "Card_2"])
        pool = [f"Card_{i}" for i in range(5)]
        dist = deck_to_distribution(deck, "magic", pool)

        assert dist.shape == (5,)
        assert abs(dist.sum() - 1.0) < 1e-10
        # Cards 0,1,2 should have equal mass
        assert abs(dist[0] - dist[1]) < 1e-10
        assert abs(dist[1] - dist[2]) < 1e-10
        # Cards 3,4 should have zero mass
        assert dist[3] == 0.0
        assert dist[4] == 0.0

    def test_empty_deck(self):
        deck = _make_deck([])
        pool = ["A", "B", "C"]
        dist = deck_to_distribution(deck, "magic", pool)
        # Should be uniform
        assert abs(dist.sum() - 1.0) < 1e-10
        assert abs(dist[0] - 1.0 / 3) < 1e-10

    def test_weighted_counts(self):
        deck = {
            "partitions": [
                {
                    "name": "Main",
                    "cards": [
                        {"name": "A", "count": 3},
                        {"name": "B", "count": 1},
                    ],
                }
            ]
        }
        pool = ["A", "B", "C"]
        dist = deck_to_distribution(deck, "magic", pool)
        assert abs(dist[0] - 0.75) < 1e-10  # A: 3/4
        assert abs(dist[1] - 0.25) < 1e-10  # B: 1/4
        assert dist[2] == 0.0


# ---------------------------------------------------------------------------
# Tests: compute_reference_distribution
# ---------------------------------------------------------------------------


class TestReferenceDistribution:
    def test_concentrates_on_similar(self):
        embeddings, names = _make_embeddings(10)
        seeds = [names[0]]
        pool = names[1:]  # Exclude seed

        dist = compute_reference_distribution(seeds, embeddings, pool, temperature=0.1)

        assert dist.shape == (len(pool),)
        assert abs(dist.sum() - 1.0) < 1e-8
        # Distribution should not be uniform (concentrated on similar cards)
        assert dist.max() > 1.0 / len(pool)

    def test_no_seeds_returns_uniform(self):
        embeddings, names = _make_embeddings(5)
        dist = compute_reference_distribution([], embeddings, names)
        expected = 1.0 / len(names)
        for d in dist:
            assert abs(d - expected) < 1e-10

    def test_no_embeddings_returns_uniform(self):
        dist = compute_reference_distribution(["X"], None, ["A", "B", "C"])
        assert abs(dist.sum() - 1.0) < 1e-10
        assert abs(dist[0] - 1.0 / 3) < 1e-10


# ---------------------------------------------------------------------------
# Tests: build_cost_matrix
# ---------------------------------------------------------------------------


class TestBuildCostMatrix:
    def test_shape(self):
        embeddings, names = _make_embeddings(10)
        costs = build_cost_matrix(
            card_pool=names,
            embeddings=embeddings,
            seed_cards=names[:3],
        )
        assert costs.shape == (10,)

    def test_seed_cards_have_lower_cost(self):
        embeddings, names = _make_embeddings(10)
        # Cards similar to seeds should have lower embedding cost
        costs = build_cost_matrix(
            card_pool=names,
            embeddings=embeddings,
            seed_cards=[names[0]],
            embedding_weight=1.0,
            role_weight=0.0,
            curve_weight=0.0,
        )
        # The seed itself should have very low cost (self-similarity ~= 1)
        seed_idx = names.index(names[0])
        assert costs[seed_idx] < 0.1

    def test_role_gaps_reduce_cost(self):
        embeddings, names = _make_embeddings(5)

        def tag_fn(name: str) -> set[str]:
            if name == names[0]:
                return {"removal"}
            return set()

        costs = build_cost_matrix(
            card_pool=names,
            embeddings=embeddings,
            seed_cards=[names[1]],
            tag_set_fn=tag_fn,
            role_gaps={"removal": 5},
            embedding_weight=0.0,
            role_weight=1.0,
            curve_weight=0.0,
        )
        # Card_0 (has removal tag) should have lower role cost than Card_1 (no tag)
        assert costs[0] < costs[1]


# ---------------------------------------------------------------------------
# Tests: _round_transport_plan
# ---------------------------------------------------------------------------


class TestRoundTransportPlan:
    def test_basic_rounding(self):
        pool = ["A", "B", "C"]
        plan = np.array([0.5, 0.3, 0.2])
        deck = _make_deck(["Seed"], "magic")

        additions = _round_transport_plan(
            plan_marginal=plan,
            card_pool=pool,
            deck=deck,
            game="magic",
            slots_to_fill=5,
        )

        total_added = sum(c for _, c in additions)
        assert total_added <= 5
        assert total_added > 0
        # A should be first (highest mass)
        assert additions[0][0] == "A"

    def test_respects_copy_limit(self):
        pool = ["A"]
        plan = np.array([1.0])
        deck = _make_deck(["Seed"], "magic")

        additions = _round_transport_plan(
            plan_marginal=plan,
            card_pool=pool,
            deck=deck,
            game="magic",
            slots_to_fill=10,  # More than copy limit
        )

        # Magic allows 4 copies
        total = sum(c for _, c in additions)
        assert total <= 4

    def test_zero_mass_skipped(self):
        pool = ["A", "B"]
        plan = np.array([0.8, 0.0])
        deck = _make_deck([], "magic")

        additions = _round_transport_plan(
            plan_marginal=plan,
            card_pool=pool,
            deck=deck,
            game="magic",
            slots_to_fill=3,
        )

        card_names = [name for name, _ in additions]
        assert "B" not in card_names


# ---------------------------------------------------------------------------
# Tests: ot_complete_deck (integration)
# ---------------------------------------------------------------------------


class TestOTCompleteDeck:
    def test_basic_completion(self):
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:5], "magic")

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=15,  # Small for test speed
            pool_size=20,
            sinkhorn_reg=0.1,  # Higher reg for faster convergence
        )

        result = ot_complete_deck(
            game="magic",
            deck=deck,
            embeddings=embeddings,
            cfg=cfg,
        )

        assert result.additions  # Should have added cards
        total_added = sum(a["count"] for a in result.additions)
        assert total_added > 0
        assert total_added <= 10  # 15 - 5 = 10 slots
        assert result.metrics["slots_to_fill"] == 10

    def test_already_full(self):
        embeddings, names = _make_embeddings(10)
        deck = _make_deck(names[:5], "magic")

        cfg = OTCompletionConfig(game="magic", target_main_size=5)
        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)

        assert result.additions == []
        assert result.metrics["slots_to_fill"] == 0

    def test_with_role_gaps(self):
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:3], "magic")

        def tag_fn(name: str) -> set[str]:
            # Give some cards the "removal" tag
            if name in names[10:15]:
                return {"removal"}
            return set()

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=10,
            pool_size=25,
            sinkhorn_reg=0.1,
        )

        result = ot_complete_deck(
            game="magic",
            deck=deck,
            embeddings=embeddings,
            cfg=cfg,
            tag_set_fn=tag_fn,
            role_gaps={"removal": 5},
        )

        assert result.additions
        assert result.metrics["cards_added"] > 0

    def test_yugioh_copy_limit(self):
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:5], "yugioh")

        cfg = OTCompletionConfig(
            game="yugioh",
            target_main_size=40,
            pool_size=25,
            sinkhorn_reg=0.1,
        )

        result = ot_complete_deck(game="yugioh", deck=deck, embeddings=embeddings, cfg=cfg)

        # Verify no card exceeds 3 copies (YGO rule)
        for a in result.additions:
            assert a["count"] <= 3, f"{a['card']} has {a['count']} copies"

    def test_pot_not_installed_error(self, monkeypatch):
        """Verify graceful error when POT is not installed."""
        import ml.deck_building.ot_completion as mod

        monkeypatch.setattr(mod, "pot", None)
        embeddings, names = _make_embeddings(10)
        deck = _make_deck(names[:3], "magic")
        cfg = OTCompletionConfig(game="magic", target_main_size=10)

        with pytest.raises(ImportError, match="POT library required"):
            ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)

    def test_empty_candidate_pool(self):
        """Empty candidate pool returns error metric, not crash."""
        # Use embeddings with only the seed cards -- no candidates available
        rng = np.random.RandomState(99)
        data = {f"Seed_{i}": rng.randn(8) for i in range(5)}
        embeddings = FakeKeyedVectors(data)
        deck = _make_deck([f"Seed_{i}" for i in range(5)], "magic")

        # candidate_fn that returns nothing
        def empty_candidate_fn(card: str, top_k: int) -> list[tuple[str, float]]:
            return []

        cfg = OTCompletionConfig(game="magic", target_main_size=15, pool_size=20)
        result = ot_complete_deck(
            game="magic",
            deck=deck,
            embeddings=embeddings,
            cfg=cfg,
            candidate_fn=empty_candidate_fn,
        )

        assert result.additions == []
        assert result.metrics.get("error") == "empty_candidate_pool"

    def test_sinkhorn_failure_returns_error(self, monkeypatch):
        """Sinkhorn solver exception returns error metric, not crash."""
        import ml.deck_building.ot_completion as mod

        embeddings, names = _make_embeddings(20)
        deck = _make_deck(names[:3], "magic")
        cfg = OTCompletionConfig(
            game="magic", target_main_size=10, pool_size=15, sinkhorn_reg=0.1
        )

        # Make pot.sinkhorn raise an exception
        real_pot = mod.pot

        class FakePot:
            def __getattr__(self, name):
                if name == "sinkhorn":
                    def fail(*args, **kwargs):
                        raise RuntimeError("Solver diverged")
                    return fail
                return getattr(real_pot, name)

        monkeypatch.setattr(mod, "pot", FakePot())

        result = ot_complete_deck(
            game="magic", deck=deck, embeddings=embeddings, cfg=cfg
        )

        assert result.additions == []
        assert "sinkhorn_failed" in result.metrics.get("error", "")


# ---------------------------------------------------------------------------
# Tests: idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_same_input_same_output(self):
        """OT completion with same inputs produces same results (deterministic)."""
        embeddings, names = _make_embeddings(20, seed=123)
        deck = _make_deck(names[:4], "magic")

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=10,
            pool_size=15,
            sinkhorn_reg=0.1,
        )

        r1 = ot_complete_deck(game="magic", deck=_make_deck(names[:4], "magic"), embeddings=embeddings, cfg=cfg)
        r2 = ot_complete_deck(game="magic", deck=_make_deck(names[:4], "magic"), embeddings=embeddings, cfg=cfg)

        # Same additions
        names1 = [(a["card"], a["count"]) for a in r1.additions]
        names2 = [(a["card"], a["count"]) for a in r2.additions]
        assert names1 == names2

    def test_rerun_on_completed_deck_is_noop(self):
        """Running OT on an already-completed deck adds nothing."""
        embeddings, names = _make_embeddings(20)
        deck = _make_deck(names[:4], "magic")

        cfg = OTCompletionConfig(game="magic", target_main_size=8, pool_size=15, sinkhorn_reg=0.1)
        r1 = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)

        # Now run again on the completed deck
        cfg2 = OTCompletionConfig(game="magic", target_main_size=8, pool_size=15, sinkhorn_reg=0.1)
        r2 = ot_complete_deck(game="magic", deck=r1.deck, embeddings=embeddings, cfg=cfg2)

        assert r2.additions == []
        assert r2.metrics["slots_to_fill"] == 0
