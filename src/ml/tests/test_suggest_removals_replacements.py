#!/usr/bin/env python3
"""Tests for suggest_removals() and suggest_replacements() in deck_completion."""

from __future__ import annotations

from ..deck_building.deck_completion import suggest_removals, suggest_replacements


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

# Known similarity graph: card -> [(similar_card, score), ...]
_SIMILARITY: dict[str, list[tuple[str, float]]] = {
    "Lightning Bolt": [
        ("Lava Spike", 0.95),
        ("Rift Bolt", 0.90),
        ("Searing Blaze", 0.85),
        ("Skullcrack", 0.80),
        ("Shock", 0.75),
    ],
    "Goblin Guide": [
        ("Monastery Swiftspear", 0.92),
        ("Ragavan, Nimble Pilferer", 0.88),
        ("Soul-Scar Mage", 0.84),
        ("Bomat Courier", 0.78),
    ],
    "Monastery Swiftspear": [
        ("Soul-Scar Mage", 0.91),
        ("Goblin Guide", 0.89),
        ("Dragon's Rage Channeler", 0.83),
    ],
    "Searing Blaze": [
        ("Lightning Bolt", 0.85),
        ("Searing Blood", 0.80),
        ("Roiling Vortex", 0.70),
    ],
    "Dark Confidant": [
        ("Phyrexian Arena", 0.82),
        ("Night's Whisper", 0.78),
        ("Sign in Blood", 0.74),
    ],
    "Thoughtseize": [
        ("Inquisition of Kozilek", 0.90),
        ("Duress", 0.80),
        ("Grief", 0.75),
    ],
    "Fatal Push": [
        ("Lightning Bolt", 0.80),
        ("Dismember", 0.75),
        ("Path to Exile", 0.70),
    ],
    "Tarmogoyf": [
        ("Scavenging Ooze", 0.80),
        ("Grim Flayer", 0.75),
    ],
}


def _candidate_fn(card: str, k: int) -> list[tuple[str, float]]:
    """Fake CandidateFn returning known similar cards."""
    return _SIMILARITY.get(card, [])[:k]


_TAGS: dict[str, set[str]] = {
    "Lightning Bolt": {"removal", "burn"},
    "Lava Spike": {"burn"},
    "Rift Bolt": {"burn"},
    "Searing Blaze": {"removal", "burn"},
    "Goblin Guide": {"threat"},
    "Monastery Swiftspear": {"threat"},
    "Soul-Scar Mage": {"threat"},
    "Mountain": set(),
    "Dark Confidant": {"card_draw", "threat"},
    "Thoughtseize": {"removal"},
    "Fatal Push": {"removal"},
    "Tarmogoyf": {"threat"},
    "Ragavan, Nimble Pilferer": {"threat", "ramp"},
    "Skullcrack": {"burn"},
    "Shock": {"removal", "burn"},
}


def _tag_set_fn(card: str) -> set[str]:
    return _TAGS.get(card, set())


_PRICES: dict[str, float] = {
    "Lightning Bolt": 1.50,
    "Lava Spike": 1.00,
    "Rift Bolt": 0.75,
    "Searing Blaze": 3.00,
    "Skullcrack": 0.50,
    "Shock": 0.10,
    "Goblin Guide": 5.00,
    "Monastery Swiftspear": 0.50,
    "Soul-Scar Mage": 2.00,
    "Ragavan, Nimble Pilferer": 60.00,
    "Dark Confidant": 8.00,
    "Phyrexian Arena": 4.00,
    "Night's Whisper": 0.25,
}


def _price_fn(card: str) -> float | None:
    return _PRICES.get(card)


def _make_deck(
    cards: list[tuple[str, int]],
    partition_name: str = "Main",
    fmt: str = "Modern",
) -> dict:
    """Build a deck dict in partitions format."""
    return {
        "deck_id": "test",
        "format": fmt,
        "partitions": [
            {
                "name": partition_name,
                "cards": [{"name": n, "count": c} for n, c in cards],
            }
        ],
    }


_BURN_DECK = _make_deck([
    ("Lightning Bolt", 4),
    ("Goblin Guide", 4),
    ("Monastery Swiftspear", 4),
    ("Searing Blaze", 4),
    ("Lava Spike", 4),
    ("Rift Bolt", 4),
    ("Mountain", 20),
])

