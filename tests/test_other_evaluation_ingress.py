"""The contextual evaluators must not consume failed pseudo-judgments."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.mark.parametrize("script", ["eval_contextual", "sweep_contextual_weights"])
def test_loader_excludes_failed_judgments(script, tmp_path, monkeypatch, capsys):
    path = Path(__file__).resolve().parents[1] / "scripts" / "evaluation" / f"{script}.py"
    spec = importlib.util.spec_from_file_location(script, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    directory = tmp_path / "test_sets"
    directory.mkdir()
    source = {
        "queries": {
            "Q": {
                "annotations": [
                    {"candidate": "valid", "similarity_score": 0.8},
                    {"candidate": "failed", "similarity_score": 0.9, "error": True},
                ],
                "highly_relevant": ["valid", "failed"],
            }
        }
    }
    target = directory / "annotated_magic_v2.json"
    target.write_text(json.dumps(source))
    loaded = module.load_test_set("magic")
    assert loaded["queries"]["Q"]["highly_relevant"] == ["valid"]
    assert [ann["candidate"] for ann in loaded["queries"]["Q"]["annotations"]] == ["valid"]
    assert json.loads(target.read_text()) == source
    assert "Excluded 1" in capsys.readouterr().err
