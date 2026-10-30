"""One manifest for every learned representation the service can name.

A consumer asks for a representation by ``(game, capability)`` and receives a
record carrying the identity a filename cannot: content hash, dimension, encoder
id, and the recipe that produced it. Paths come from ``.env`` and the on-disk
layout instead of a name hardcoded in nine scripts.

Importing this module reads two small files (``.env`` and
``PROVENANCE.json``) and stats the artefacts. Content hashes are computed on
first use and memoised against size and mtime, so a rebuilt artefact is re-hashed
rather than trusted.

This is a lookup layer. ``src/ml/api/api.py``, ``fusion.py`` and
``hybrid_search.py`` do not import it yet; see
``.agents/reports/2026-10-29-representation-registry-impl.md``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import numpy as np

from ml.utils.paths import PATHS


GAMES: tuple[str, ...] = ("magic", "pokemon", "yugioh")

_ENV_DIR = ".env-missing"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")

# A model id is the only thing that constrains the width of its output. Keeping
# the map small and explicit is deliberate: an unknown id yields ``dim=None`` and
# the dimensional contract is then "whatever the artefact says", never a guess.
TEXT_DIMS: dict[str, int] = {
    "intfloat/e5-base-v2": 768,
    "intfloat/e5-large-v2": 1024,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
}
VISUAL_DIMS: dict[str, int] = {
    "google/siglip-base-patch16-224": 768,
    "google/siglip2-so400m-patch16-384": 1152,
}

# The structural encoders declared by data/embeddings/PROVENANCE.json.
GRAPH_ENCODERS: dict[str, str] = {
    "magic": "graph-spectral:mu=0.35",
    "pokemon": "attribute-fusion:pca128:alpha=0.7",
    "yugioh": "graph-spectral:mu=0.3",
}


class Status(StrEnum):
    """Whether a declared artefact exists, is absent, or is kept only as history."""

    PRESENT = "PRESENT"
    MISSING = "MISSING"
    HISTORICAL = "HISTORICAL"
    """Exists, is kept for rollback or reference, and must never be served by default."""


class Capability(StrEnum):
    """The question a representation answers, not the file format it uses."""

    CARD_EMBEDDING = "card_embedding"
    TEXT_INDEX = "text_index"
    VISUAL_INDEX = "visual_index"
    COOCCURRENCE_GRAPH = "cooccurrence_graph"
    FUSION_WEIGHTS = "fusion_weights"
    ARCHETYPE_SIGNAL = "archetype_signal"


@lru_cache(maxsize=128)
def _digest(path: str, size: int, mtime_ns: int) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of(path: Path) -> str:
    """Content hash, memoised on ``(path, size, mtime_ns)``.

    Hashing 271 MB of deck pairs costs a fraction of a second, so it is done once
    per process and only when an identity is actually asked for.
    """
    stat = path.stat()
    return _digest(str(path), stat.st_size, stat.st_mtime_ns)


@dataclass(frozen=True)
class Representation:
    """One declared artefact and the identity it must keep."""

    game: str
    capability: Capability
    name: str
    path: Path
    dim: int | None = None
    encoder: str | None = None
    """Encoder identity the artefact was produced with; ``None`` means unrecorded."""
    sha256: str | None = None
    """Pinned content hash; ``None`` means the artefact is a derived cache."""
    producer_recipe: str | None = None
    status: Status = Status.PRESENT
    served: bool = True
    """``False`` for a member artefact: addressable by id, never auto-selected."""
    tasks: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.game or not self.name or not self.capability:
            raise ValueError("a representation needs a game, a capability and a name")
        if not isinstance(self.path, Path):
            raise TypeError(f"{self.id}: path must be a Path")
        if self.sha256 is not None and not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError(f"{self.id}: sha256 must be 64 lowercase hex characters")
        if self.dim is not None and self.dim <= 0:
            raise ValueError(f"{self.id}: dim must be positive")

    @property
    def id(self) -> str:
        return f"{self.game}:{self.capability}:{self.name}"

    def exists(self) -> bool:
        return self.path.is_file()

    def actual_sha256(self) -> str:
        return sha256_of(self.path)


# --- loaders: one per capability, each returning what it actually found ------


@dataclass(frozen=True)
class Loaded:
    """The artefact, opened, plus the identity it recorded about itself."""

    kind: str
    """``keyed_vectors``, ``dense_index``, ``edge_csv``, ``weights`` or ``json``."""
    dim: int | None
    encoder: str | None
    payload: object
    names: tuple[str, ...] = ()

    @property
    def size(self) -> int:
        return len(self.names)


@dataclass(frozen=True)
class EdgeCsv:
    """A co-occurrence edge list, streamed rather than materialised."""

    path: Path
    header: tuple[str, ...]

    @property
    def count_column(self) -> str | None:
        for candidate in ("COUNT_MULTISET", "COUNT", "WEIGHT"):
            if candidate in self.header:
                return candidate
        return None

    def iter_edges(self, limit: int | None = None) -> Iterator[tuple[str, str, int]]:
        import csv

        with self.path.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader):
                if limit is not None and index >= limit:
                    return
                left = row.get("NAME_1") or ""
                right = row.get("NAME_2") or ""
                if not left or not right:
                    continue
                column = self.count_column
                try:
                    weight = int(float(row.get(column, 1))) if column else 1
                except (TypeError, ValueError):
                    weight = 1
                yield left, right, weight

    def sample(self, limit: int = 3) -> list[tuple[str, str, int]]:
        return list(self.iter_edges(limit=limit))


def load_card_embedding(path: Path) -> Loaded:
    """Gensim ``KeyedVectors`` on disk (``.wv``)."""
    from gensim.models import KeyedVectors

    vectors = KeyedVectors.load(str(path))
    return Loaded(
        kind="keyed_vectors",
        dim=int(vectors.vector_size),
        encoder=None,
        payload=vectors,
        names=tuple(vectors.index_to_key),
    )


def _names_beside(path: Path) -> tuple[str, ...]:
    candidates = (
        path.with_name(path.name.replace("_embeddings.npy", "_names.txt")),
        path.with_name(f"{path.stem}_names.txt"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return tuple(candidate.read_text(errors="replace").splitlines())
    return ()


def load_dense_index(path: Path) -> Loaded:
    """A card-by-component matrix, with the ordered card names beside it."""
    suffix = path.suffix.lower()
    if suffix == ".npz":
        archive = np.load(path)
        matrix = archive["matrix"]
        encoder = str(archive["encoder"]) if "encoder" in archive.files else None
        meta_path = path.with_suffix(".meta.json")
        if meta_path.is_file():
            # hybrid_search writes this beside the cache; it is the only record
            # of which encoder produced the matrix.
            try:
                encoder = json.loads(meta_path.read_text()).get("encoder") or encoder
            except (OSError, ValueError):
                encoder = None
        names_path = path.with_suffix(".names.json")
        names = tuple(json.loads(names_path.read_text())) if names_path.is_file() else ()
        return Loaded(
            kind="dense_index",
            dim=int(matrix.shape[1]),
            encoder=encoder,
            payload=archive,
            names=names,
        )
    if suffix == ".npy":
        matrix = np.load(path, mmap_mode="r")
        if matrix.ndim != 2:
            raise ValueError(f"{path.name}: expected a 2-D matrix, found shape {matrix.shape}")
        return Loaded(
            kind="dense_index",
            dim=int(matrix.shape[1]),
            encoder=None,
            payload=matrix,
            names=_names_beside(path),
        )
    raise ValueError(f"{path.name}: no dense-index reader for {suffix or 'a suffixless file'}")


def load_edge_csv(path: Path) -> Loaded:
    """A pairs CSV. The schema is not shared between games, so it is read, not assumed."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        first = handle.readline().strip()
    header = tuple(part.strip() for part in first.split(",") if part.strip())
    if "NAME_1" not in header or "NAME_2" not in header:
        raise ValueError(f"{path.name}: expected NAME_1/NAME_2 columns, found {header}")
    return Loaded(kind="edge_csv", dim=None, encoder=None, payload=EdgeCsv(path, header))


