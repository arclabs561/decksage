"""Tests for the canonical judge prompts and their strict parser.

No network, no model calls: every response here is a literal string.
"""

from __future__ import annotations

import csv
import itertools
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.annotation import prompts as p


BOLT = p.CardFacts(
    name="Lightning Bolt",
    type_line="Instant",
    text="Lightning Bolt deals 3 damage to any target.",
    cost="{R}",
)
SHOCK = p.CardFacts(
    name="Shock",
    type_line="Instant",
    text="Shock deals 2 damage to any target.",
    cost="{R}",
)


def _similarity_prompt(**kwargs):
    return p.build_prompt("similarity", BOLT, SHOCK, game="magic", **kwargs)


def _response(**overrides) -> str:
    payload = {
        "prompt_version": p.PROMPT_VERSION,
        "task": "similarity",
        "status": "scored",
        "band": "near_substitute",
        "score": 0.75,
        "confidence": 0.8,
        "rationale": "Same card type, same cost and same target; only the damage number differs.",
        "card_a": "Lightning Bolt",
        "card_b": "Shock",
        "differences": ["3 damage instead of 2"],
    }
    payload.update(overrides)
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("task", ["similarity", "substitute", "synergy", "meta"])
def test_pair_prompt_carries_version_bands_and_uncertain_path(task):
    prompt = p.build_prompt(task, BOLT, SHOCK, game="magic")
    assert prompt.prompt_version == p.PROMPT_VERSION
    assert p.PROMPT_VERSION in prompt.user
    assert "uncertain" in prompt.user.lower()
    for band in p.BANDS[p.JudgeTask(task)]:
        assert band.key in prompt.user
    assert "Anchors (declared rubric anchors" in prompt.user


def test_only_symmetric_tasks_get_the_order_instruction():
    for task in ("similarity", "substitute", "synergy", "meta"):
        assert "symmetric" in p.build_prompt(task, BOLT, SHOCK, game="magic").system.lower()
    archetype = p.build_prompt(
        "archetype", BOLT, None, game="magic", candidates=["Burn", "Control"]
    )
    assert "symmetric" not in archetype.system.lower()


def test_swap_reverses_cards_but_keeps_identity_and_instructions():
    forward = _similarity_prompt()
    swapped = _similarity_prompt(swap=True)
    assert forward.card_a == "Lightning Bolt"
    assert swapped.card_a == "Shock"
    assert forward.pair_key == swapped.pair_key
    assert forward.system == swapped.system
    assert "Lightning Bolt" in forward.user.split("Card A:", 1)[1].split("Card B:", 1)[0]
    assert "Lightning Bolt" in swapped.user.split("Card B:", 1)[1]


def test_swap_is_refused_for_non_symmetric_tasks():
    with pytest.raises(ValueError):
        p.build_prompt("archetype", BOLT, None, game="magic", candidates=["Burn"], swap=True)


def test_meta_prompt_refuses_to_guess_without_evidence():
    without = p.build_prompt("meta", BOLT, SHOCK, game="magic")
    assert 'status "uncertain"' in without.user
    with_evidence = p.build_prompt(
        "meta",
        BOLT,
        SHOCK,
        game="magic",
        evidence={
            "corpus": "test corpus",
            "decks_with_a": 10,
            "decks_with_b": 5,
            "decks_with_both": 4,
            "deck_total": 100,
        },
    )
    assert "Decks containing both: 4" in with_evidence.user


def test_archetype_prompt_is_a_closed_set():
    prompt = p.build_prompt(
        "archetype", BOLT, None, game="yugioh", candidates=["Snake-Eye", "Blue-Eyes"]
    )
    assert "Candidates (closed set): Snake-Eye, Blue-Eyes" in prompt.user
    assert "must not be invented" in prompt.user.lower()


def test_deck_quality_prompt_needs_a_summary_and_lists_real_anchors():
    with pytest.raises(ValueError):
        p.build_prompt("deck_quality", BOLT, None, game="magic")
    prompt = p.build_prompt(
        "deck_quality",
        BOLT,
        None,
        game="magic",
        deck_summary={"total_cards": 59, "expected_size": 60, "max_copies": 4},
    )
    assert "Rakdos evil" in prompt.user
    assert "size_fit" in prompt.user


def test_card_facts_from_metadata_row_keeps_only_recorded_facts():
    row = {
        "name": "Blue-Eyes White Dragon",
        "type": "Normal Monster",
        "oracle_text": "This legendary dragon is a powerful engine of destruction.",
        "atk": "3000.0",
        "def_stat": "2500.0",
        "level_rank_link": "8.0",
        "archetype": "Blue-Eyes",
    }
    facts = p.card_facts_from_row(row)
    assert facts.name == "Blue-Eyes White Dragon"
    assert "ATK/DEF 3000.0/2500.0" in facts.stats
    assert "Level/Rank 8.0" in facts.stats
    assert facts.archetype == "Blue-Eyes"
    assert facts.cost is None
    with pytest.raises(ValueError):
        p.card_facts_from_row({"name": "No Text"})


