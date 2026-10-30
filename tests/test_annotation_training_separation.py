"""Training sources cannot silently consume reserved evaluation pairs."""

import importlib.util
import json
from pathlib import Path

import pytest


def load_script(relative):
    path = Path(__file__).resolve().parents[1] / relative
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_graph_export_excludes_bucket_only_pairs_and_does_not_infer_function(tmp_path, monkeypatch):
    module = load_script("scripts/data_processing/export_annotation_edges.py")
    monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    (tmp_path / "test_sets").mkdir()
    (tmp_path / "annotations").mkdir()
    (tmp_path / "test_sets/annotated_magic_v2.json").write_text(
        json.dumps({"queries": {"Q": {"relevant": ["held-out"]}}})
    )
    (tmp_path / "annotations/magic_2000_v4.json").write_text(
        json.dumps(
            {
                "labels": [
                    {"card1": "held-out", "card2": "Q", "functional_score": 0.9},
                    {"card1": "A", "card2": "B", "similarity_score": 0.9},
                    {"card1": "C", "card2": "D", "functional_score": 0.8},
                ]
            }
        )
    )
    result = module.export_edges("magic")
    assert result["excluded_eval"] == 1
    assert (tmp_path / "graphs/magic_annotation_edges.edg").read_text() == "C\tD\t4.0000\n"


def test_graph_export_requires_evaluation_snapshot(tmp_path, monkeypatch):
    module = load_script("scripts/data_processing/export_annotation_edges.py")
    monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        module.export_edges("magic")
    with pytest.raises(ValueError):
        module.export_edges("magic", exclude_eval=False)
    (tmp_path / "test_sets").mkdir()
    (tmp_path / "test_sets/annotated_magic_v2.json").write_text('{"queries": {}}')
    with pytest.raises(ValueError, match="empty queries"):
        module.export_edges("magic")


def test_legacy_reranker_refuses_evaluation_training():
    module = load_script("scripts/training/train_reranker.py")
    with pytest.raises(RuntimeError, match="evaluation set"):
        module.load_pairs("magic")


@pytest.mark.parametrize(
    ("script", "loader"),
    [
        ("train_box_v2", "load_annotation_pairs"),
        ("train_card_containment", "load_upgrade_pairs"),
        ("train_cone_upgrades", "load_upgrade_pairs"),
    ],
)
def test_containment_trainers_refuse_evaluation_training(script, loader):
    module = load_script(f"scripts/training/{script}.py")
    with pytest.raises(RuntimeError, match="evaluation judgments"):
        getattr(module, loader)("magic")
