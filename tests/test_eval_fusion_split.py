"""Held-out query split for the fusion evaluator.

Covers `scripts/evaluation/eval_fusion.py`: the seed-13 query partition shared
with `calibrate_fusion_weights.py`, its 80/20 sizes, and split metadata that
does not infer model independence from the partition alone.
"""

import importlib.util
import json
import random
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluation" / "eval_fusion.py"


@pytest.fixture(scope="module")
def evaluator():
    """Load the evaluator script as a module (it lives outside the package)."""
    spec = importlib.util.spec_from_file_location("eval_fusion", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_names(n: int) -> list[str]:
    return [f"Query {i:03d}" for i in range(n)]


# --- partition properties ---------------------------------------------------


def test_split_defaults_match_calibration_seed(evaluator):
    assert evaluator.SPLIT_SEED == 13
    assert evaluator.SPLIT_CHOICES == ("all", "train", "holdout")


def test_train_and_holdout_are_disjoint_and_exhaustive(evaluator):
    names = synthetic_names(50)
    train = evaluator.split_query_names(names, "train")
    holdout = evaluator.split_query_names(names, "holdout")

    assert set(train).isdisjoint(holdout)
    assert sorted(train + holdout) == sorted(names)
    assert len(train) + len(holdout) == len(names)
    # No duplicates on either side.
    assert len(set(train)) == len(train)
    assert len(set(holdout)) == len(holdout)


def test_same_seed_is_deterministic_regardless_of_input_order(evaluator):
    names = synthetic_names(50)
    assert evaluator.split_query_names(names, "train") == evaluator.split_query_names(
        names, "train"
    )
    # The partition is over sorted names, so query-dict insertion order is
    # irrelevant.
    shuffled = names[:]
    random.Random(99).shuffle(shuffled)
    assert evaluator.split_query_names(shuffled, "train") == evaluator.split_query_names(
        names, "train"
    )
    assert evaluator.split_query_names(shuffled, "holdout") == evaluator.split_query_names(
        names, "holdout"
    )


def test_partition_matches_calibrate_fusion_weights(evaluator):
    # calibrate_fusion_weights.py: sort names, shuffle with Random(13), fit on
    # names[:int(0.8 * n)], report on the rest. The evaluator must select the
    # exact same sets or its "holdout" is not the calibrator's holdout.
    names = synthetic_names(37)
    reference = sorted(names)
    random.Random(13).shuffle(reference)
    split_at = int(len(reference) * 0.8)

    assert evaluator.split_query_names(names, "train") == reference[:split_at]
    assert evaluator.split_query_names(names, "holdout") == reference[split_at:]


@pytest.mark.parametrize("n", [10, 25, 50, 100, 101])
def test_split_sizes_follow_eighty_twenty_rule(evaluator, n):
    names = synthetic_names(n)
    train = evaluator.split_query_names(names, "train")
    holdout = evaluator.split_query_names(names, "holdout")

    assert len(train) == int(n * 0.8)
    assert len(holdout) == n - int(n * 0.8)


def test_all_returns_every_query(evaluator):
    names = synthetic_names(17)
    assert evaluator.split_query_names(names, "all") == sorted(names)


def test_unknown_split_is_rejected(evaluator):
    with pytest.raises(ValueError):
        evaluator.split_query_names(synthetic_names(5), "validation")


# --- provenance recorded in the result --------------------------------------


def test_split_does_not_claim_unknown_source_model_independence(evaluator):
    info = evaluator.split_note("all", 13, 20, 20)
    assert info["partial"] is False
    assert info["in_sample"] is None
    assert "independence is not established" in info["note"]


@pytest.mark.parametrize("split", ["train", "holdout"])
def test_partial_splits_say_they_are_partial(evaluator, split):
    info = evaluator.split_note(split, 13, 16, 20)
    assert info["partial"] is True
    assert "Partial result" in info["note"]
    assert "16/20" in info["note"]


def test_splits_do_not_establish_model_training_provenance(evaluator):
    assert evaluator.split_note("holdout", 13, 4, 20)["in_sample"] is None
    assert evaluator.split_note("train", 13, 16, 20)["in_sample"] is None


def test_labels_are_scoped_to_their_declared_task(evaluator):
    annotations = [
        {"candidate": "sub", "task": "substitute", "functional_score": 0.8},
        {"candidate": "other", "task": "synergy", "functional_score": 1.0},
        {"candidate": "legacy", "functional_score": 0.5},
        {"candidate": "typo", "task": "substitut", "functional_score": 1.0},
    ]
    assert evaluator.task_scores(annotations, "substitute") == {"sub": 0.8, "legacy": 0.5}


# --- end to end through main() ---------------------------------------------


class FakeKeyedVectors:
    """KeyedVectors stand-in: neighbors are a fixed per-query ranking."""

    def __init__(self, keys, neighbors_by_query):
        self.index_to_key = list(keys)
        self.key_to_index = {key: i for i, key in enumerate(self.index_to_key)}
        self.neighbors_by_query = neighbors_by_query

    def __len__(self):
        return len(self.index_to_key)

    def __contains__(self, key):
        return key in self.key_to_index

    def most_similar(self, query, topn=10):
        return list(self.neighbors_by_query.get(query, []))[:topn]


def write_unit_inputs(root: Path, game: str = "magic", n_queries: int = 20) -> dict:
    """Create a test set and two placeholder embedding files under `root`."""
    queries = {}
    neighbors = {}
    for i in range(n_queries):
        query = f"Query {i:03d}"
        candidates = [f"Cand {i}-{j}" for j in range(3)]
        queries[query] = {
            "annotations": [
                {"candidate": candidates[0], "functional_score": 0.9},
                {"candidate": candidates[1], "functional_score": 0.4},
                {"candidate": candidates[2], "functional_score": 0.1},
            ]
        }
        neighbors[query] = [(c, 1.0 - 0.1 * j) for j, c in enumerate(candidates)]

    test_dir = root / "test_sets"
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / f"annotated_{game}_v2.json").write_text(json.dumps({"queries": queries}))

    emb_dir = root / "embeddings"
    emb_dir.mkdir(parents=True, exist_ok=True)
    for source in ("cleora_1iter", "text_e5"):
        (emb_dir / f"{game}_{source}.wv").write_bytes(b"")

    return {"queries": queries, "neighbors": neighbors}


