"""Review candidates are reproducible and blind to prior judge scores."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def test_sample_is_blind_and_excludes_invalid_or_contextless_records():
    path = Path(__file__).resolve().parents[1] / "scripts/annotation/prepare_human_review.py"
    spec = importlib.util.spec_from_file_location("prepare_review", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = {
        "queries": {
            "A": {
                "annotations": [
                    {"candidate": "B", "functional_score": 0.8},
                    {"candidate": "C", "functional_score": 0.7, "error": True},
                    {"candidate": "D", "functional_score": 0.1},
                ]
            }
        }
    }
    contexts = {"A": "rules A", "B": "rules B", "C": "rules C"}
    review, ledger = module.sample_game(data, "magic", contexts, seed=42)
    assert (review, ledger) == module.sample_game(data, "magic", contexts, seed=42)
    assert len(review) == 1
    assert review[0]["candidate"] == "B"
    assert review[0]["human_score"] is None
    assert "judge_score" not in review[0]
    assert ledger[0]["judge_score"] == 0.8


def test_cli_separates_blinded_review_and_selection_ledger(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "data"
    (source / "test_sets").mkdir(parents=True)
    (source / "processed").mkdir()
    for game in ("magic", "pokemon", "yugioh"):
        (source / "test_sets" / f"annotated_{game}_v2.json").write_text(
            json.dumps(
                {"queries": {"A": {"annotations": [{"candidate": "B", "functional_score": 0.8}]}}}
            )
        )
        (source / "processed" / f"card_attributes_{game}_enriched.csv").write_text(
            "name,type,oracle_text\nA,Creature,Rule A\nB,Creature,Rule B\n"
        )
    output = tmp_path / "review"
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts/annotation/prepare_human_review.py"),
            "--data-dir",
            str(source),
            "--output-dir",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    review = json.loads((output / "review.json").read_text())
    ledger = json.loads((output / "private_selection_ledger.json").read_text())
    assert len(review) == len(ledger["records"]) == 3
    assert all(item["human_score"] is None and "judge_score" not in item for item in review)
    assert all(item["judge_score"] == 0.8 for item in ledger["records"])
