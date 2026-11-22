"""The offline enrichment check runs from a fresh checkout, without API credentials."""

import json
import subprocess
import sys
from pathlib import Path

from ..enrichment.card_market_data import MarketDataManager


def test_enrichment_script_runs_outside_repo(tmp_path):
    script = Path(__file__).resolve().parents[3] / "scripts" / "test_enrichment_pipeline.py"
    result = subprocess.run(
        [sys.executable, "-I", "-O", str(script)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert [line for line in result.stdout.splitlines() if line.startswith("Passed:")] == [
        "Passed: Scryfall fixture pricing",
        "Passed: Pokémon functional tags",
        "Passed: Yu-Gi-Oh! functional tags",
    ]


def test_prices_after_first_thousand_files_and_malformed_record(tmp_path, capsys):
    # The old loader silently truncated the directory at 1000 entries.
    for i in range(1000):
        (tmp_path / f"{i:04}.json").write_text("{}")
    (tmp_path / "bad.json").write_text("{")
    (tmp_path / "last.json").write_text(json.dumps({"name": "Last", "prices": {"usd": "0.00"}}))
    manager = MarketDataManager(tmp_path)
    assert "bad.json" in capsys.readouterr().err
    assert manager.get_price("Last").has_price
    assert manager.get_deck_price({"Last": 2})["coverage"] == "1/1"
    manager.analyze_price_distribution()
    assert "Median: $0.00" in capsys.readouterr().out
