"""The non-learned baselines score exactly the candidates they are given.

These tests guard the two properties the comparison harness relies on: a
heuristic arm is deterministic (same index, same scores) and it answers for the
passed candidate tuple only (no extra keys, no reordering, no re-retrieval).
Everything else here is arithmetic on a hand-built metadata table.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "evaluation" / "heuristic_scorers.py"

HEADER = [
    "name",
    "type",
    "cmc",
    "oracle_text",
    "mana_cost",
    "color_identity_str",
    "rarity",
    "keyword_abilities",
]

CARDS = [
    (
        "Bolt",
        "Instant",
        "1.0",
        "Bolt deals 3 damage to any target.",
        "{R}",
        "R",
        "common",
        "",
    ),
    (
        "Shock",
        "Instant",
        "1.0",
        "Shock deals 2 damage to any target.",
        "{R}",
        "R",
        "common",
        "",
    ),
    (
        "Elf",
        "Creature — Elf Druid",
        "1.0",
        "Add {G}. (This mana is a reminder span.)",
        "{G}",
        "G",
        "common",
        "Flying",
    ),
    (
        "Bear",
        "Creature — Bear",
        "2.0",
        "Vanilla body with no abilities.",
        "{1}{G}",
        "G",
        "common",
        "",
    ),
    (
        "Counter",
        "Instant",
        "2.0",
        "Counter target spell.",
        "{1}{U}",
        "U",
        "common",
        "",
    ),
]


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location("heuristic_scorers", SCRIPT)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def metadata(tmp_path: Path) -> Path:
    path = tmp_path / "card_attributes_magic_enriched.csv"
    lines = [",".join(HEADER)]
    for row in CARDS:
        lines.append(",".join(f'"{value}"' for value in row))
    path.write_text("\n".join(lines) + "\n")
    return path


def test_tokenize_strips_reminder_mana_and_numbers(module):
    tokens = module.tokenize(
        "Elf gets +2/+2 (a reminder span). Add {G}{G} and draw 3 cards, X spells."
    )

    assert "reminder" not in tokens
    assert "span" not in tokens
    assert "g" not in tokens  # mana symbols are a structured feature, not text
    assert "3" not in tokens
    assert "num" in tokens
    assert "ptcounter" in tokens
    assert "x" in tokens


def test_tokenize_drops_stopwords_only(module):
    tokens = module.tokenize("the target creature you control")

    assert tokens == ["target", "creature", "control"]


def test_lexical_is_deterministic_across_builds(module, metadata):
    first = module.build_lexical("magic", metadata)
    second = module.build_lexical("magic", metadata)
    candidates = [name for name, *_ in CARDS]

    assert first.cosines("Bolt", candidates).tolist() == second.cosines("Bolt", candidates).tolist()
    assert first.cosines("Bolt", candidates).tolist() == first.cosines("Bolt", candidates).tolist()


def test_lexical_scores_exactly_the_candidates_given(module, metadata):
    index = module.build_lexical("magic", metadata)
    candidates = ["Shock", "Bear", "Counter"]

    scored = index.cosines("Bolt", candidates)

    assert scored.shape == (len(candidates),)
    assert np.isfinite(scored).all()
    assert index.cosines("Bolt", []).shape == (0,)


def test_lexical_candidate_scores_match_the_full_scan(module, metadata):
    """Retrieval over all keys and scoring a shortlist must agree exactly."""
    index = module.build_lexical("magic", metadata)
    shortlist = ["Shock", "Elf"]

    full = index.cosines("Bolt", index.keys)
    positions = [index.positions[name] for name in shortlist]

    assert full[positions].tolist() == index.cosines("Bolt", shortlist).tolist()


def test_lexical_refuses_unknown_candidates(module, metadata):
    index = module.build_lexical("magic", metadata)

    with pytest.raises(module.HeuristicError, match="lacks candidates"):
        index.cosines("Bolt", ["Shock", "Not A Card"])


def test_structured_prefers_same_slot_over_shared_text(module, metadata):
    index = module.build_structured("magic", metadata)
    scores = index.cosines("Bolt", ["Shock", "Counter", "Elf", "Bear"])

    # Shock shares type, mana value, colour and text; Counter shares type and
    # cost only; Elf and Bear share neither type nor cost.
    assert scores[0] > scores[1] > scores[2]
    assert scores[0] > scores[3]


def test_structured_is_deterministic_and_tuple_bounded(module, metadata):
    index = module.build_structured("magic", metadata)
    candidates = ["Counter", "Bear"]

    first = index.cosines("Bolt", candidates)
    second = index.cosines("Bolt", candidates)

    assert first.tolist() == second.tolist()
    assert first.shape == (len(candidates),)
    assert index.cosines("Bolt", []).shape == (0,)


def test_structured_does_not_reward_two_empty_keyword_sets(module, metadata):
    """Bear and Counter both have no keywords; sharing nothing is not a match."""
    index = module.build_structured("magic", metadata)

    bear, counter = index.positions["Bear"], index.positions["Counter"]
    rows = np.array([counter])
    scores = index.score_rows(bear, rows)

    # With keywords masked, the remaining components decide: different type,
    # different mana value, different colour, unrelated text.
    assert scores[0] < 0.5


def test_build_heuristic_dispatches_by_name(module, metadata):
    assert module.build_heuristic("b1", "magic", metadata).name.startswith("heuristic:b1")
    assert module.build_heuristic("heuristic:b2", "magic", metadata).name.startswith("heuristic:b2")
    assert module.is_heuristic_spec("heuristic:b1")
    assert module.is_heuristic_spec("b2")
    assert not module.is_heuristic_spec("magic_v7_spectral_mu35")

    with pytest.raises(module.HeuristicError, match="unknown heuristic"):
        module.build_heuristic("b3", "magic", metadata)
