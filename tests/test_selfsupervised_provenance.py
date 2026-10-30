"""Self-supervised pairs must retain their game and exclude evaluation pairs."""

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/training/{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generator_excludes_reversed_eval_pairs_and_records_provenance(tmp_path, monkeypatch):
    generator = load_script("generate_selfsupervised_pairs")
    monkeypatch.setattr(generator, "DATA_DIR", tmp_path)
    (tmp_path / "test_sets").mkdir()
    (tmp_path / "test_sets/annotated_magic_v2.json").write_text(
        json.dumps({"queries": {"B": {"annotations": [{"candidate": "A"}]}}})
    )
    cards = [
        {"name": name, "type_line": "Creature", "keywords": "Flying", "oracle_text": "Flying"}
        for name in ("A", "B", "C")
    ]
    monkeypatch.setattr(generator, "_load_cards", lambda game: cards)
    pairs = generator.generate_pairs("magic")
    assert pairs
    assert all({p["query"], p["candidate"]} != {"A", "B"} for p in pairs)
    assert all(p["game"] == "magic" and p["source"] == "card_attributes" for p in pairs)


def test_per_game_loader_rejects_unprovenanced_legacy_data(tmp_path, monkeypatch):
    trainer = load_script("train_e5_lora")
    monkeypatch.setattr(trainer, "DATA_DIR", tmp_path)
    (tmp_path / "training").mkdir()
    (tmp_path / "training/selfsupervised_pairs.json").write_text(
        json.dumps({"pairs": [{"query_text": "A", "candidate_text": "B", "score": 0.5}]})
    )
    with pytest.raises(SystemExit, match="game provenance"):
        trainer.load_training_data("magic")


def test_typed_training_filter_excludes_eval_pair_and_other_game(tmp_path):
    from ml.contracts.training_pairs import verified_pairs

    (tmp_path / "test_sets").mkdir()
    (tmp_path / "test_sets/annotated_magic_v2.json").write_text(
        json.dumps({"queries": {"A": {"annotations": [{"candidate": "B"}], "relevant": ["E"]}}})
    )
    base = {
        "source": "card_attributes",
        "task": "attribute_similarity",
        "query_text": "a",
        "candidate_text": "b",
        "score": 0.5,
    }
    rows = [
        {**base, "game": "magic", "query": "B", "candidate": "A"},
        {**base, "game": "magic", "query": "C", "candidate": "D"},
        {**base, "game": "pokemon", "query": "C", "candidate": "D"},
        {**base, "game": "magic", "query": "E", "candidate": "A"},
    ]
    assert verified_pairs(rows, tmp_path, ["magic"]) == [rows[1]]


def test_attribute_proxy_cannot_be_labeled_as_synergy(monkeypatch, capsys):
    import sys

    trainer = load_script("train_e5_lora")
    monkeypatch.setattr(sys, "argv", ["train_e5_lora.py", "--task", "synergy"])
    with pytest.raises(SystemExit):
        trainer.main()
    assert "attribute" in capsys.readouterr().err.lower()


def test_trainers_accept_explicit_curated_file_and_exclude_eval_pair(tmp_path, monkeypatch):
    (tmp_path / "test_sets").mkdir()
    (tmp_path / "test_sets/annotated_magic_v2.json").write_text(
        json.dumps({"queries": {"A": {"annotations": [{"candidate": "B"}]}}})
    )
    base = {
        "game": "magic",
        "source": "card_attributes",
        "task": "attribute_similarity",
        "query_text": "a",
        "candidate_text": "b",
        "score": 0.5,
    }
    pairs = [
        {**base, "query": "B", "candidate": "A"},
        {**base, "query": "C", "candidate": "D"},
    ]
    path = tmp_path / "curated.json"
    path.write_text(json.dumps({"pairs": pairs}))
    lora = load_script("train_e5_lora")
    cross = load_script("train_cross_encoder")
    e5 = load_script("finetune_e5")
    for module in (lora, cross, e5):
        monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    assert len(lora.load_training_data("magic", path)) == 1
    assert cross.load_selfsupervised_pairs(["magic"], path) == [pairs[1]]
    assert e5.load_pairs("selfsupervised", path) == [pairs[1]]