def load_fusion_weights(path: Path) -> Loaded:
    """A weights file is only loadable when it says what produced it.

    The withdrawn 0065 artefact carried weights and nothing else, which is how a
    calibration fitted on dead signals could be served. The three evidence fields
    are the difference between a result and a number.
    """
    weights = json.loads(path.read_text())
    if not isinstance(weights, dict) or "best_weights" not in weights:
        raise ValueError(f"{path.name}: expected a fusion record with 'best_weights'")
    required = ("objective", "holdout_coverage", "experiment")
    missing = [field for field in required if field not in weights]
    if missing:
        raise ValueError(
            f"{path.name}: no {', '.join(missing)} recorded; "
            "this is a pre-0067 artefact and must not be served as calibrated"
        )
    return Loaded(kind="weights", dim=None, encoder=None, payload=weights)


def load_json_signal(path: Path) -> Loaded:
    payload = json.loads(path.read_text())
    if not isinstance(payload, (dict, list)):
        raise ValueError(f"{path.name}: expected JSON object or array")
    return Loaded(kind="json", dim=None, encoder=None, payload=payload)


LOADERS: dict[str, Callable[[Path], Loaded]] = {
    Capability.CARD_EMBEDDING: load_card_embedding,
    Capability.TEXT_INDEX: load_dense_index,
    Capability.VISUAL_INDEX: load_dense_index,
    Capability.COOCCURRENCE_GRAPH: load_edge_csv,
    Capability.FUSION_WEIGHTS: load_fusion_weights,
    Capability.ARCHETYPE_SIGNAL: load_json_signal,
}


