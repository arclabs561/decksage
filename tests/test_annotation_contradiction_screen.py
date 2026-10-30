"""Rule-level checks for the structural contradiction screen.

Each test uses a tiny synthetic pair and metadata, so a failure names the rule
that regressed rather than a corpus-level count.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def screen():
    path = Path(__file__).resolve().parents[1] / "scripts/annotation/screen_contradictions.py"
    spec = importlib.util.spec_from_file_location("screen_contradictions", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["screen_contradictions"] = module
    spec.loader.exec_module(module)
    return module


def card(screen, name, game, kind, **overrides):
    fields = {
        "name": name,
        "game": game,
        "kind": kind,
        "oracle_text": "some rules text",
        "type_line": kind,
    }
    fields.update(overrides)
    return screen.CardMeta(**fields)


def record(screen, card_a, card_b, score, game="pokemon", **overrides):
    fields = {
        "card_a": card_a,
        "card_b": card_b,
        "score": score,
        "game": game,
        "mode": "substitution",
        "is_substitute": False,
        "relevance": None,
        "bucket_membership": None,
        "source_file": "fixture.jsonl",
        "line": 1,
        "record_path": "",
        "raw": {},
    }
    fields.update(overrides)
    return screen.PairRecord(**fields)


def test_self_pair_is_high(screen):
    meta = {"pokemon": {}}
    hit = screen.check_self_pair(record(screen, "Abra", "Abra", 0.8), meta)
    assert hit is not None
    assert hit.rule_id == "self_pair"
    assert hit.severity == "high"


def test_gender_symbols_do_not_make_a_self_pair(screen):
    meta = {"pokemon": {}}
    assert screen.check_self_pair(record(screen, "Nidoran ♀", "Nidoran ♂", 0.8), meta) is None
    assert screen.check_self_pair(record(screen, "Unown [?]", "Unown [!]", 0.8), meta) is None
    hit = screen.check_self_pair(record(screen, "Genesect ex", "Genesect-EX", 0.8), meta)
    assert hit is not None


def test_trainer_versus_creature_is_a_kind_conflict(screen):
    meta = {
        "pokemon": {
            "teamstargrunt": card(screen, "Team Star Grunt", "pokemon", "trainer"),
            "greedentex": card(screen, "Greedent ex", "pokemon", "creature"),
        }
    }
    hit = screen.check_kind_conflict(record(screen, "Team Star Grunt", "Greedent ex", 0.83), meta)
    assert hit is not None
    assert hit.rule_id == "kind_conflict"
    assert hit.evidence["kind_a"] == "trainer"


def test_kind_conflict_needs_high_score_and_substitution_intent(screen):
    meta = {
        "pokemon": {
            "teamstargrunt": card(screen, "Team Star Grunt", "pokemon", "trainer"),
            "greedentex": card(screen, "Greedent ex", "pokemon", "creature"),
        }
    }
    low = record(screen, "Team Star Grunt", "Greedent ex", 0.4)
    assert screen.check_kind_conflict(low, meta) is None
    synergy = record(screen, "Team Star Grunt", "Greedent ex", 0.9, mode="synergy")
    assert screen.check_kind_conflict(synergy, meta) is None


def test_magic_kind_conflict_uses_the_higher_threshold(screen):
    meta = {
        "magic": {
            "grizzlybears": card(screen, "Grizzly Bears", "magic", "creature"),
            "lightningbolt": card(screen, "Lightning Bolt", "magic", "instant"),
        }
    }
    assert (
        screen.check_kind_conflict(
            record(screen, "Grizzly Bears", "Lightning Bolt", 0.8, game="magic"), meta
        )
        is None
    )
    hit = screen.check_kind_conflict(
        record(screen, "Grizzly Bears", "Lightning Bolt", 0.9, game="magic"), meta
    )
    assert hit is not None


def test_basic_versus_stage_two_substitute_is_an_evolution_conflict(screen):
    meta = {
        "pokemon": {
            "abra": card(screen, "Abra", "pokemon", "creature", stage="basic"),
            "alakazam": card(screen, "Alakazam", "pokemon", "creature", stage="stage2"),
        }
    }
    hit = screen.check_evolution_conflict(record(screen, "Abra", "Alakazam", 0.85), meta)
    assert hit is not None
    assert hit.rule_id == "evolution_conflict"
    assert hit.evidence["stage_a"] == "basic"
    assert hit.evidence["stage_b"] == "stage2"


def test_evolution_conflict_ignores_same_stage_and_synergy(screen):
    meta = {
        "pokemon": {
            "abra": card(screen, "Abra", "pokemon", "creature", stage="basic"),
            "alakazam": card(screen, "Alakazam", "pokemon", "creature", stage="stage2"),
        }
    }
    same = record(screen, "Abra", "Abra", 0.9)
    assert screen.check_evolution_conflict(same, meta) is None
    synergy = record(screen, "Abra", "Alakazam", 0.9, mode="synergy")
    assert screen.check_evolution_conflict(synergy, meta) is None


def test_energy_type_conflict_requires_a_high_substitution_score(screen):
    meta = {
        "pokemon": {
            "gossifleur": card(screen, "Gossifleur", "pokemon", "creature", energy_type="Grass"),
            "nsklink": card(screen, "N's Klink", "pokemon", "creature", energy_type="Metal"),
        }
    }
    hit = screen.check_type_conflict(record(screen, "Gossifleur", "N's Klink", 0.9), meta)
    assert hit is not None
    assert hit.evidence["energy_type_a"] == "Grass"
    assert screen.check_type_conflict(record(screen, "Gossifleur", "N's Klink", 0.2), meta) is None


def test_yugioh_attribute_conflict(screen):
    meta = {
        "yugioh": {
            "left": card(screen, "Left", "yugioh", "creature", attribute="LIGHT"),
            "right": card(screen, "Right", "yugioh", "creature", attribute="DARK"),
        }
    }
    hit = screen.check_type_conflict(record(screen, "Left", "Right", 0.9, game="yugioh"), meta)
    assert hit is not None
    assert hit.evidence["attribute_a"] == "LIGHT"


def test_score_without_evidence_is_flagged_but_metadata_gap_is_low(screen):
    empty = {"pokemon": {"a": card(screen, "Aaa", "pokemon", "creature", oracle_text="")}}
    hit = screen.check_score_evidence(record(screen, "Aaa", "Bbb", 0.9), empty)
    assert hit is not None
    assert hit.severity == "low"  # Bbb metadata is absent, so coverage is unknown
    present = {
        "pokemon": {
            "aaa": card(screen, "Aaa", "pokemon", "creature", oracle_text=""),
            "bbb": card(screen, "Bbb", "pokemon", "creature", oracle_text=""),
        }
    }
    assert (
        screen.check_score_evidence(record(screen, "Aaa", "Bbb", 0.9), present).severity == "medium"
    )


def test_name_overlap_suppresses_score_evidence_conflict(screen):
    meta = {
        "pokemon": {
            "airballoon": card(screen, "Air Balloon", "pokemon", "trainer", oracle_text=""),
            "bigairballoon": card(screen, "Big Air Balloon", "pokemon", "trainer", oracle_text=""),
        }
    }
    assert (
        screen.check_score_evidence(record(screen, "Air Balloon", "Big Air Balloon", 0.9), meta)
        is None
    )


def test_duplicate_conflict_reports_only_same_mode_dispersion(screen):
    records = [
        record(screen, "Tribute Mage", "Trophy Mage", 0.0, game="magic"),
        record(screen, "Tribute Mage", "Trophy Mage", 0.9, game="magic"),
        record(screen, "Tribute Mage", "Trophy Mage", 0.1, game="magic", mode="synergy"),
    ]
    hits = screen.duplicate_hits(records)
    assert len(hits) == 1
    assert hits[0].evidence["scores"] == [0.0, 0.9]
    assert hits[0].evidence["mode"] == "substitution"


def test_bucket_mismatch_uses_the_canonical_bands(screen):
    meta = {"pokemon": {}}
    hit = screen.check_bucket_mismatch(
        record(screen, "A", "B", 0.2, relevance="highly_relevant"), meta
    )
    assert hit is not None
    assert hit.evidence["expected_bucket"] == "marginally_relevant"
    assert hit.severity == "low"
    assert (
        screen.check_bucket_mismatch(
            record(screen, "A", "B", 0.8, relevance="highly_relevant"), meta
        )
        is None
    )


def test_curation_removes_only_self_pairs(screen, tmp_path):
    source = tmp_path / "pairs.jsonl"
    rows = [
        {"query": "Abra", "candidate": "Abra", "similarity_score": 0.8, "mode": "substitution"},
        {"query": "Abra", "candidate": "Alakazam", "similarity_score": 0.8, "mode": "substitution"},
        {"query": "Abra", "candidate": "Alakazam", "similarity_score": 0.1, "mode": "substitution"},
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    before = source.read_bytes()
    records = screen.load_records(source)
    output = tmp_path / "curated" / "pairs.jsonl"
    written, removed = screen.curate_corpus(source, records, output)
    assert written == output
    assert [item["reason"] for item in removed] == ["self_pair"]
    assert source.read_bytes() == before
    kept = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(kept) == 2
    assert {entry["similarity_score"] for entry in kept} == {0.8, 0.1}


def test_curation_never_writes_over_the_source(screen, tmp_path):
    source = tmp_path / "pairs.json"
    source.write_text(
        json.dumps({"labels": [{"card1": "A", "card2": "B", "similarity_score": 0.5}]}),
        encoding="utf-8",
    )
    before = source.read_bytes()
    records = screen.load_records(source)
    output = tmp_path / "copy.json"
    screen.curate_corpus(source, records, output)
    assert source.read_bytes() == before
    assert output.exists()
