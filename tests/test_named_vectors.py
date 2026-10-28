"""Named-vector storage and exact cosine search contracts."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from ml.similarity.named_vectors import NamedVectors


def test_roundtrip_and_cosine_retrieval(tmp_path):
    vectors = NamedVectors(["A", "B", "C"], np.array([[1, 0], [1, 1], [-1, 0]], dtype=np.float32))
    path = tmp_path / "vectors.npz"
    vectors.save(path)
    loaded = NamedVectors.load(path)
    assert loaded.index_to_key == ["A", "B", "C"]
    np.testing.assert_array_equal(loaded.vectors, vectors.vectors)
    assert [name for name, _ in loaded.most_similar("A", 2)] == ["B", "C"]
    assert loaded.similarity("A", "B") == pytest.approx(1 / np.sqrt(2))
    assert [name for name, _ in loaded.similar_by_vector(np.array([1.0, 0.0]), 2)] == ["A", "B"]
    with pytest.raises(ValueError, match="query norm"):
        loaded.similar_by_vector(np.zeros(2))
    with pytest.raises(FileExistsError):
        vectors.save(path)


@pytest.mark.parametrize(
    ("names", "vectors"),
    [
        (["A", "A"], [[1.0], [2.0]]),
        (["A"], [[0.0]]),
        (["A"], [[float("nan")]]),
        (["A"], [[float("inf")]]),
        (["A"], [[1], [2]]),
    ],
)
def test_invalid_vectors_rejected(names, vectors):
    with pytest.raises(ValueError):
        NamedVectors(names, np.asarray(vectors, dtype=np.float32))


def test_invalid_version_and_pickle_names_are_rejected(tmp_path):
    path = tmp_path / "bad.npz"
    np.savez(path, version=2, names=np.array(["A"]), vectors=np.array([[1.0]]))
    with pytest.raises(ValueError, match="version"):
        NamedVectors.load(path)
    object_path = tmp_path / "object.npz"
    np.savez(object_path, version=1, names=np.array(["A"], dtype=object), vectors=np.array([[1.0]]))
    with pytest.raises(ValueError):
        NamedVectors.load(object_path)


def test_api_loads_portable_vectors_without_gensim(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from ml.api import api, query_history
    from ml.api.models import ApiState

    path = tmp_path / "vectors.npz"
    NamedVectors(["A", "B", "C"], np.array([[1, 0], [1, 1], [-1, 0]], dtype=np.float32)).save(path)
    state = ApiState()
    monkeypatch.setattr(api, "HAS_GENSIM", False)
    monkeypatch.setattr(api, "get_state", lambda *args: state)
    monkeypatch.setattr(query_history, "log_query", lambda **kwargs: None)
    api.load_embeddings_to_state("magic", str(path))
    response = TestClient(api.app).get(
        "/v1/cards/A/similar", params={"mode": "embedding", "game": "magic", "k": 2}
    )
    assert response.status_code == 200
    assert [item["card"] for item in response.json()["results"]] == ["B", "C"]
    assert state.model_info["num_cards"] == 3


def test_evaluators_load_explicit_portable_vectors(tmp_path, monkeypatch):
    embeddings = tmp_path / "embeddings"
    embeddings.mkdir()
    path = embeddings / "magic_sample.npz"
    NamedVectors(["A", "B"], np.array([[1, 0], [1, 1]], dtype=np.float32)).save(path)
    root = Path(__file__).resolve().parents[1]
    modules = []
    for script in ("eval_fusion", "eval_per_mode"):
        spec = importlib.util.spec_from_file_location(
            script, root / f"scripts/evaluation/{script}.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    fusion, per_mode = modules
    monkeypatch.setattr(per_mode, "DATA_DIR", tmp_path)
    assert fusion.load_vectors(path).most_similar("A", 1)[0][0] == "B"
    assert per_mode.load_embeddings("magic", "magic_sample.npz").most_similar("A", 1)[0][0] == "B"


def test_metapath_output_is_portable_and_does_not_overwrite(tmp_path):
    pytest.importorskip("torch")
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "train_metapath2vec", root / "scripts/training/train_metapath2vec.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "embeddings" / "magic_metapath2vec.npz"
    source = np.array([[1, 0], [1, 1]], dtype=np.float32)
    module.save_training_vectors(["A", "B"], source, path)
    np.testing.assert_array_equal(NamedVectors.load(path).vectors, source)
    with pytest.raises(FileExistsError):
        module.save_training_vectors(["A", "B"], source, path)
