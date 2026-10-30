"""The representation surface: one lookup for every learned artefact.

Nothing served imports this package yet. It exists so that a caller can name an
artefact and be refused, instead of recomputing a cache path and degrading to
zero.

    >>> from ml.representations import registry
    >>> registry.resolve("magic", "card_embedding").identity.dim
    128
"""

from __future__ import annotations

from ml.representations.manifest import (
    GAMES,
    Capability,
    Loaded,
    Representation,
    RepresentationManifest,
    Status,
    build_manifest,
    default_manifest,
    load_card_embedding,
    load_dense_index,
    load_edge_csv,
    load_fusion_weights,
    load_json_signal,
    sha256_of,
)
from ml.representations.registry import (
    REPAIRS,
    Identity,
    RefusalCode,
    RepresentationRefusal,
    RepresentationRegistry,
    Resolution,
    VerifyRow,
    VerifyTable,
    default_registry,
    resolve,
    verify,
)


__all__ = [
    "GAMES",
    "REPAIRS",
    "Capability",
    "Identity",
    "Loaded",
    "RefusalCode",
    "Representation",
    "RepresentationManifest",
    "RepresentationRefusal",
    "RepresentationRegistry",
    "Resolution",
    "Status",
    "VerifyRow",
    "VerifyTable",
    "build_manifest",
    "default_manifest",
    "default_registry",
    "load_card_embedding",
    "load_dense_index",
    "load_edge_csv",
    "load_fusion_weights",
    "load_json_signal",
    "resolve",
    "sha256_of",
    "verify",
]
