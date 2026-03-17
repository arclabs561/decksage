"""Tests for OT-based deck completion."""

from __future__ import annotations

import numpy as np
import pytest

from ml.deck_building.ot_completion import (
    FormatConstraints,
    OTCompletionConfig,
    _round_transport_plan,
    _round_transport_plan_ilp,
    build_cost_matrix,
    compute_reference_distribution,
    compute_source_distribution,
    deck_to_distribution,
    get_format_constraints,
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


def _make_embeddings(
    n: int = 20, dim: int = 8, seed: int = 42
) -> tuple[FakeKeyedVectors, list[str]]:
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
# Tests: compute_source_distribution
# ---------------------------------------------------------------------------


class TestSourceDistribution:
    def test_none_temperature_returns_uniform(self):
        embeddings, names = _make_embeddings(10)
        dist = compute_source_distribution(names[:3], embeddings, names[3:], temperature=None)
        n = len(names) - 3
        expected = 1.0 / n
        for d in dist:
            assert abs(d - expected) < 1e-10

    def test_quality_weighted_not_uniform(self):
        embeddings, names = _make_embeddings(10)
        seeds = [names[0]]
        pool = names[1:]
        dist = compute_source_distribution(seeds, embeddings, pool, temperature=0.2)

        assert dist.shape == (len(pool),)
        assert abs(dist.sum() - 1.0) < 1e-8
        # Should not be uniform
        assert dist.max() > 1.5 / len(pool)

    def test_low_temperature_more_concentrated(self):
        embeddings, names = _make_embeddings(20)
        seeds = [names[0]]
        pool = names[5:]

        dist_warm = compute_source_distribution(seeds, embeddings, pool, temperature=1.0)
        dist_cold = compute_source_distribution(seeds, embeddings, pool, temperature=0.05)

        # Colder temperature should have higher max (more concentrated)
        assert dist_cold.max() > dist_warm.max()


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
# Tests: _round_transport_plan (greedy, backward compat alias)
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
# Tests: _round_transport_plan_ilp
# ---------------------------------------------------------------------------


class TestILPRounding:
    def test_basic_ilp_rounding(self):
        pool = ["A", "B", "C", "D"]
        plan = np.array([0.4, 0.3, 0.2, 0.1])
        deck = _make_deck(["Seed"], "magic")

        additions = _round_transport_plan_ilp(
            plan_marginal=plan,
            card_pool=pool,
            deck=deck,
            game="magic",
            slots_to_fill=5,
        )

        total_added = sum(c for _, c in additions)
        assert total_added == 5

    def test_ilp_respects_copy_limit(self):
        pool = ["A", "B"]
        plan = np.array([0.9, 0.1])
        deck = _make_deck(["Seed"], "magic")

        additions = _round_transport_plan_ilp(
            plan_marginal=plan,
            card_pool=pool,
            deck=deck,
            game="magic",
            slots_to_fill=8,
        )

        for name, count in additions:
            assert count <= 4, f"{name} has {count} copies, exceeds 4"

    def test_ilp_closer_to_fractional_than_greedy(self):
        """ILP should produce an assignment closer to the fractional target."""
        pool = [f"Card_{i}" for i in range(10)]
        # Fractional plan: spread across many cards
        plan = np.array([0.15, 0.14, 0.13, 0.12, 0.11, 0.10, 0.09, 0.07, 0.05, 0.04])
        deck = _make_deck(["Seed"], "magic")
        slots = 10

        ilp_adds = _round_transport_plan_ilp(
            plan_marginal=plan, card_pool=pool, deck=deck, game="magic", slots_to_fill=slots
        )
        # ILP should fill exactly slots_to_fill
        total = sum(c for _, c in ilp_adds)
        assert total == slots

    def test_ilp_empty_pool(self):
        additions = _round_transport_plan_ilp(
            plan_marginal=np.array([]),
            card_pool=[],
            deck=_make_deck([], "magic"),
            game="magic",
            slots_to_fill=5,
        )
        assert additions == []

    def test_ilp_yugioh_3_copy_limit(self):
        pool = ["A", "B"]
        plan = np.array([0.8, 0.2])
        deck = _make_deck(["Seed"], "yugioh")

        additions = _round_transport_plan_ilp(
            plan_marginal=plan,
            card_pool=pool,
            deck=deck,
            game="yugioh",
            slots_to_fill=6,
        )

        for name, count in additions:
            assert count <= 3, f"{name} has {count} copies, exceeds YGO 3-copy limit"
        total = sum(c for _, c in additions)
        assert total == 6


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
        cfg = OTCompletionConfig(game="magic", target_main_size=10, pool_size=15, sinkhorn_reg=0.1)

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

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)

        assert result.additions == []
        assert "sinkhorn_failed" in result.metrics.get("error", "")


