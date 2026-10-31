"""The repair ledger is tracked and agrees with the canonical evaluation sets."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.evaluation.label_gate import superseded_hashes


LEDGER = PROJECT_ROOT / "data" / "results" / "REPAIR-LEDGER.json"


def _ledger() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def test_ledger_is_tracked_and_names_every_game() -> None:
    ledger = _ledger()
    assert {game["game"] for game in ledger["games"]} == {"magic", "pokemon", "yugioh"}
    for game in ledger["games"]:
        assert len(game["original"]["sha256"]) == 64
        assert len(game["repaired"]["sha256"]) == 64


def test_canonical_hash_matches_where_the_set_is_present() -> None:
    for game in _ledger()["games"]:
        path = PROJECT_ROOT / game["canonical_path"]
        if not path.exists():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == game["repaired"]["sha256"], game["game"]


def test_superseded_hashes_are_the_originals_not_the_repairs() -> None:
    superseded = superseded_hashes()
    assert superseded
    for game in _ledger()["games"]:
        assert game["original"]["sha256"] in superseded
        assert game["repaired"]["sha256"] not in superseded
