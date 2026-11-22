import runpy
from pathlib import Path
from types import SimpleNamespace

from ml.utils import paths


def test_inventory_distinguishes_missing_empty_directory_and_populated(tmp_path, monkeypatch):
    check = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/validation/validate_all.py")
    )
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data/processed"
    data.mkdir(parents=True)
    optional = data / "decks_all_final.jsonl"
    monkeypatch.setattr(
        paths,
        "PATHS",
        SimpleNamespace(
            decks_all_final=optional,
            pairs_large=data / "pairs_large.csv",
            card_attributes=data / "card_attributes_enriched.csv",
        ),
    )
    (data / "pairs_large.csv").mkdir()
    (data / "pairs_multi_game.csv").touch()
    (data / "card_attributes_enriched.csv").write_text("name\n")
    decks = data / "decks_pokemon.jsonl"
    result = check["ValidationResult"]()
    check["validate_data_files"](result)
    assert [r["check"] for r in result.warnings] == ["Deck file: decks_all_final.jsonl"]
    assert {r["reason"] for r in result.failed} == {
        "Expected a regular file",
        "File is empty",
        "File not found",
    }
    assert [r["check"] for r in result.passed] == ["Data file: card_attributes_enriched.csv"]
    optional.touch()
    decks.write_text("{}\n")
    result = check["ValidationResult"]()
    check["validate_data_files"](result)
    assert not result.warnings
    assert any(
        r["check"] == "Deck file: decks_all_final.jsonl" and r["reason"] == "File is empty"
        for r in result.failed
    )
    assert any(r["check"] == "Deck file: decks_pokemon.jsonl" for r in result.passed)