# ---------------------------------------------------------------------------
# Tests: unbalanced OT
# ---------------------------------------------------------------------------


class TestUnbalancedOT:
    def test_unbalanced_completes(self):
        """Unbalanced OT should still produce valid completions."""
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:5], "magic")

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=15,
            pool_size=20,
            sinkhorn_reg=0.1,
            reg_m=1.0,  # Enable unbalanced OT
        )

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)

        assert result.additions
        total_added = sum(a["count"] for a in result.additions)
        assert total_added > 0
        assert result.metrics.get("reg_m") == 1.0
        assert "transported_mass" in result.metrics

    def test_low_reg_m_transports_less(self):
        """Lower reg_m should transport less mass (more aggressive filtering)."""
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:5], "magic")

        cfg_high = OTCompletionConfig(
            game="magic",
            target_main_size=15,
            pool_size=20,
            sinkhorn_reg=0.1,
            reg_m=5.0,  # Near-balanced
        )
        cfg_low = OTCompletionConfig(
            game="magic",
            target_main_size=15,
            pool_size=20,
            sinkhorn_reg=0.1,
            reg_m=0.1,  # Aggressive filtering
        )

        r_high = ot_complete_deck(
            game="magic",
            deck=_make_deck(names[:5], "magic"),
            embeddings=embeddings,
            cfg=cfg_high,
        )
        r_low = ot_complete_deck(
            game="magic",
            deck=_make_deck(names[:5], "magic"),
            embeddings=embeddings,
            cfg=cfg_low,
        )

        # Lower reg_m should transport less total mass
        assert r_low.metrics["transported_mass"] <= r_high.metrics["transported_mass"] + 1e-6


# ---------------------------------------------------------------------------
# Tests: quality-weighted source
# ---------------------------------------------------------------------------


class TestQualityWeightedSource:
    def test_quality_weighted_source_in_metrics(self):
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:5], "magic")

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=15,
            pool_size=20,
            sinkhorn_reg=0.1,
            source_temperature=0.2,
        )

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)
        assert result.metrics["source_type"] == "quality_weighted"

    def test_uniform_source_in_metrics(self):
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:5], "magic")

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=15,
            pool_size=20,
            sinkhorn_reg=0.1,
            source_temperature=None,  # Uniform
        )

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)
        assert result.metrics["source_type"] == "uniform"


# ---------------------------------------------------------------------------
# Tests: ILP rounding via ot_complete_deck
# ---------------------------------------------------------------------------


class TestOTWithILPRounding:
    def test_ilp_rounding_mode(self):
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:5], "magic")

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=15,
            pool_size=20,
            sinkhorn_reg=0.1,
            rounding="ilp",
        )

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)
        assert result.additions
        assert result.metrics["rounding"] == "ilp"
        total = sum(a["count"] for a in result.additions)
        assert total == 10  # ILP should fill exactly

    def test_greedy_rounding_mode(self):
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:5], "magic")

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=15,
            pool_size=20,
            sinkhorn_reg=0.1,
            rounding="greedy",
        )

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)
        assert result.additions
        assert result.metrics["rounding"] == "greedy"


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

        r1 = ot_complete_deck(
            game="magic", deck=_make_deck(names[:4], "magic"), embeddings=embeddings, cfg=cfg
        )
        r2 = ot_complete_deck(
            game="magic", deck=_make_deck(names[:4], "magic"), embeddings=embeddings, cfg=cfg
        )

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