# --- declaration ------------------------------------------------------------


def project_root() -> Path:
    override = os.getenv("DECKSAGE_ROOT")
    return Path(override).expanduser().resolve() if override else Path(PATHS.project_root).resolve()


def read_env(root: Path) -> dict[str, str]:
    """``.env`` values, with the process environment taking precedence."""
    values: dict[str, str] = {}
    dotenv = root / ".env"
    if dotenv.is_file():
        from dotenv import dotenv_values

        values.update({k: v for k, v in dotenv_values(dotenv).items() if v is not None})
    values.update(os.environ)
    return values


def _env_path(env: Mapping[str, str], key: str, root: Path) -> Path:
    value = env.get(key, "").strip()
    if not value:
        # Declared, absent, and named: a lookup refuses instead of guessing a name.
        return root / _ENV_DIR / key
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path)


def _recipes(root: Path) -> dict[str, dict]:
    path = root / "data" / "embeddings" / "PROVENANCE.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    artefacts = data.get("artefacts")
    return artefacts if isinstance(artefacts, dict) else {}


def _recipe_text(recipes: Mapping[str, dict], path: Path) -> str | None:
    recipe = recipes.get(path.name)
    if not recipe:
        return None
    producer = str(recipe.get("producer") or "").strip()
    argv = str(recipe.get("argv") or "").strip()
    if not producer:
        return None
    return f"{producer} :: {argv}" if argv else producer


def _status(path: Path, *, historical: bool = False) -> Status:
    if historical:
        return Status.HISTORICAL
    return Status.PRESENT if path.is_file() else Status.MISSING


