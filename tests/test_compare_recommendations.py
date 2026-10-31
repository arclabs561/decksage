"""The pre-registered recommendation harness decides, refuses, and holds sets fixed.

Synthetic fixtures only: a tiny judged set is built in a per-query subspace, so a
card from one query has exactly zero similarity to another query. That makes the
two arms' expected behaviour arithmetic rather than empirical -- the "candidate"
arms in these fixtures are deliberately, mechanically better or identical.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
SCRIPT = PROJECT_ROOT / "scripts" / "evaluation" / "compare_recommendations.py"

FILLERS = 8
BASELINE_COSINES = {"rel_a": 0.10, "rel_b": 0.12, "irr_a": 0.90, "irr_b": 0.88}
CANDIDATE_COSINES = {"rel_a": 0.95, "rel_b": 0.90, "irr_a": 0.20, "irr_b": 0.15}
PASSING_GATE = {
    "status": "passed",
    "summary": "synthetic.json: no structural contradictions in 0 records",
    "examined": 0,
    "counts": {},
    "blocking": 0,
    "skipped": None,
}


@pytest.fixture(scope="module")
def harness():
    """Load the harness script as a module (it lives outside the package)."""
    spec = importlib.util.spec_from_file_location("compare_recommendations", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Dataclass processing resolves string annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def card_names(index: int) -> list[str]:
    names = [
        f"Query {index}",
        f"Rel {index} A",
        f"Rel {index} B",
        f"Irr {index} A",
        f"Irr {index} B",
    ]
    names += [f"Fill {index} {filler}" for filler in range(FILLERS)]
    return names


def embedding_matrix(n_queries: int, cosines: dict[str, float]) -> np.ndarray:
    """One axis pair per query; the query sits on the first axis.

    A card's cosine to its own query is set exactly, and its cosine to every
    other query is exactly zero because the axes do not overlap.
    """
    dim = 2 * n_queries
    matrix = np.zeros((n_queries * len(card_names(0)), dim), dtype=np.float32)
    for index in range(n_queries):
        offset = index * len(card_names(0))
        axis = 2 * index
        targets = [1.0] + [cosines[key] for key in ("rel_a", "rel_b", "irr_a", "irr_b")]
        targets += [0.55 + 0.01 * filler for filler in range(FILLERS)]
        for position, target in enumerate(targets):
            angle = np.arccos(target)
            matrix[offset + position, axis] = np.cos(angle)
            matrix[offset + position, axis + 1] = np.sin(angle)
    return matrix


def write_world(tmp_path: Path, n_queries: int) -> dict[str, Path]:
    """A judged test set plus a baseline and a candidate embedding artefact."""
    from ml.similarity.named_vectors import NamedVectors

    names: list[str] = []
    for index in range(n_queries):
        names.extend(card_names(index))

    baseline = tmp_path / "baseline.npz"
    candidate = tmp_path / "candidate.npz"
    NamedVectors(names, embedding_matrix(n_queries, BASELINE_COSINES)).save(baseline)
    NamedVectors(names, embedding_matrix(n_queries, CANDIDATE_COSINES)).save(candidate)

    queries = {}
    for index in range(n_queries):
        query, rel_a, rel_b, irr_a, irr_b = card_names(index)[:5]
        queries[query] = {
            "annotations": [
                {"candidate": rel_a, "functional_score": 0.9, "task": "substitute"},
                {"candidate": rel_b, "functional_score": 0.8, "task": "substitute"},
                {"candidate": irr_a, "functional_score": 0.05, "task": "substitute"},
                {"candidate": irr_b, "functional_score": 0.02, "task": "substitute"},
            ]
        }
    test_set = tmp_path / "annotated_magic_v2.json"
    test_set.write_text(
        json.dumps(
            {
                "version": "synthetic-fixture",
                "game": "magic",
                "num_queries": n_queries,
                "queries": queries,
            }
        )
    )
    return {"test_set": test_set, "baseline": baseline, "candidate": candidate}


def run_harness(
    harness,
    monkeypatch,
    tmp_path: Path,
    *,
    n_queries: int,
    sources: str,
    weights: str | None = None,
    label: str,
    extra: list[str] | None = None,
    sparse_ok: bool = True,
) -> tuple[int, Path, str]:
    world = write_world(tmp_path, n_queries)
    monkeypatch.setattr(harness, "screen", lambda *args, **kwargs: dict(PASSING_GATE))
    output = tmp_path / f"{label}.json"
    argv = [
        "--game",
        "magic",
        "--test-set",
        str(world["test_set"]),
        "--baseline",
        str(world["baseline"]),
        "--candidate-sources",
        sources.format(base=world["baseline"], candidate=world["candidate"]),
        "--output",
        str(output),
        "--depth",
        "20",
    ]
    if weights is not None:
        argv += ["--candidate-weights", weights]
    if sparse_ok:
        # The fixture judges 4 of 20 candidates; the coverage gate is exercised
        # by its own test, not by every verdict test.
        argv += ["--allow-sparse-labels"]
    code = harness.main(argv + list(extra or []))
    return code, output, label


def expected_ndcg_first_ranks(ranked_relevance: list[float]) -> float:
    """nDCG@10 for a ranking whose top slots carry exactly these relevances.

    The ideal keeps every judged slot inside k, including judged-but-unranked
    cards, so a perfect top-2 is not 1.0 when four pairs were judged.
    """
    judged = [0.9, 0.8, 0.05, 0.02]
    discounts = np.log2(np.arange(2, 11))
    ideal = sum(value / discount for value, discount in zip(judged, discounts))
    achieved = sum(value / discount for value, discount in zip(ranked_relevance, discounts))
    return achieved / ideal


def test_better_candidate_arm_reports_candidate_better(harness, monkeypatch, tmp_path, capsys):
    code, output, _ = run_harness(
        harness,
        monkeypatch,
        tmp_path,
        n_queries=32,
        sources="{base},{candidate}",
        weights="0.3,0.7",
        label="better",
    )

    assert code == 0
    result = json.loads(output.read_text())
    assert result["verdict"] == "candidate_better"
    assert result["queries_usable"] == 32
    assert result["candidate_set_assertion"]["identical"] is True
    assert len(result["per_query"]) == 32
    # The fixture makes the candidate arm rank both relevant cards first on every
    # query and the baseline arm rank only the two judged-irrelevant ones, so the
    # per-query scores are arithmetic rather than empirical.
    baseline_expected = expected_ndcg_first_ranks([0.05, 0.02])
    candidate_expected = expected_ndcg_first_ranks([0.9, 0.8])
    assert result["summary"]["mean"]["baseline"]["ndcg_at_10"] == pytest.approx(
        baseline_expected, abs=1e-9
    )
    assert result["summary"]["mean"]["candidate"]["ndcg_at_10"] == pytest.approx(
        candidate_expected, abs=1e-9
    )
    assert result["summary"]["mean_delta"]["ndcg_at_10"] == pytest.approx(
        candidate_expected - baseline_expected, abs=1e-9
    )
    assert result["summary"]["mean_delta"]["recall_at_10"] == pytest.approx(1.0)
    assert result["bootstrap"]["ndcg_at_10"]["ci_low"] > 0
    assert result["test_set"]["sha256"] == harness.sha256_file(tmp_path / "annotated_magic_v2.json")
    assert result["command_line"].startswith(
        "uv run scripts/evaluation/compare_recommendations.py --game magic"
    )
    assert "candidate set fixed: PASS" in capsys.readouterr().out


def test_identical_arms_report_no_difference(harness, monkeypatch, tmp_path):
    code, output, _ = run_harness(
        harness,
        monkeypatch,
        tmp_path,
        n_queries=32,
        sources="{base}",
        label="identical",
    )

    assert code == 0
    result = json.loads(output.read_text())
    assert result["verdict"] == "no_difference"
    assert result["queries_usable"] == 32
    assert result["candidate_set_assertion"]["identical"] is True
    assert all(record["delta"]["ndcg_at_10"] == 0.0 for record in result["per_query"])
    interval = result["bootstrap"]["ndcg_at_10"]
    assert (interval["ci_low"], interval["ci_high"]) == (0.0, 0.0)
    assert interval["excludes_zero"] is False


def test_sparse_labels_are_refused_without_an_override(harness, monkeypatch, tmp_path, capsys):
    code, output, _ = run_harness(
        harness,
        monkeypatch,
        tmp_path,
        n_queries=32,
        sources="{base}",
        label="sparse",
        sparse_ok=False,
    )

    assert code != 0
    assert not output.exists()
    assert "median judged pool" in capsys.readouterr().err


def test_below_query_floor_reports_insufficient_evidence(harness, monkeypatch, tmp_path, capsys):
    code, output, _ = run_harness(
        harness,
        monkeypatch,
        tmp_path,
        n_queries=10,
        sources="{base},{candidate}",
        weights="0.3,0.7",
        label="floor",
    )

    assert code == 0
    result = json.loads(output.read_text())
    assert result["verdict"] == "insufficient_evidence"
    assert result["queries_usable"] == 10
    # The interval still excludes zero; the floor is what withholds the verdict.
    assert result["bootstrap"]["ndcg_at_10"]["ci_low"] > 0
    assert "below the pre-registered floor of 30" in result["verdict_reason"]
    assert "insufficient_evidence" in capsys.readouterr().out


def test_screen_turns_a_gate_refusal_into_a_harness_refusal(harness, monkeypatch):
    def refuse(*args, **kwargs):
        raise ValueError("annotated_magic_v2.json carries 3 structurally contradictory judgments")

    monkeypatch.setattr("ml.evaluation.label_gate.gate_or_refuse", refuse)

    with pytest.raises(harness.HarnessRefusal, match="structurally contradictory"):
        harness.screen(Path("annotated_magic_v2.json"), False, None)


def test_blocking_gate_refuses_and_writes_nothing(harness, monkeypatch, tmp_path, capsys):
    world = write_world(tmp_path, 32)

    def blocked(*args, **kwargs):
        raise harness.HarnessRefusal(
            "annotated_magic_v2.json carries 3 structurally contradictory judgments"
        )

    monkeypatch.setattr(harness, "screen", blocked)
    output = tmp_path / "blocked.json"

    code = harness.main(
        [
            "--game",
            "magic",
            "--test-set",
            str(world["test_set"]),
            "--baseline",
            str(world["baseline"]),
            "--candidate-sources",
            str(world["candidate"]),
            "--output",
            str(output),
        ]
    )

    assert code == 2
    assert not output.exists()
    assert "refused" in capsys.readouterr().err


def test_dry_run_resolves_without_scoring_or_writing(harness, monkeypatch, tmp_path, capsys):
    world = write_world(tmp_path, 32)
    monkeypatch.setattr(harness, "screen", lambda *args, **kwargs: dict(PASSING_GATE))
    output = tmp_path / "dry.json"

    code = harness.main(
        [
            "--game",
            "magic",
            "--test-set",
            str(world["test_set"]),
            "--baseline",
            str(world["baseline"]),
            "--candidate-sources",
            str(world["candidate"]),
            "--output",
            str(output),
            "--dry-run",
        ]
    )

    assert code == 0
    assert not output.exists()
    captured = capsys.readouterr().out
    assert "usable queries 32 of 32" in captured
    assert "dry run: nothing scored" in captured


def test_diverging_candidate_sets_are_caught(harness):
    candidates = ("A", "B")
    digest = harness.candidates_digest(candidates)
    observation = {
        "query": "Q",
        "candidates": candidates,
        "retrieved_digest": digest,
        "arms": {
            "baseline": {
                "digest": digest,
                "keys_match": True,
                "count": 2,
                "list_object": 1,
                "relevance_digest": "rels",
            },
            "candidate": {
                "digest": harness.candidates_digest(("B", "A")),
                "keys_match": False,
                "count": 2,
                "list_object": 2,
                "relevance_digest": "rels",
            },
        },
    }

    with pytest.raises(harness.HarnessRefusal, match="candidate sets are not fixed"):
        harness.assert_fixed_candidate_sets([observation])


def test_verdict_floor_precedes_the_interval(harness):
    interval = {"ci_low": 0.4, "ci_high": 0.6}
    verdict, reason = harness.decide_verdict(12, 30, interval)

    assert verdict == "insufficient_evidence"
    assert "floor of 30" in reason