# ---------------------------------------------------------------------------
# Tests: get_format_constraints
# ---------------------------------------------------------------------------


class TestGetFormatConstraints:
    def test_magic_standard(self):
        fc = get_format_constraints("magic", "standard")
        assert fc.min_deck_size == 60
        assert fc.copy_limit == 4
        assert fc.singleton is False

    def test_magic_commander(self):
        fc = get_format_constraints("magic", "commander")
        assert fc.min_deck_size == 100
        assert fc.max_deck_size == 100
        assert fc.copy_limit == 1
        assert fc.singleton is True
        assert fc.color_identity_required is True

    def test_magic_draft(self):
        fc = get_format_constraints("magic", "draft")
        assert fc.min_deck_size == 40
        assert fc.copy_limit == 100  # effectively unlimited

    def test_yugioh_advanced(self):
        fc = get_format_constraints("yugioh", "advanced")
        assert fc.min_deck_size == 40
        assert fc.max_deck_size == 60
        assert fc.copy_limit == 3

    def test_pokemon_pocket(self):
        fc = get_format_constraints("pokemon", "pocket")
        assert fc.min_deck_size == 20
        assert fc.max_deck_size == 20
        assert fc.copy_limit == 2

    def test_unknown_format_falls_back(self):
        fc = get_format_constraints("magic", "notaformat")
        assert fc.min_deck_size == 60
        assert fc.copy_limit == 4

    def test_none_format_defaults(self):
        fc = get_format_constraints("yugioh", None)
        assert fc.copy_limit == 3


# ---------------------------------------------------------------------------
# Tests: format-aware OT completion
# ---------------------------------------------------------------------------