def _game_representations(
    game: str, env: Mapping[str, str], root: Path, recipes: Mapping[str, dict]
) -> list[Representation]:
    data = root / "data"
    upper = game.upper()
    text_model = env.get("INSTRUCTION_EMBEDDER_MODEL") or None
    visual_model = env.get("VISUAL_EMBEDDER_MODEL") or None

    primary = _env_path(env, f"EMBEDDINGS_PATH_{upper}", root)
    secondary = _env_path(env, f"SECONDARY_EMBEDDINGS_PATH_{upper}", root)
    pairs = _env_path(env, f"PAIRS_PATH_{upper}", root)
    legacy_text = data / "cache" / "text_embeddings" / f"{game}_embeddings.npy"
    keyed_text = data / "cache" / f"text_emb_cache_cards_{game}.npz"
    visual = data / "cache" / "visual_embeddings" / f"{game}_embeddings.npy"
    fusion = data / "embeddings" / f"fusion_weights_{game}.json"
    archetype = root / "experiments" / "signals" / "archetype_staples.json"

    return [
        Representation(
            game=game,
            capability=Capability.CARD_EMBEDDING,
            name="primary",
            path=primary,
            dim=128,
            encoder=GRAPH_ENCODERS.get(game),
            sha256={
                "magic": "3d221e573abf447dbb634a789cf256d167b6e7898a609ab08adc6569b5bd5419",
                "pokemon": "bd2462d05f283fa5a553f98b4bcdd15c64982dd5f4d20b688d632bace57f5a61",
                "yugioh": "cf8d657debeb525970d60f9155abdee98faeb2663359849573be45f60b8a6bad",
            }.get(game),
            producer_recipe=_recipe_text(recipes, primary),
            status=_status(primary),
            notes="structural embedding; identity is the hash, not the _mu suffix",
        ),
        Representation(
            game=game,
            capability=Capability.CARD_EMBEDDING,
            name="secondary_metapath2vec",
            path=secondary,
            dim=128,
            encoder="metapath2vec",
            sha256={
                "magic": "97dcf9dd8c332107beb20c7f42f0ddeeb310810ffe38f11ee3e18349d501a21e",
                "pokemon": "ac3e4d3a71b8c8e742042b7b4e368259713517f1e46a0d6f84206fa5f8aa6960",
                "yugioh": "dde13fb3c1c852db6146a6c489d704d19429d09804c034dacd0d8bee9a23709a",
            }.get(game),
            producer_recipe=_recipe_text(recipes, secondary),
            status=_status(secondary),
            served=False,
            notes=(
                "declared by SECONDARY_EMBEDDINGS_PATH_*; a reranker member, so it is "
                "addressable by id and never auto-selected for a task"
            ),
        ),
        Representation(
            game=game,
            capability=Capability.TEXT_INDEX,
            name="encoder_keyed_npz",
            path=keyed_text,
            dim=TEXT_DIMS.get(text_model) if text_model else None,
            encoder=text_model,
            sha256=None,
            producer_recipe="ml.search.hybrid_search",
            status=_status(keyed_text),
            notes=(
                "derived cache: unpinned because a rebuild is expected. The file on disk "
                "has no .meta.json, so the served encoder is declared here and unverified "
                "by the artefact; hybrid_search now writes an encoder-slugged name, so "
                "this path will not be the one a rebuild produces"
            ),
        ),
        Representation(
            game=game,
            capability=Capability.TEXT_INDEX,
            name="legacy_npy",
            path=legacy_text,
            dim=768,
            encoder=None,
            sha256={
                "magic": "bc3862f4269ef55ba05cb3e4054131af2d648e8670d4d66bd8ca029417263e63",
                "pokemon": "0f3e6222fc7119f6ec5065372f6bce440f32e817565f240ad527e37e8506e3a7",
                "yugioh": "cda64108ab8b3ded66bfd6894278c9b00fa24755cf0bbb1c72aa2571ed5f71dc",
            }.get(game),
            producer_recipe="scripts/training/build_text_embedding_index.py",
            status=Status.HISTORICAL,
            notes=(
                "legacy layout read only by fusion.py; the encoder that produced it was "
                "never recorded, so allow_historical=True still refuses an encoder contract"
            ),
        ),
        Representation(
            game=game,
            capability=Capability.VISUAL_INDEX,
            name="siglip_npy",
            path=visual,
            dim=VISUAL_DIMS.get(visual_model) if visual_model else None,
            encoder=visual_model,
            sha256=None,
            producer_recipe="scripts/training/build_visual_embedding_index.py",
            status=_status(visual),
            notes="declared and never built on this checkout; absent is MISSING, not zero weight",
        ),
        Representation(
            game=game,
            capability=Capability.COOCCURRENCE_GRAPH,
            name="pairs",
            path=pairs,
            dim=None,
            encoder=None,
            sha256={
                "magic": "0832b055c8423a840d6103bfa769ca3c461a53437431fbbe2235cfdb14c1fdc0",
                "pokemon": "f8ce3fc5f8e47aeb3a7ff9a35861a0937fb04a570aad62496d326ba4e3c27eae",
                "yugioh": "0d1b19f45d468c12742a8818a4928143c3c201fdbd53734ae6f8cb4acfcb6e37",
            }.get(game),
            producer_recipe="deck ingest -> data/processed/pairs_*.csv",
            status=_status(pairs),
            notes="the edge list the .graph.pkl cache is derived from; two schemas exist across games",
        ),
        Representation(
            game=game,
            capability=Capability.FUSION_WEIGHTS,
            name="calibrated",
            path=fusion,
            dim=None,
            encoder="linear:best_weights",
            # Not hash-pinned on purpose: a weights file is derived, and each
            # calibration rewrites it. Its identity is the experiment id recorded
            # inside the file, which `load_fusion_weights` now refuses to skip.
            sha256=None,
            producer_recipe="scripts/training/calibrate_fusion_weights.py",
            status=_status(fusion),
            tasks=("substitute",),
            notes=(
                "calibrated under experiment 0067 on canonical labels; carries objective, "
                "coverage and experiment id, which the loader requires"
                if game == "magic"
                else "no calibrated weights exist for this game; a missing file is MISSING, not zero"
            ),
        ),
        Representation(
            game=game,
            capability=Capability.ARCHETYPE_SIGNAL,
            name="staples",
            path=archetype,
            dim=None,
            encoder=None,
            sha256=None,
            producer_recipe="scripts/training/load_signals.py reads experiments/signals/*.json",
            status=_status(archetype),
            tasks=("synergy",),
            notes="startup reports signals 2/3 for every game because this file is absent",
        ),
    ]


