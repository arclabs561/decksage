"""Evaluation merges must not consume augmented training judgments."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def merge():
    path = Path(__file__).resolve().parents[1] / "scripts/annotation/annotation_convergence.py"
    spec = importlib.util.spec_from_file_location("annotation_convergence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.merge_annotations


@pytest.mark.parametrize(
    "marker",
    [
        {"synthetic": True},
        {"_provenance": {"augmentation": "swap"}},
        {"error": True},
        {"llm_model": "cosine_fallback"},
    ],
)
def test_synthetic_record_cannot_create_or_modify_evaluation_labels(merge, marker):
    original = {
        "queries": {"q": {"annotations": [{"candidate": "existing", "similarity_score": 0.2}]}}
    }
    rows = [
        {"query": "q", "candidate": "existing", "similarity_score": 0.9, **marker},
        {"query": "new", "candidate": "candidate", "similarity_score": 0.9, **marker},
    ]
    result, added, deduped = merge(original, rows)
    assert added == deduped == 0
    assert result["queries"]["q"]["annotations"][0]["similarity_score"] == 0.2
    assert "new" not in result["queries"]


def test_diverse_candidate_loader_rejects_augmentation(tmp_path, monkeypatch):
    import json

    path = Path(__file__).resolve().parents[1] / "scripts/annotation/annotate_diverse_pairs.py"
    spec = importlib.util.spec_from_file_location("annotate_diverse_pairs", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    (tmp_path / "annotations").mkdir()
    rows = [
        {"card1": "a", "card2": "b"},
        {"card1": "a", "card2": "c", "synthetic": True},
        {"card1": "a", "card2": "d", "_provenance": {"augmentation": "swap"}},
    ]
    (tmp_path / "annotations/diverse_pairs_magic.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )
    assert module.load_diverse_pairs("magic") == [rows[0]]


def test_consensus_tracks_contributors_and_field_specific_counts():
    path = Path(__file__).resolve().parents[1] / "scripts/annotation/annotate_diverse_pairs.py"
    spec = importlib.util.spec_from_file_location("diverse_consensus", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    rows = [
        {"candidate": "x", "similarity_score": 0.2, "functional_score": 0.2, "llm_model": "one"},
        {"candidate": "x", "similarity_score": 0.4, "llm_model": "two"},
        {"candidate": "x", "similarity_score": 0.6, "functional_score": 0.8, "llm_model": "three"},
    ]
    result = module.consensus_annotations(rows)[0]
    assert result["similarity_score"] == pytest.approx(0.4)
    assert result["functional_score"] == pytest.approx(0.5)
    assert result["n_annotators"] == 3
    assert [p["model"] for p in result["_provenance"]["contributors"]] == ["one", "two", "three"]


def test_curated_evaluation_removes_failed_fallback_and_its_bucket():
    from ml.contracts.annotations import curate_evaluation_data

    data = {
        "queries": {
            "q": {
                "annotations": [
                    {"candidate": "failed", "similarity_score": 0.9, "error": True},
                    {"candidate": "valid", "similarity_score": 0.8},
                ],
                "highly_relevant": ["failed", "valid"],
                "modes": {"failed": "substitution", "valid": "synergy"},
            }
        }
    }
    curated, removed = curate_evaluation_data(data)
    assert removed == 1
    assert curated["queries"]["q"]["annotations"] == [
        {"candidate": "valid", "similarity_score": 0.8}
    ]
    assert curated["queries"]["q"]["highly_relevant"] == ["valid"]
    assert curated["queries"]["q"]["modes"] == {"valid": "synergy"}
    assert len(data["queries"]["q"]["annotations"]) == 2


def test_scale_writer_does_not_bucket_failed_calls(monkeypatch):
    import asyncio

    path = Path(__file__).resolve().parents[1] / "scripts/annotation/scale_annotations.py"
    spec = importlib.util.spec_from_file_location("scale_annotations", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    async def annotate(agent, query, card, sim, game, **kwargs):
        return {"query": query, "candidate": card, "relevance": "highly_relevant", "error": True}

    monkeypatch.setattr(module, "annotate_pair_with_mode", annotate)
    result = asyncio.run(module.annotate_query(None, "q", [("x", 0.9)]))
    assert result["annotations"] == []
    assert result["highly_relevant"] == []
