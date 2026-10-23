"""Structural interfaces for the optional fusion inputs.

Each of these is optional at runtime and silently scores zero when absent,
which is how three of five fusion signals ended up dead without anyone
noticing. A Protocol gives the type checker something to enforce: passing
`None` where an embedder is required, or an object without `encode`, becomes a
type error rather than a constant zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray


@runtime_checkable
class TextEmbedder(Protocol):
    """Encodes card text into a fixed-width vector."""

    def encode(
        self, texts: Sequence[str], normalize_embeddings: bool = True
    ) -> NDArray[np.float32]: ...


@runtime_checkable
class VisualEmbedder(Protocol):
    """Encodes card images into a fixed-width vector."""

    def encode_images(self, paths: Sequence[str]) -> NDArray[np.float32]: ...


@runtime_checkable
class CardTagger(Protocol):
    """Assigns functional tags to a card by name."""

    def tag_card(self, name: str) -> object: ...
