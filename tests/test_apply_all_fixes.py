import json
from pathlib import Path
import subprocess
import sys


def test_deck_pipeline_preserves_last_good_export(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/apply_all_fixes.sh"
    src = tmp_path / "decks_all_unified.jsonl"
    source = {"deck_id": "fixture", "game": "magic", "format": "standard",
              "cards": [{"name": "Island", "partition": "Main", "count": 60}]}
    src.write_text(json.dumps(source) + "\n")
    subprocess.run(["bash", script, tmp_path], check=True)
    output = tmp_path / "decks_all_final.jsonl"
    good = output.read_bytes()
    assert json.loads(good)["deck_id"] == "fixture"
    src.write_text("invalid JSON\n")
    assert subprocess.run(["bash", script, tmp_path]).returncode != 0
    assert output.read_bytes() == good

def test_direct_validator_reports_missing_dependencies(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/validation/validate_exported_decks.py"
    source, output = tmp_path / "input.jsonl", tmp_path / "output.jsonl"
    source.write_text('{"deck_id":"fixture"}\n')
    run = subprocess.run([sys.executable, "-IS", script, "--input", source, "--output", output],
                         cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode != 0
    assert "pydantic" in run.stderr
    assert not output.exists()