def run_main(evaluator, monkeypatch, capsys, split: str) -> dict:
    argv = ["eval_fusion.py", "--game", "magic", "--json", "--split", split]
    monkeypatch.setattr(sys, "argv", argv)
    assert evaluator.main() == 0
    captured = capsys.readouterr()
    # The script prints human-readable progress before the JSON block.
    return json.loads(captured.out[captured.out.index("\n{") :])


@pytest.fixture
def unit_eval(evaluator, monkeypatch, tmp_path):
    inputs = write_unit_inputs(tmp_path)
    keys = list(inputs["queries"]) + [c for cands in inputs["neighbors"].values() for c, _ in cands]
    neighbors = inputs["neighbors"]
    monkeypatch.setattr(evaluator, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        evaluator,
        "load_vectors",
        lambda path: FakeKeyedVectors(keys, neighbors),
    )
    return evaluator, inputs


def test_result_records_split_metadata(unit_eval, monkeypatch, capsys):
    evaluator, inputs = unit_eval
    n_total = len(inputs["queries"])

    everything = run_main(evaluator, monkeypatch, capsys, "all")
    assert everything["split"] == "all"
    assert everything["split_seed"] == 13
    assert everything["n_queries"] == n_total
    assert everything["partial"] is False
    assert everything["in_sample"] is None
    assert "independence is not established" in everything["note"]
    assert everything["data"]["num_queries"] == n_total
    assert everything["substitute_legacy_pairs"] == 3 * n_total
    assert everything["synergy_ndcg"] is None
    assert everything["synergy_n"] == 0

    train = run_main(evaluator, monkeypatch, capsys, "train")
    holdout = run_main(evaluator, monkeypatch, capsys, "holdout")

    assert train["split"] == "train" and train["partial"] is True
    assert holdout["split"] == "holdout" and holdout["partial"] is True
    assert train["n_queries"] == int(n_total * 0.8)
    assert holdout["n_queries"] == n_total - int(n_total * 0.8)
    assert "Partial result" in train["note"]
    assert "Partial result" in holdout["note"]
    assert "independence is not established" in holdout["note"]
    assert holdout["in_sample"] is None
    # data.num_queries still describes the whole test set, not the split.
    assert holdout["data"]["num_queries"] == n_total
    assert holdout["data"]["split_queries"] == holdout["n_queries"]
