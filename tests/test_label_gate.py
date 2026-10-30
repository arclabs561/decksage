"""Tests for the evaluation label gate (no metadata needed)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.evaluation.label_gate import BLOCKING_RULES, GateResult, screen_corpus


@dataclass
class FakeHit:
    rule_id: str
    card_a: str = "A"
    card_b: str = "B"


def test_blocking_rules_are_the_structural_ones() -> None:
    assert set(BLOCKING_RULES) == {
        "self_pair",
        "kind_conflict",
        "evolution_conflict",
    }
    # A cross-type substitute can be legitimate for another deck, so the gate
    # reports it and does not refuse on it. Pinned so a future widening of the
    # blocking set has to be deliberate.
    assert "type_conflict" not in BLOCKING_RULES


def test_reporting_only_rules_do_not_block() -> None:
    result = GateResult(path=Path("x.json"))
    result.hits = [FakeHit("duplicate_conflict"), FakeHit("bucket_mismatch")]
    assert result.blocking == []


def test_structural_rule_blocks() -> None:
    result = GateResult(path=Path("x.json"))
    result.hits = [FakeHit("kind_conflict"), FakeHit("duplicate_conflict")]
    assert [h.rule_id for h in result.blocking] == ["kind_conflict"]


def test_counts_sort_by_frequency() -> None:
    result = GateResult(path=Path("x.json"))
    result.hits = [FakeHit("type_conflict"), FakeHit("type_conflict"), FakeHit("self_pair")]
    assert list(result.counts().items()) == [("type_conflict", 2), ("self_pair", 1)]


def test_summary_names_the_reason_when_skipped() -> None:
    result = GateResult(path=Path("x.json"), skipped="corpus not found")
    assert "gate not applied" in result.summary()


def test_missing_corpus_is_skipped_not_blocked(tmp_path: Path) -> None:
    result = screen_corpus(tmp_path / "absent.json")
    assert result.skipped is not None
    assert result.blocking == []


def test_superseded_content_is_refused(tmp_path: Path) -> None:
    """Reintroducing a repaired-away set must fail, not silently score."""
    import hashlib
    import json

    from ml.evaluation.label_gate import refuse_if_superseded

    stale = tmp_path / "stale.json"
    stale.write_text('{"queries": {}}')
    digest = hashlib.sha256(stale.read_bytes()).hexdigest()
    ledger = tmp_path / "REPAIR-LEDGER.json"
    ledger.write_text(json.dumps({"games": [{"game": "magic", "original": {"sha256": digest}}]}))
    try:
        refuse_if_superseded(stale, ledger_path=ledger)
    except ValueError as exc:
        assert "superseded" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("superseded content was accepted")

    # the repaired content is the fix, not the fault: it must pass
    repaired = tmp_path / "repaired.json"
    repaired.write_text('{"queries": {"x": 1}}')
    refuse_if_superseded(repaired, ledger_path=ledger)