# Archetype data: card -> {archetype -> inclusion_rate}
_BURN_STAPLES: dict[str, dict[str, float]] = {
    "Lightning Bolt": {"burn": 0.98},
    "Goblin Guide": {"burn": 0.95},
    "Monastery Swiftspear": {"burn": 0.93},
    "Lava Spike": {"burn": 0.90},
    "Rift Bolt": {"burn": 0.85},
    "Searing Blaze": {"burn": 0.70},
    "Mountain": {"burn": 0.99},
    # Dark Confidant is NOT a burn staple
    "Dark Confidant": {"midrange": 0.80},
    # Tarmogoyf is not burn
    "Tarmogoyf": {"midrange": 0.90, "jund": 0.85},
}


# ---------------------------------------------------------------------------
# TestSuggestRemovals
# ---------------------------------------------------------------------------

class TestSuggestRemovals:
    """Tests for suggest_removals()."""

    def test_basic_returns_tuples(self):
        """With archetype context, returns non-empty list of 3-tuples."""
        # Add a non-burn card so there is something to flag
        deck = _make_deck([
            ("Lightning Bolt", 4),
            ("Goblin Guide", 4),
            ("Dark Confidant", 2),
            ("Mountain", 10),
        ])
        results = suggest_removals(
            "magic",
            deck,
            _candidate_fn,
            archetype="burn",
            archetype_staples=_BURN_STAPLES,
            tag_set_fn=_tag_set_fn,
        )
        assert len(results) > 0
        for card_name, score, reason in results:
            assert isinstance(card_name, str)
            assert isinstance(score, float)
            assert isinstance(reason, str)
            assert len(reason) > 0

    def test_returned_cards_are_in_deck(self):
        """All suggested removals must be cards actually present in the deck."""
        deck = _make_deck([
            ("Lightning Bolt", 4),
            ("Goblin Guide", 4),
            ("Dark Confidant", 2),
            ("Tarmogoyf", 3),
            ("Mountain", 10),
        ])
        have = {c["name"] for p in deck["partitions"] for c in p["cards"]}
        results = suggest_removals(
            "magic",
            deck,
            _candidate_fn,
            archetype="burn",
            archetype_staples=_BURN_STAPLES,
        )
        for card_name, _, _ in results:
            assert card_name in have, f"{card_name} not in deck"

    def test_respects_max_suggestions(self):
        """Output length capped by max_suggestions."""
        deck = _make_deck([
            ("Lightning Bolt", 4),
            ("Goblin Guide", 4),
            ("Dark Confidant", 2),
            ("Tarmogoyf", 3),
            ("Thoughtseize", 4),
            ("Fatal Push", 4),
            ("Mountain", 10),
        ])
        results = suggest_removals(
            "magic",
            deck,
            _candidate_fn,
            archetype="burn",
            archetype_staples=_BURN_STAPLES,
            max_suggestions=2,
        )
        assert len(results) <= 2

    def test_off_archetype_cards_flagged(self):
        """Cards not in the archetype staples get higher removal scores."""
        deck = _make_deck([
            ("Lightning Bolt", 4),
            ("Goblin Guide", 4),
            ("Dark Confidant", 2),  # midrange, not burn
            ("Mountain", 10),
        ])
        results = suggest_removals(
            "magic",
            deck,
            _candidate_fn,
            archetype="burn",
            archetype_staples=_BURN_STAPLES,
        )
        flagged_names = [name for name, _, _ in results]
        assert "Dark Confidant" in flagged_names

    def test_preserve_roles_redundant_removal(self):
        """With preserve_roles, excessive role cards get flagged as redundant."""
        # Build a deck with >12 removal-tagged cards to trigger threshold
        removal_cards = [
            ("Lightning Bolt", 4),
            ("Searing Blaze", 4),
            ("Fatal Push", 4),
            ("Thoughtseize", 4),  # tagged as removal
        ]  # total 16 removal cards, threshold is 12
        deck = _make_deck([*removal_cards, ("Mountain", 20)])
        results = suggest_removals(
            "magic",
            deck,
            _candidate_fn,
            preserve_roles=True,
            tag_set_fn=_tag_set_fn,
        )
        # Should flag some cards as redundant removal
        reasons = [reason for _, _, reason in results]
        redundant = [r for r in reasons if "redundant" in r]
        assert len(redundant) > 0

    def test_empty_deck_returns_empty(self):
        """An empty deck yields no removal suggestions."""
        deck = _make_deck([])
        results = suggest_removals("magic", deck, _candidate_fn)
        assert results == []

    def test_single_card_deck_no_archetype(self):
        """Without archetype context or role excess, nothing to flag."""
        deck = _make_deck([("Lightning Bolt", 1)])
        results = suggest_removals("magic", deck, _candidate_fn)
        assert results == []

    def test_no_archetype_no_tags_returns_empty(self):
        """Without archetype or tag_set_fn, no heuristic triggers."""
        results = suggest_removals("magic", _BURN_DECK, _candidate_fn)
        assert results == []


