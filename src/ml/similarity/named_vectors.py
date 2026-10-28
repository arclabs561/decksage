"""Named vectors with a pickle-free NumPy storage format.

This is a narrow retrieval interface, not a replacement for Word2Vec training.
Legacy Gensim artifacts must be converted separately from trusted inputs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


class NamedVectors:
    """Named dense vectors and exact cosine retrieval."""

    def __init__(self, names: list[str], vectors: np.ndarray) -> None:
        matrix = np.asarray(vectors)
        if matrix.ndim != 2 or not matrix.shape[0] or not matrix.shape[1]:
            raise ValueError("vectors must be a nonempty matrix")
        if len(names) != len(matrix) or any(not isinstance(n, str) or not n for n in names):
            raise ValueError("each vector must have a nonempty name")
        if len(set(names)) != len(names):
            raise ValueError("vector names must be unique")
        if matrix.dtype not in (np.dtype("float32"), np.dtype("float64")):
            raise ValueError("vectors must use float32 or float64")
        if not np.isfinite(matrix).all():
            raise ValueError("vectors must be finite")
        norms = np.linalg.norm(matrix, axis=1)
        if not np.isfinite(norms).all() or np.any(norms == 0):
            raise ValueError("vector norms must be finite and nonzero")
        self.index_to_key = list(names)
        self.key_to_index = {name: index for index, name in enumerate(names)}
        self.vectors = matrix.copy()
        self.vectors.flags.writeable = False
        self.vector_size = matrix.shape[1]
        self._normalized = self.vectors / norms[:, None]
        self._normalized.flags.writeable = False

    def __len__(self) -> int:
        return len(self.index_to_key)

    def __contains__(self, key: str) -> bool:
        return key in self.key_to_index

    def __getitem__(self, key: str) -> np.ndarray:
        return self.vectors[self.key_to_index[key]]

    def get_normed_vectors(self) -> np.ndarray:
        return self._normalized

    def similarity(self, left: str, right: str) -> float:
        return float(
            np.dot(
                self._normalized[self.key_to_index[left]],
                self._normalized[self.key_to_index[right]],
            )
        )

    def most_similar(self, key: str, topn: int = 10) -> list[tuple[str, float]]:
        if topn < 0:
            raise ValueError("topn must be nonnegative")
        query_index = self.key_to_index[key]
        scores = self._normalized @ self._normalized[query_index]
        order = np.argsort(-scores, kind="stable")
        return [(self.index_to_key[i], float(scores[i])) for i in order if i != query_index][:topn]

    def save(self, path: str | Path) -> None:
        """Create a new portable artifact; never overwrite an existing file."""
        with Path(path).open("xb") as handle:
            np.savez(
                handle,
                version=np.array(1, dtype=np.int64),
                names=np.asarray(self.index_to_key),
                vectors=self.vectors,
            )

    @classmethod
    def load(cls, path: str | Path) -> NamedVectors:
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != {"version", "names", "vectors"}:
                raise ValueError("invalid named-vector artifact fields")
            version, names, vectors = archive["version"], archive["names"], archive["vectors"]
            if version.shape != () or version.dtype.kind not in "iu" or int(version) != 1:
                raise ValueError("unsupported named-vector artifact version")
            if names.ndim != 1 or names.dtype.kind != "U":
                raise ValueError("names must be a Unicode array")
            return cls(names.tolist(), vectors)
