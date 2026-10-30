"""Bucket audit follows annotate_diverse_pairs.py's consensus-score thresholds."""

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluation/dataset_diagnostics.py"


@pytest.fixture
def diagnostics(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("dataset_diagnostics", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    (tmp_path / "test_sets").mkdir()
    return module


def write_test_set(diagnostics, buckets):
    entry = {bucket: [candidate for candidate, _ in pairs] for bucket, pairs in buckets.items()}
    entry["annotations"] = [
        {"candidate": candidate, "similarity_score": score}
        for pairs in buckets.values()
        for candidate, score in pairs
    ]
    path = diagnostics.DATA_DIR / "test_sets/annotated_magic_v2.json"
    path.write_text(json.dumps({"queries": {"query": entry}}))


def test_threshold_boundaries(diagnostics):
    write_test_set(
        diagnostics,
        {
            "highly_relevant": [("top", 1.0), ("high", 0.70)],
            "relevant": [("relevant", 0.50)],
            "somewhat_relevant": [("somewhat", 0.30)],
            "marginally_relevant": [("marginal", 0.15)],
            "irrelevant": [("bottom", 0.0), ("below", 0.149)],
        },
    )
    result = diagnostics.diagnose_bucket_consistency("magic")
    assert result["checked"] == 7
    assert result["contradictions"] == 0
    assert result["warnings"] == []


def test_contradictions_include_irrelevant_and_invalid_range(diagnostics):
    write_test_set(
        diagnostics,
        {
            "highly_relevant": [("low", 0.69), ("overflow", 1.005)],
            "relevant": [("high", 0.70)],
            "somewhat_relevant": [("relevant", 0.50)],
            "marginally_relevant": [("somewhat", 0.30)],
            "irrelevant": [("marginal", 0.15), ("negative", -0.1)],
        },
    )
    result = diagnostics.diagnose_bucket_consistency("magic")
    assert result["checked"] == result["contradictions"] == 7
    assert len(result["examples"]) == 5
    assert "7 of 7" in result["warnings"][0]


def test_unscored_pairs_are_not_compared(diagnostics):
    write_test_set(diagnostics, {"relevant": [("unscored", None)]})
    result = diagnostics.diagnose_bucket_consistency("magic")
    assert result["checked"] == result["contradictions"] == 0


def test_missing_test_set_is_explicit(diagnostics):
    result = diagnostics.diagnose_bucket_consistency("pokemon")
    assert result["checked"] == 0
    assert "missing annotated_pokemon_v2.json" in result["warnings"][0]


def test_warning_reaches_full_report(diagnostics, monkeypatch, capsys):
    write_test_set(diagnostics, {"irrelevant": [("high", 0.9)]})
    for name in ("diagnose_edges", "diagnose_annotations", "diagnose_decks", "diagnose_metadata"):
        monkeypatch.setattr(diagnostics, name, lambda game: {})
    result = diagnostics.run_diagnostics("magic")
    assert result["bucket_consistency"]["contradictions"] == 1
    assert result["warnings"] == result["bucket_consistency"]["warnings"]
    assert "1 of 1 bucketed pairs" in capsys.readouterr().out


def test_diagnostics_flag_failed_and_unprovenanced_judgments(diagnostics):
    path = diagnostics.DATA_DIR / "test_sets/annotated_magic_v2.json"
    path.write_text(
        json.dumps(
            {
                "queries": {
                    "q": {
                        "annotations": [
                            {"candidate": "failed", "error": True, "similarity_score": 0.9},
                            {
                                "candidate": "valid",
                                "similarity_score": 0.3,
                                "_provenance": {"model": "judge"},
                            },
                        ]
                    }
                }
            }
        )
    )
    result = diagnostics.diagnose_annotations("magic")
    assert result["test_set"]["ineligible_judgments"] == 1
    assert result["test_set"]["missing_provenance"] == 1
    assert any("ineligible" in warning.lower() for warning in result["warnings"])


def test_ineligible_gate_fails_on_bad_or_missing_test_set(diagnostics, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["diagnostics", "--fail-ineligible"])
    monkeypatch.setattr(
        diagnostics,
        "run_diagnostics",
        lambda game, as_json: {"annotations": {"test_set": {"ineligible_judgments": 1}}},
    )
    assert diagnostics.main() == 1
    monkeypatch.setattr(diagnostics, "run_diagnostics", lambda game, as_json: {"annotations": {}})
    assert diagnostics.main() == 1
    monkeypatch.setattr(
        diagnostics,
        "run_diagnostics",
        lambda game, as_json: {"annotations": {"test_set": {"ineligible_judgments": 0}}},
    )
    assert diagnostics.main() == 0