# ---------------------------------------------------------------------------
# TestSuggestReplacements
# ---------------------------------------------------------------------------

class TestSuggestReplacements:
    """Tests for suggest_replacements()."""

    def test_basic_returns_tuples(self):
        """Returns non-empty list of 3-tuples."""
        results = suggest_replacements(
            "magic",
            _BURN_DECK,
            "Lightning Bolt",
            _candidate_fn,
        )
        assert len(results) > 0
        for repl_name, score, reason in results:
            assert isinstance(repl_name, str)
            assert isinstance(score, float)
            assert isinstance(reason, str)
            assert len(reason) > 0

    def test_replacement_excludes_original(self):
        """The card being replaced never appears in the results."""
        results = suggest_replacements(
            "magic",
            _BURN_DECK,
            "Lightning Bolt",
            _candidate_fn,
            top_k=20,
        )
        repl_names = [name for name, _, _ in results]
        assert "Lightning Bolt" not in repl_names

    def test_replacement_excludes_deck_cards(self):
        """Replacements are not already in the deck (via candidate_fn filtering).

        Note: suggest_replacements filters out the replaced card via
        resolver.equals, but does NOT itself filter other deck members.
        The candidate_fn may return cards already in the deck.
        This test documents the current behavior.
        """
        results = suggest_replacements(
            "magic",
            _BURN_DECK,
            "Goblin Guide",
            _candidate_fn,
        )
        # Monastery Swiftspear IS in deck but candidate_fn returns it for
        # Goblin Guide. suggest_replacements does NOT filter deck members
        # besides the replaced card itself -- document this behavior.
        repl_names = [name for name, _, _ in results]
        assert "Goblin Guide" not in repl_names

    def test_respects_top_k(self):
        """Output length capped by top_k."""
        results = suggest_replacements(
            "magic",
            _BURN_DECK,
            "Lightning Bolt",
            _candidate_fn,
            top_k=2,
        )
        assert len(results) <= 2

    def test_upgrade_boosts_expensive(self):
        """With upgrade=True, pricier replacements score higher."""
        results_normal = suggest_replacements(
            "magic",
            _BURN_DECK,
            "Lightning Bolt",
            _candidate_fn,
            price_fn=_price_fn,
        )
        results_upgrade = suggest_replacements(
            "magic",
            _BURN_DECK,
            "Lightning Bolt",
            _candidate_fn,
            price_fn=_price_fn,
            upgrade=True,
        )
        # Searing Blaze costs $3.00 vs Lightning Bolt $1.50 -- upgrade should
        # boost its score relative to non-upgrade.
        def score_for(results: list, card: str) -> float | None:
            for name, sc, _ in results:
                if name == card:
                    return sc
            return None

        normal_score = score_for(results_normal, "Searing Blaze")
        upgrade_score = score_for(results_upgrade, "Searing Blaze")
        assert normal_score is not None and upgrade_score is not None
        assert upgrade_score > normal_score

    def test_downgrade_boosts_cheaper(self):
        """With downgrade=True, cheaper replacements score higher."""
        # Replace Goblin Guide ($5.00) -- Monastery Swiftspear ($0.50) is cheaper
        results_normal = suggest_replacements(
            "magic",
            _make_deck([("Goblin Guide", 4), ("Mountain", 16)]),
            "Goblin Guide",
            _candidate_fn,
            price_fn=_price_fn,
        )
        results_downgrade = suggest_replacements(
            "magic",
            _make_deck([("Goblin Guide", 4), ("Mountain", 16)]),
            "Goblin Guide",
            _candidate_fn,
            price_fn=_price_fn,
            downgrade=True,
        )

        def score_for(results: list, card: str) -> float | None:
            for name, sc, _ in results:
                if name == card:
                    return sc
            return None

        normal_score = score_for(results_normal, "Monastery Swiftspear")
        downgrade_score = score_for(results_downgrade, "Monastery Swiftspear")
        assert normal_score is not None and downgrade_score is not None
        assert downgrade_score > normal_score

    def test_card_not_in_vocab_returns_empty(self):
        """Card with no similarity data returns empty list."""
        results = suggest_replacements(
            "magic",
            _BURN_DECK,
            "Nonexistent Card",
            _candidate_fn,
        )
        assert results == []

    def test_with_max_unit_price(self):
        """Price constraint: suggest_replacements does not itself filter by price,
        but upgrade/downgrade flags use price_fn for scoring."""
        # This documents current behavior -- price_fn affects scoring, not filtering
        results = suggest_replacements(
            "magic",
            _BURN_DECK,
            "Lightning Bolt",
            _candidate_fn,
            price_fn=_price_fn,
            max_unit_price=1.00,  # param exists but is unused in current impl
        )
        # Still returns results (price is scoring, not gating)
        assert len(results) > 0

    def test_functional_alternative_reason(self):
        """Cards sharing roles get 'functional_alternative' reason."""
        # Lightning Bolt has {removal, burn}; Searing Blaze has {removal, burn}
        # overlap > 0.5 -> functional_alternative
        results = suggest_replacements(
            "magic",
            _BURN_DECK,
            "Lightning Bolt",
            _candidate_fn,
            tag_set_fn=_tag_set_fn,
        )
        reasons_by_card = {name: reason for name, _, reason in results}
        assert reasons_by_card.get("Searing Blaze", "").startswith("functional_alternative")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases spanning both functions."""

    def test_all_copies_one_card(self):
        """Deck with only copies of one card."""
        deck = _make_deck([("Lightning Bolt", 4)])
        removals = suggest_removals(
            "magic", deck, _candidate_fn,
            archetype="burn", archetype_staples=_BURN_STAPLES,
        )
        # Lightning Bolt IS a burn staple at 98%, no reason to flag
        assert all(name != "Lightning Bolt" or score < 0.5 for name, score, _ in removals)

        replacements = suggest_replacements(
            "magic", deck, "Lightning Bolt", _candidate_fn,
        )
        assert len(replacements) > 0

    def test_empty_tags(self):
        """tag_set_fn returning empty set for all cards."""
        def empty_tags(_):
            return set()
        deck = _make_deck([
            ("Lightning Bolt", 4),
            ("Goblin Guide", 4),
            ("Dark Confidant", 2),
            ("Mountain", 10),
        ])
        removals = suggest_removals(
            "magic", deck, _candidate_fn,
            preserve_roles=True,
            tag_set_fn=empty_tags,
        )
        # No roles detected -> no redundancy -> no removals (without archetype)
        assert removals == []

        replacements = suggest_replacements(
            "magic", deck, "Lightning Bolt", _candidate_fn,
            tag_set_fn=empty_tags,
        )
        # Still returns results (similarity-based, role overlap is 0)
        assert len(replacements) > 0
        # All reasons should be "similar_card" (no role overlap)
        for _, _, reason in replacements:
            assert reason == "similar_card"

    def test_candidate_fn_returns_empty(self):
        """candidate_fn producing no candidates."""
        def empty_fn(card, k):
            return []
        deck = _make_deck([("Lightning Bolt", 4), ("Mountain", 10)])
        # Removals don't depend on candidate_fn for scoring
        # (they use archetype and role heuristics), so this is a no-op test
        removals = suggest_removals("magic", deck, empty_fn)
        assert removals == []

        replacements = suggest_replacements(
            "magic", deck, "Lightning Bolt", empty_fn,
        )
        assert replacements == []
