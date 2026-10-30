"""Regression for replacing a bucket-only label with a scored annotation."""

import importlib.util
import json
from pathlib import Path


def test_new_score_replaces_existing_bucket_membership(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/evaluation/fill_eval_holes.py"
    spec = importlib.util.spec_from_file_location("fill_eval_holes", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    test_dir = tmp_path / "test_sets"
    test_dir.mkdir()
    path = test_dir / "annotated_magic_v2.json"
    path.write_text(json.dumps({"queries": {"query": {"irrelevant": ["candidate"]}}}))

    assert (
        module.merge_into_test_set(
            "magic", [{"query": "query", "candidate": "candidate", "similarity_score": 0.8}]
        )
        == 1
    )
    query = json.loads(path.read_text())["queries"]["query"]
    assert query["highly_relevant"] == ["candidate"]
    assert query["irrelevant"] == []