# ---------------------------------------------------------------------------
# Parsing: valid
# ---------------------------------------------------------------------------


def test_valid_response_is_parsed_with_band_and_version():
    label = p.parse_pair_label(_response(), _similarity_prompt())
    assert label.status is p.JudgeStatus.SCORED
    assert label.score == 0.75
    assert label.band is not None and label.band.key == "near_substitute"
    assert label.prompt_version == p.PROMPT_VERSION


def test_legacy_record_keeps_the_prompt_version_and_task():
    label = p.parse_pair_label(_response(), _similarity_prompt())
    record = label.as_legacy_record()
    assert record["similarity_score"] == 0.75
    assert record["prompt_version"] == p.PROMPT_VERSION
    assert record["task"] == "similarity"
    assert record["judge_band"] == "near_substitute"


def test_uncertain_response_is_valid_and_has_no_score():
    text = _response(status="uncertain", band=None, score=None, differences=[])
    label = p.parse_pair_label(text, _similarity_prompt())
    assert label.status is p.JudgeStatus.UNCERTAIN
    assert label.score is None and label.band is None


@pytest.mark.parametrize(
    ("task", "band", "score", "field"),
    [
        ("substitute", "close", 0.7, "substitutability"),
        ("synergy", "strong", 0.7, "synergy_score"),
        ("meta", "common", 0.5, "meta_relevance"),
    ],
)
def test_per_task_labels_map_to_their_legacy_field(task, band, score, field):
    prompt = p.build_prompt(task, BOLT, SHOCK, game="magic")
    text = _response(task=task, band=band, score=score)
    label = p.parse_pair_label(text, prompt)
    assert label.as_legacy_record()[field] == score


# ---------------------------------------------------------------------------
# Parsing: malformed responses
# ---------------------------------------------------------------------------


def test_prose_wrapped_json_is_rejected():
    text = "Sure! Here is the answer:\n" + _response()
    with pytest.raises(p.JudgeResponseError):
        p.parse_pair_label(text, _similarity_prompt())


def test_markdown_fence_is_rejected():
    with pytest.raises(p.JudgeResponseError):
        p.parse_pair_label("```json\n" + _response() + "\n```", _similarity_prompt())


def test_score_outside_declared_band_is_rejected():
    with pytest.raises(p.JudgeResponseError, match="outside the declared band"):
        p.parse_pair_label(_response(band="near_substitute", score=0.2), _similarity_prompt())


def test_unknown_band_is_rejected():
    with pytest.raises(p.JudgeResponseError, match="unknown band"):
        p.parse_pair_label(_response(band="vibes"), _similarity_prompt())


def test_wrong_prompt_version_is_rejected():
    with pytest.raises(p.JudgeResponseError, match="prompt_version"):
        p.parse_pair_label(_response(prompt_version="judge-prompt-v0.9.0"), _similarity_prompt())


def test_task_mismatch_is_rejected():
    with pytest.raises(p.JudgeResponseError, match="task"):
        p.parse_pair_label(_response(task="substitute"), _similarity_prompt())


def test_echoed_cards_must_match_the_prompt():
    with pytest.raises(p.JudgeResponseError, match="echoed cards"):
        p.parse_pair_label(_response(card_b="Shock "), _similarity_prompt())
    with pytest.raises(p.JudgeResponseError, match="echoed cards"):
        p.parse_pair_label(_response(card_b="Chain Lightning"), _similarity_prompt())


def test_string_score_is_rejected_under_strict_types():
    with pytest.raises(p.JudgeResponseError):
        p.parse_pair_label(_response(score="0.75"), _similarity_prompt())


def test_extra_keys_are_rejected():
    with pytest.raises(p.JudgeResponseError):
        p.parse_pair_label(_response(mode="synergy"), _similarity_prompt())


def test_short_rationale_is_rejected():
    with pytest.raises(p.JudgeResponseError, match="rationale"):
        p.parse_pair_label(_response(rationale="same card"), _similarity_prompt())


def test_scored_response_needs_a_difference():
    with pytest.raises(p.JudgeResponseError, match="differences"):
        p.parse_pair_label(_response(differences=[]), _similarity_prompt())


def test_uncertain_response_may_not_smuggle_a_score():
    with pytest.raises(p.JudgeResponseError):
        p.parse_pair_label(
            _response(status="uncertain", band=None, score=0.7), _similarity_prompt()
        )


# ---------------------------------------------------------------------------
# Archetype and deck quality
# ---------------------------------------------------------------------------


def _archetype_prompt():
    return p.build_prompt(
        "archetype",
        p.CardFacts("Snake-Eye Ash", "Effect Monster", "If this card is Normal Summoned: ..."),
        None,
        game="yugioh",
        candidates=["Snake-Eye", "Blue-Eyes"],
    )


