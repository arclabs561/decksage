import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_script(name, *args, cwd):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
    )


def test_dataset_validator_checks_supplied_evidence(tmp_path):
    attrs = tmp_path / "attrs.csv"
    attrs.write_text("name\nA\nB\n")
    pairs = tmp_path / "pairs.csv"
    queries = tmp_path / "queries.json"
    queries.write_text('{"queries":{"A":{}}}')
    validate = lambda *args: run_script(
        "validation/validate_datasets.py", "--attributes", attrs, *args, cwd=tmp_path
    )
    assert validate("--test-set", queries).returncode == 0
    assert validate("--pairs", pairs).returncode != 0
    pairs.write_text("NAME_1,NAME_2\nA,B\n")
    assert validate("--pairs", pairs).returncode == 0
    for body in (
        "NAME_1,NAME_2\n",
        "NAME_1,NAME_2\nA,C\n",
        "NAME_1,NAME_2\nA,B\nB,A\n",
        "x,y\n1,2\n",
    ):
        pairs.write_text(body)
        assert validate("--pairs", pairs).returncode != 0
    queries.write_text('{"queries":{}}')
    assert validate("--test-set", queries).returncode != 0


def test_duplicate_annotations_fail_the_command(tmp_path):
    pairs = tmp_path / "pairs.json"
    pairs.write_text('[["A","B"]]')
    validate = lambda: run_script(
        "validation/validate_annotations.py", "--pairs", pairs, cwd=tmp_path
    )
    assert validate().returncode == 0
    pairs.write_text('[["A","B"],["B","A"]]')
    result = validate()
    assert result.returncode != 0 and "uplicate" in result.stdout


def test_precision_and_rank_on_labeled_queries(tmp_path):
    evaluate = runpy.run_path(str(ROOT / "scripts/evaluate_instruction_embeddings.py"))[
        "evaluate_on_test_set"
    ]
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps({"queries": {"query": {"relevant": ["hit"], "irrelevant": ["miss"]}}})
    )

    class Ranker:
        def most_similar(self, query, candidates, **opts):
            assert candidates == ["hit", "miss"]
            return [("miss", 0.9), ("hit", 0.8)]

    metrics = evaluate(Ranker(), path)
    assert metrics["p_at_10"] == 0.1
    assert metrics["mrr"] == 0.5
    path.write_text('{"queries":{"query":{}}}')
    with pytest.raises(ValueError, match="labeled"):
        evaluate(Ranker(), path)


def test_missing_observations_cannot_produce_a_confidence_interval():
    from ml.evaluation.confidence_intervals_integration import (
        add_confidence_intervals_to_evaluation_results as intervals,
    )

    assert "mrr_ci" not in intervals({"mrr": 0.4})
    result = intervals({"mrr": 0.4}, {"a": {"mrr": 0.4}, "b": {"mrr": 0.4}})
    assert result["mrr_ci"]["lower"] == result["mrr_ci"]["upper"] == 0.4


def test_visual_wrapper_runs_all_checks_and_preserves_failure(tmp_path):
    import os

    fake = tmp_path / "python3"
    fake.write_text(
        '#!/bin/sh\necho invocation >> "$LOG"\ncase "$*" in *integration.py*) exit 7;; esac\n'
    )
    fake.chmod(0o755)
    log = tmp_path / "calls"
    runner = ROOT / "scripts/testing/run_visual_embeddings_tests.sh"
    result = subprocess.run(
        ["bash", str(runner)],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(tmp_path) + ":" + os.environ["PATH"], "LOG": str(log)},
    )
    assert result.returncode == 7
    assert log.read_text().splitlines() == ["invocation"] * 5