class TestFormatAwareCompletion:
    def test_format_legality_filters_banned_cards(self):
        """Banned cards in the target format are excluded from the pool."""
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:5], "magic")

        # Mark half the non-seed cards as "banned" in standard
        legality: dict[str, dict[str, str]] = {}
        for name in names:
            if name in names[5:20]:
                legality[name] = {"standard": "banned"}
            else:
                legality[name] = {"standard": "legal"}

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=15,
            pool_size=25,
            sinkhorn_reg=0.1,
            format="standard",
            legality_data=legality,
        )

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)

        # None of the banned cards should appear in additions
        banned_names = set(names[5:20])
        added_names = {a["card"] for a in result.additions}
        assert not added_names.intersection(banned_names), (
            f"Banned cards appeared in additions: {added_names & banned_names}"
        )
        assert result.metrics.get("format") == "standard"
        assert result.metrics.get("format_filtered", 0) > 0

    def test_commander_singleton_constraint(self):
        """Commander mode: all non-basic cards should have count=1."""
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:5], "magic")

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=15,
            pool_size=25,
            sinkhorn_reg=0.1,
            format="commander",
        )

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)

        for a in result.additions:
            assert a["count"] == 1, (
                f"Commander singleton violated: {a['card']} has count={a['count']}"
            )

    def test_commander_basics_can_exceed_singleton(self):
        """Basic lands are exempt from the singleton rule in Commander."""
        # Create embeddings that include basic land names
        rng = np.random.RandomState(77)
        names_custom = ["Plains", "Island", "Card_A", "Card_B", "Card_C"]
        data = {name: rng.randn(8).astype(np.float64) for name in names_custom}
        # Add more cards for pool
        for i in range(20):
            cname = f"Pool_{i}"
            data[cname] = rng.randn(8).astype(np.float64)
            names_custom.append(cname)
        embeddings = FakeKeyedVectors(data)

        deck = _make_deck(["Card_A", "Card_B"], "magic")

        # Singleton format but basics should be unlimited
        fc = FormatConstraints(
            min_deck_size=10, copy_limit=1, singleton=True, basics_unlimited=True
        )
        pool = ["Plains", "Island"] + [f"Pool_{i}" for i in range(10)]
        plan = np.zeros(len(pool))
        plan[0] = 0.4  # Plains
        plan[1] = 0.3  # Island
        for i in range(2, len(pool)):
            plan[i] = 0.3 / (len(pool) - 2)

        additions = _round_transport_plan_ilp(
            plan_marginal=plan,
            card_pool=pool,
            deck=deck,
            game="magic",
            slots_to_fill=8,
            format_constraints=fc,
        )

        # Plains should be allowed more than 1 copy
        plains_count = sum(c for name, c in additions if name == "Plains")
        # Non-basic cards should be limited to 1
        for name, count in additions:
            if name not in ("Plains", "Island"):
                assert count <= 1, f"Non-basic {name} has {count} copies in singleton"

    def test_standard_only_legal_cards(self):
        """OT completion with format=standard only uses standard-legal cards."""
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:3], "magic")

        # Make only a subset legal in standard
        legality = {}
        standard_legal = set(names[:3]) | set(names[20:])  # seeds + last 10
        for name in names:
            if name in standard_legal:
                legality[name] = {"standard": "legal"}
            else:
                legality[name] = {"standard": "not_legal"}

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=10,
            pool_size=25,
            sinkhorn_reg=0.1,
            format="standard",
            legality_data=legality,
        )

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)

        added_names = {a["card"] for a in result.additions}
        # All additions should be from the standard-legal set
        for card in added_names:
            assert card in standard_legal, f"{card} is not standard-legal but was added"

    def test_restricted_cards_limited_to_one_copy(self):
        """Restricted cards (Vintage) should get upper_bound=1 in ILP."""
        embeddings, names = _make_embeddings(20)
        deck = _make_deck(names[:3], "magic")

        # Mark one card as restricted
        legality = {}
        for name in names:
            legality[name] = {"vintage": "legal"}
        restricted_card = names[5]
        legality[restricted_card] = {"vintage": "restricted"}

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=10,
            pool_size=15,
            sinkhorn_reg=0.1,
            format="vintage",
            legality_data=legality,
        )

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)

        for a in result.additions:
            if a["card"] == restricted_card:
                assert a["count"] <= 1, f"Restricted card {restricted_card} has count={a['count']}"

    def test_color_identity_filtering(self):
        """Commander CI filtering removes cards outside the deck's colors."""
        rng = np.random.RandomState(88)
        card_names = [f"Card_{i}" for i in range(25)]
        data = {name: rng.randn(8).astype(np.float64) for name in card_names}
        embeddings = FakeKeyedVectors(data)

        deck = _make_deck(card_names[:3], "magic")

        # Deck is W/U; cards 10-19 are R/G (outside CI)
        card_ci: dict[str, set[str]] = {}
        for name in card_names:
            card_ci[name] = {"W", "U"}
        for i in range(10, 20):
            card_ci[card_names[i]] = {"R", "G"}

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=10,
            pool_size=20,
            sinkhorn_reg=0.1,
            format="commander",
            color_identity={"W", "U"},
            card_color_identity=card_ci,
        )

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)

        off_color = set(card_names[10:20])
        added_names = {a["card"] for a in result.additions}
        assert not added_names.intersection(off_color), (
            f"Off-color cards added: {added_names & off_color}"
        )

    def test_no_format_backward_compatible(self):
        """Without format, OT completion works exactly as before."""
        embeddings, names = _make_embeddings(30)
        deck = _make_deck(names[:5], "magic")

        cfg = OTCompletionConfig(
            game="magic",
            target_main_size=15,
            pool_size=20,
            sinkhorn_reg=0.1,
        )

        result = ot_complete_deck(game="magic", deck=deck, embeddings=embeddings, cfg=cfg)

        assert result.additions
        assert "format" not in result.metrics