def test_archetype_accepts_a_candidate_label():
    text = json.dumps(
        {
            "prompt_version": p.PROMPT_VERSION,
            "task": "archetype",
            "status": "scored",
            "label": "Snake-Eye",
            "confidence": 0.9,
            "rationale": "The metadata records the archetype Snake-Eye and the text names Snake-Eye.",
            "card_a": "Snake-Eye Ash",
        }
    )
    label = p.parse_archetype_label(
        text, _archetype_prompt(), candidates=["Snake-Eye", "Blue-Eyes"]
    )
    assert label.label == "Snake-Eye"


def test_archetype_rejects_an_invented_label():
    text = json.dumps(
        {
            "prompt_version": p.PROMPT_VERSION,
            "task": "archetype",
            "status": "scored",
            "label": "Snake Eyes",
            "confidence": 0.9,
            "rationale": "Close enough to the candidate name that a careless parser would accept it.",
            "card_a": "Snake-Eye Ash",
        }
    )
    with pytest.raises(p.JudgeResponseError, match="candidate set"):
        p.parse_archetype_label(text, _archetype_prompt(), candidates=["Snake-Eye", "Blue-Eyes"])


def _deck_prompt():
    return p.build_prompt(
        "deck_quality",
        p.CardFacts("Rakdos evil", "deck", "decklist"),
        None,
        game="magic",
        deck_summary={"total_cards": 59, "expected_size": 60, "max_copies": 4},
    )


def _deck_response(**overrides):
    payload = {
        "prompt_version": p.PROMPT_VERSION,
        "task": "deck_quality",
        "status": "scored",
        "dimensions": {
            "size_fit": 1,
            "copy_limit": 2,
            "role_coverage": None,
            "archetype_coherence": None,
        },
        "confidence": 0.9,
        "rationale": "59 of 60 cards is within ten percent; the maximum copy count is four.",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_deck_quality_score_is_computed_from_levels():
    label = p.parse_deck_quality_label(_deck_response(), _deck_prompt())
    assert label.score == pytest.approx(3 / 4)
    assert label.dimensions["copy_limit"] == 2


def test_deck_quality_uncertain_requires_all_dimensions_null():
    text = _deck_response(
        status="uncertain",
        dimensions=dict.fromkeys(p.DECK_DIMENSIONS),
    )
    label = p.parse_deck_quality_label(text, _deck_prompt())
    assert label.score is None
    with pytest.raises(p.JudgeResponseError):
        p.parse_deck_quality_label(
            _deck_response(
                status="uncertain",
                dimensions={
                    "size_fit": 1,
                    "copy_limit": None,
                    "role_coverage": None,
                    "archetype_coherence": None,
                },
            ),
            _deck_prompt(),
        )


def test_deck_quality_rejects_out_of_range_and_missing_dimensions():
    bad_level = _deck_response(
        dimensions={
            "size_fit": 3,
            "copy_limit": 2,
            "role_coverage": None,
            "archetype_coherence": None,
        }
    )
    with pytest.raises(p.JudgeResponseError, match="must be 0, 1, 2"):
        p.parse_deck_quality_label(bad_level, _deck_prompt())
    missing = _deck_response(dimensions={"size_fit": 1, "copy_limit": 2, "role_coverage": None})
    with pytest.raises(p.JudgeResponseError, match="dimensions must be exactly"):
        p.parse_deck_quality_label(missing, _deck_prompt())


# ---------------------------------------------------------------------------
# Anchors are grounded in repository metadata
# ---------------------------------------------------------------------------


def _names_from_csv(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["name"] for row in csv.DictReader(handle) if row.get("name")}


@pytest.mark.parametrize("game", ["magic", "pokemon", "yugioh"])
def test_every_pair_anchor_names_a_card_in_repo_metadata(game):
    path = PROJECT_ROOT / "data" / "processed" / f"card_attributes_{game}_enriched.csv"
    if not path.is_file():
        pytest.skip(f"metadata not checked out: {path}")
    names = _names_from_csv(path)
    anchors = [
        anchor
        for (task, anchor_game), values in p.ANCHORS.items()
        if anchor_game == game
        for anchor in values
    ]
    assert anchors, f"no anchors recorded for {game}"
    missing = sorted(
        {name for anchor in anchors for name in (anchor.card_a, anchor.card_b)} - names
    )
    assert not missing, f"anchors cite cards absent from metadata: {missing}"


def test_band_boundaries_are_contiguous_and_cover_the_range():
    for task, bands in p.BANDS.items():
        assert bands[0].low == 0.0
        assert bands[-1].high == 1.0
        for lower, upper in itertools.pairwise(bands):
            assert lower.high == upper.low
        assert p.band_for(task, 0.0) is bands[0]
        assert p.band_for(task, 1.0) is bands[-1]


def test_anchor_export_is_probe_compatible_and_deduplicated():
    rows = p.emit_anchor_pairs()
    assert rows
    keys = [(row["query"], row["candidate"]) for row in rows]
    assert len(keys) == len(set(keys))
    for row in rows:
        assert set(row) == {"query", "candidate", "task", "game"}
        json.dumps(row)  # JSONL-safe