@dataclass(frozen=True)
class RepresentationManifest:
    """The declared set, validated so a lookup can never be ambiguous."""

    root: Path
    representations: tuple[Representation, ...]

    def __post_init__(self) -> None:
        seen: dict[str, Representation] = {}
        for record in self.representations:
            if record.id in seen:
                raise ValueError(f"duplicate representation id: {record.id}")
            seen[record.id] = record
        self._validate_unique_serving()

    def _validate_unique_serving(self) -> None:
        groups: dict[tuple[str, str], list[Representation]] = {}
        for record in self.representations:
            if record.status is Status.HISTORICAL or not record.served:
                continue
            groups.setdefault((record.game, record.capability), []).append(record)
        for (game, capability), records in groups.items():
            for index, left in enumerate(records):
                for right in records[index + 1 :]:
                    if left.tasks and right.tasks and set(left.tasks).isdisjoint(right.tasks):
                        continue
                    raise ValueError(
                        f"{game}/{capability}: two servable representations ({left.id}, "
                        f"{right.id}); declare one or mark one HISTORICAL"
                    )

    def __iter__(self) -> Iterator[Representation]:
        return iter(self.representations)

    def __len__(self) -> int:
        return len(self.representations)

    def get(self, representation_id: str) -> Representation | None:
        for record in self.representations:
            if record.id == representation_id:
                return record
        return None

    def select(self, game: str, capability: str) -> list[Representation]:
        return [
            record
            for record in self.representations
            if record.game == game and record.capability == capability
        ]

    def games(self) -> tuple[str, ...]:
        return tuple(sorted({record.game for record in self.representations}))


def build_manifest(
    root: Path | None = None, env: Mapping[str, str] | None = None
) -> RepresentationManifest:
    """Declare every artefact from ``.env`` and the layout under ``data/``."""
    resolved_root = Path(root).expanduser().resolve() if root else project_root()
    values = dict(env) if env is not None else read_env(resolved_root)
    recipes = _recipes(resolved_root)
    records: list[Representation] = []
    for game in GAMES:
        records.extend(_game_representations(game, values, resolved_root, recipes))
    return RepresentationManifest(root=resolved_root, representations=tuple(records))


@lru_cache(maxsize=1)
def default_manifest() -> RepresentationManifest:
    """The manifest for this checkout, built once per process."""
    return build_manifest()
