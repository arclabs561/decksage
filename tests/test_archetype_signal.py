"""The archetype signal in fusion must be produced from shipped deck labels, or absent.

The API advertised an `archetype` fusion signal that no producer wrote and no
loader could find, so every game logged `signals: 2/3 loaded`. These tests pin
the producer's contract: deterministic artefacts with recorded hashes, honest
"no source data" for a game whose decks carry no archetype label, and a loader
that flips the signal to loaded only when both artefacts exist.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "data_processing" / "build_archetype_signal.py"

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.api.load_signals import load_signals_to_state
from ml.similarity.archetype_signal import archetype_similarity


def _producer():
    spec = importlib.util.spec_from_file_location("build_archetype_signal", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["build_archetype_signal"] = module
    spec.loader.exec_module(module)
    return module


def _deck(deck_id: str, archetype: str | None, cards: list[str]) -> dict:
    deck: dict = {
        "deck_id": deck_id,
        "cards": [{"name": name, "count": 1, "partition": "Main"} for name in cards],
    }
    if archetype is not None:
        deck["archetype"] = archetype
    return deck


def _write_jsonl(path: Path, decks: list[dict]) -> None:
    path.write_text("".join(json.dumps(d) + "\n" for d in decks), encoding="utf-8")


@pytest.fixture()
def decks_dir(tmp_path: Path) -> Path:
    decks = tmp_path / "decks"
    decks.mkdir()
    # "Burn" has 3 decks, "Control" 2, "Rare" 1 (below min_decks=2).
    _write_jsonl(
        decks / "decks_magic.jsonl",
        [
            _deck("d1", "Burn", ["Lightning Bolt", "Chain Lightning", "Mountain"]),
            _deck("d2", "Burn", ["Lightning Bolt", "Chain Lightning", "Mountain"]),
            _deck("d3", "Burn", ["Lightning Bolt", "Fireblast"]),
            _deck("d4", "Control", ["Counterspell", "Island"]),
            _deck("d5", "Control", ["Counterspell", "Island"]),
            _deck("d6", "Rare", ["Counterbalance"]),
            _deck("d7", "Other", ["Lightning Bolt"]),  # provider bucket, not an archetype
            _deck("d8", None, ["Lightning Bolt"]),  # unlabelled
        ],
    )
    # Same deck shipped in a second export: counted once.
    _write_jsonl(
        decks / "decks_magic_goldfish.jsonl",
        [_deck("d1", "Burn", ["Lightning Bolt", "Chain Lightning", "Mountain"])],
    )
    # A game whose deck files carry no archetype field at all.
    _write_jsonl(decks / "decks_pokemon.jsonl", [_deck("p1", None, ["Pikachu"])])
    return decks


def _build(game: str, decks_dir: Path, out_root: Path, **overrides):
    params = {
        "decks_dir": decks_dir,
        "out_root": out_root,
        "min_decks": 2,
        "staple_threshold": 0.5,
        "max_partners": 1,
    }
    params.update(overrides)
    return _producer().build_game(game, **params)


def test_producer_writes_deterministic_artefacts(decks_dir: Path, tmp_path: Path) -> None:
    out_root = tmp_path / "signals"
    manifest = _build("magic", decks_dir, out_root)

    assert manifest["status"] == "built"
    assert manifest["decks"]["duplicate_deck_ids"] == 1
    assert manifest["decks"]["placeholder"] == 1
    assert manifest["archetypes"] == {
        "archetypes_seen": 3,
        "archetypes_kept": 2,
        "decks_in_kept_archetypes": 5,
    }

    staples = json.loads((out_root / "magic" / "archetype_staples.json").read_text())
    assert staples == {
        "Chain Lightning": {"Burn": 0.666667},
        "Counterspell": {"Control": 1.0},
        "Island": {"Control": 1.0},
        "Lightning Bolt": {"Burn": 1.0},
        "Mountain": {"Burn": 0.666667},
    }

    # Capped to max_partners=1; ties break on the partner name, not dict order.
    cooccurrence = json.loads((out_root / "magic" / "archetype_cooccurrence.json").read_text())
    assert cooccurrence["Lightning Bolt"] == {"Chain Lightning": 0.666667}

    first = dict(manifest["outputs"])
    rebuilt = _build("magic", decks_dir, out_root)
    assert rebuilt["outputs"] == first
    for name, info in first.items():
        digest = hashlib.sha256((out_root / "magic" / name).read_bytes()).hexdigest()
        assert info["sha256"] == digest


def test_a_game_without_archetype_labels_is_reported_as_missing(
    decks_dir: Path, tmp_path: Path
) -> None:
    out_root = tmp_path / "signals"
    (out_root / "pokemon").mkdir(parents=True)
    stale = out_root / "pokemon" / "archetype_staples.json"
    stale.write_text("{}")

    manifest = _build("pokemon", decks_dir, out_root)

    assert manifest["status"] == "no_source_data"
    assert "outputs" not in manifest
    assert not stale.exists(), "stale artefacts must not keep a game looking covered"
    assert (out_root / "pokemon" / "archetype_signal.manifest.json").exists()

    status = load_signals_to_state(
        SimpleNamespace(text_embedder=None, visual_embedder=None),
        signals_dir=out_root / "pokemon",
        skip_embedders=True,
    )
    assert status["archetype"] is False


def test_loader_reports_archetype_loaded_and_feeds_the_similarity(
    decks_dir: Path, tmp_path: Path
) -> None:
    out_root = tmp_path / "signals"
    _build("magic", decks_dir, out_root)

    state = SimpleNamespace(text_embedder=None, visual_embedder=None)
    status = load_signals_to_state(state, signals_dir=out_root / "magic", skip_embedders=True)

    assert status == {"text_embedder": False, "visual_embedder": False, "archetype": True}
    assert state.archetype_staples["Lightning Bolt"] == {"Burn": 1.0}
    assert (
        archetype_similarity(
            "Lightning Bolt",
            "Chain Lightning",
            state.archetype_staples,
            state.archetype_cooccurrence,
        )
        > 0.0
    )


def test_shipped_artefacts_match_their_recorded_hashes() -> None:
    """Local stack check: the built artefacts (git-ignored) match their manifest."""
    root = PROJECT_ROOT / "experiments" / "signals"
    manifests = sorted(root.glob("*/archetype_signal.manifest.json"))
    if not manifests:
        pytest.skip("archetype artefacts not built here; run build_archetype_signal.py")

    assert len(manifests) == 3
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text())
        assert manifest["status"] == "built"
        for name, info in manifest["outputs"].items():
            digest = hashlib.sha256((manifest_path.parent / name).read_bytes()).hexdigest()
            assert digest == info["sha256"]


def test_startup_line_reports_coverage_and_weight() -> None:
    """The line must not say a zero-weight signal is part of the blend."""
    from ml.api.api import _describe_loaded_signals

    loaded_state = SimpleNamespace(
        fusion_default_weights=None,  # default weights: archetype = 0.0
        archetype_staples={"Lightning Bolt": {"Burn": 1.0}},
        card_attrs=None,
        card_metadata={"Lightning Bolt": {}, "Counterspell": {}, "Island": {}},
    )
    line = _describe_loaded_signals(
        "magic",
        {"text_embedder": True, "visual_embedder": True, "archetype": True},
        loaded_state,
    )
    assert line == (
        "Game=magic signals: 3/3 loaded. "
        "Available=text_embedder, visual_embedder, archetype Missing=none "
        "Unweighted=archetype ArchetypeCards=1/3"
    )


def test_startup_line_reports_a_missing_archetype_plainly() -> None:
    from ml.api.api import _describe_loaded_signals

    state = SimpleNamespace(
        fusion_default_weights=None,
        archetype_staples=None,
        card_attrs=None,
        card_metadata={"Lightning Bolt": {}},
    )
    line = _describe_loaded_signals(
        "pokemon",
        {"text_embedder": True, "visual_embedder": True, "archetype": False},
        state,
    )
    assert line == (
        "Game=pokemon signals: 2/3 loaded. "
        "Available=text_embedder, visual_embedder Missing=archetype Unweighted=none"
    )
