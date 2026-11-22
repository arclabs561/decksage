from copy import deepcopy

import pytest

from ml.deck_building.beam_search import beam_search_completion
from ml.deck_building.deck_completion import CompletionConfig, greedy_complete
from ml.deck_building.deck_quality import assess_deck_quality, compute_tag_distribution
from ml.deck_building.ot_completion import (
    OTCompletionConfig,
    deck_to_distribution,
    ot_complete_deck,
)
from ml.utils.deck_parser import parse_deck_text


GROUPED = "Pokémon: 2\n2 Pikachu\nTrainer: 2\n2 Nest Ball\nEnergy: 4\n4 Lightning Energy"
FLAT = "Deck\n2 Pikachu\n2 Nest Ball\n4 Lightning Energy"


def test_grouped_and_flat_pokemon_have_the_same_scores_and_seeds():
    grouped = parse_deck_text(GROUPED, "pokemon")
    flat = parse_deck_text(FLAT, "pokemon")
    original = deepcopy(grouped)
    costs = {"Pikachu": 2, "Nest Ball": 1, "Lightning Energy": 0}

    def tags(card):
        return {"playable", card}

    scores = assess_deck_quality(grouped, "pokemon", tags, costs.get, reference_decks=[flat])
    assert scores == assess_deck_quality(
        flat, "pokemon", tags, costs.get, reference_decks=[grouped]
    )
    assert (scores.num_cards, scores.avg_tags_per_card) == (8, 2)
    assert compute_tag_distribution(grouped, "pokemon", tags, "Trainer") == {
        "playable": 2,
        "Nest Ball": 2,
    }
    assert deck_to_distribution(grouped, "pokemon", list(costs)) == pytest.approx([0.25, 0.25, 0.5])

    config = CompletionConfig(game="pokemon", target_main_size=9)
    result, steps, _ = greedy_complete("pokemon", grouped, lambda *_: [("Raichu", 1)], config)
    assert [(s["card"], s["count"]) for s in steps] == [("Raichu", 1)]
    assert sum(c["count"] for p in result["partitions"] for c in p["cards"]) == 9
    assert grouped == original


def test_beam_ranks_each_current_deck_and_ot_stops_at_target():
    grouped = parse_deck_text(GROUPED, "pokemon")
    seen = []

    def candidates(current, _):
        size = sum(c["count"] for p in current["partitions"] for c in p["cards"])
        seen.append(size)
        return [("Raichu", 1.0)]

    result = beam_search_completion(
        grouped,
        lambda *_: [],
        CompletionConfig(game="pokemon", target_main_size=10),
        deck_candidate_fn=candidates,
    )
    assert seen == [8, 9]
    assert result["partitions"][-1]["cards"] == [{"name": "Raichu", "count": 2}]
    result = ot_complete_deck(
        "pokemon", grouped, {}, OTCompletionConfig(game="pokemon", target_main_size=8)
    )
    assert result.deck == grouped
    assert result.metrics["current_size"] == 8


def test_beam_api_completes_parsed_pokemon_and_reports_the_selected_move(monkeypatch):
    from types import SimpleNamespace

    from ml.api import deck_routes, query_history
    from ml.api.models import CompleteRequest

    state = SimpleNamespace(archetype_templates=[], card_metadata={}, graph_data=None)
    monkeypatch.setattr(deck_routes, "get_state", lambda _: state)
    monkeypatch.setattr(deck_routes, "_build_deck_hooks", lambda _: (None, None, None))
    monkeypatch.setattr(
        deck_routes, "_make_candidate_fn", lambda *a, **kw: lambda *_: [("Raichu", 1.0)]
    )
    logged = {}
    monkeypatch.setattr(query_history, "log_query", lambda **kw: logged.update(kw))
    request = CompleteRequest(game="pokemon", deck_text=GROUPED, method="beam", target_main_size=9)
    response = deck_routes.complete_deck(request)
    assert logged["metadata"]["current_size"] == 8
    assert response.metrics["steps"] == 1
    assert response.steps == [{"op": "add_card", "partition": "Deck", "card": "Raichu", "count": 1}]
    assert sum(c["count"] for p in response.deck["partitions"] for c in p["cards"]) == 9
