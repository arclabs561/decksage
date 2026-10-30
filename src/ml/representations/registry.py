"""Resolve a representation, or refuse with a code that names the repair.

There is no ``None`` return and no degraded value. Every failure class in this
module replaced a silent zero in a served path, so the refusal is the feature:
``MISSING`` for an artefact that is not there, ``HISTORICAL_ONLY`` for one that
must not be served, ``DIM_MISMATCH`` and ``ENCODER_MISMATCH`` for a contract that
does not hold, ``HASH_MISMATCH`` for a file that changed under its own name,
``NO_LOADER`` for a capability nothing can open, ``UNREADABLE`` for a file that
is present and broken.

``verify()`` asks the same questions for every declared artefact and returns a
printable table, because a health check that cannot refuse is not a check.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from ml.representations.manifest import (
    LOADERS,
    Loaded,
    Representation,
    RepresentationManifest,
    Status,
    default_manifest,
)


if TYPE_CHECKING:
    from collections.abc import Iterator


class RefusalCode(StrEnum):
    """Every way a representation can refuse. One code, one repair."""

    MISSING = "MISSING"
    DIM_MISMATCH = "DIM_MISMATCH"
    ENCODER_MISMATCH = "ENCODER_MISMATCH"
    HASH_MISMATCH = "HASH_MISMATCH"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    NO_LOADER = "NO_LOADER"
    UNREADABLE = "UNREADABLE"


REPAIRS: dict[RefusalCode, str] = {
    RefusalCode.MISSING: "produce the artefact, or stop declaring it",
    RefusalCode.DIM_MISMATCH: "re-declare the dimension, or rebuild the artefact",
    RefusalCode.ENCODER_MISMATCH: "rebuild with the declared encoder, or declare the one used",
    RefusalCode.HASH_MISMATCH: "re-declare the hash after checking what produced the new file",
    RefusalCode.HISTORICAL_ONLY: "pass allow_historical=True to read it, never to serve it",
    RefusalCode.NO_LOADER: "add a loader for this capability, or drop the declaration",
    RefusalCode.UNREADABLE: "repair the file; a present artefact must open",
}


class RepresentationRefusal(Exception):
    """A typed refusal carrying the machine-readable code."""

    def __init__(
        self,
        code: RefusalCode,
        *,
        game: str,
        capability: str,
        detail: str,
        representation_id: str | None = None,
    ) -> None:
        self.code = code
        self.game = game
        self.capability = capability
        self.detail = detail
        self.representation_id = representation_id
        repair = REPAIRS[code]
        target = representation_id or f"{game}/{capability}"
        super().__init__(f"{code}: {target}: {detail} [{repair}]")

    def as_dict(self) -> dict[str, str | None]:
        return {
            "code": str(self.code),
            "game": self.game,
            "capability": self.capability,
            "representation": self.representation_id,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Identity:
    """What was served: the fields a response or an experiment record must carry."""

    id: str
    game: str
    capability: str
    path: str
    dim: int | None
    encoder: str | None
    sha256: str | None
    status: Status
    producer_recipe: str | None

    def as_dict(self) -> dict[str, str | int | None]:
        return {
            "id": self.id,
            "game": self.game,
            "capability": self.capability,
            "path": self.path,
            "dim": self.dim,
            "encoder": self.encoder,
            "sha256": self.sha256,
            "status": str(self.status),
            "producer_recipe": self.producer_recipe,
        }


@dataclass(frozen=True)
class Resolution:
    """A loaded representation plus the identity it was resolved under."""

    representation: Representation
    loaded: Loaded
    hash_checked: bool

    @property
    def identity(self) -> Identity:
        return Identity(
            id=self.representation.id,
            game=self.representation.game,
            capability=str(self.representation.capability),
            path=str(self.representation.path),
            dim=self.loaded.dim,
            encoder=self.loaded.encoder or self.representation.encoder,
            sha256=self.representation.sha256,
            status=self.representation.status,
            producer_recipe=self.representation.producer_recipe,
        )

    @property
    def dim(self) -> int | None:
        return self.loaded.dim

    @property
    def payload(self) -> object:
        return self.loaded.payload


@dataclass(frozen=True)
class VerifyRow:
    """One declared representation, as ``verify()`` saw it."""

    representation: Representation
    code: RefusalCode | None
    detail: str

    @property
    def id(self) -> str:
        return self.representation.id

    @property
    def servable(self) -> bool:
        return self.code is None

    def as_dict(self) -> dict[str, str | int | None]:
        record = self.representation
        return {
            "id": record.id,
            "game": record.game,
            "capability": str(record.capability),
            "path": str(record.path),
            "status": str(record.status),
            "dim": record.dim,
            "encoder": record.encoder,
            "sha256": record.sha256,
            "code": str(self.code) if self.code else None,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class VerifyTable:
    """Every declared representation with its status and refusal code."""

    rows: tuple[VerifyRow, ...]

    def __iter__(self) -> Iterator[VerifyRow]:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def ok(self) -> bool:
        return all(row.servable for row in self.rows)

    def refused(self) -> tuple[VerifyRow, ...]:
        return tuple(row for row in self.rows if not row.servable)

    def as_dicts(self) -> list[dict[str, str | int | None]]:
        return [row.as_dict() for row in self.rows]

    def format(self) -> str:
        header = ("id", "status", "dim", "encoder", "code", "detail")
        body = [
            (
                row.id,
                str(row.representation.status),
                str(row.representation.dim) if row.representation.dim else "-",
                row.representation.encoder or "-",
                str(row.code) if row.code else "ok",
                row.detail,
            )
            for row in self.rows
        ]
        widths = [len(name) for name in header]
        for line in body:
            for index, cell in enumerate(line):
                widths[index] = max(widths[index], len(cell))
        widths[0] = min(widths[0], 48)
        widths[3] = min(widths[3], 36)
        widths[-1] = min(widths[-1], 88)

        def render(cells: tuple[str, ...]) -> str:
            padded = [cell[:width].ljust(width) for cell, width in zip(cells, widths)]
            return "  ".join(padded).rstrip()

        lines = [render(header), render(tuple("-" * width for width in widths))]
        lines.extend(render(line) for line in body)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.format()


class RepresentationRegistry:
    """Ask for a representation; get it or a refusal."""

    def __init__(self, manifest: RepresentationManifest | None = None) -> None:
        self.manifest = manifest if manifest is not None else default_manifest()

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.manifest.root))
        except ValueError:
            return str(path)

    def __iter__(self) -> Iterator[Representation]:
        return iter(self.manifest)

    def ids(self) -> tuple[str, ...]:
        return tuple(record.id for record in self.manifest)

    def resolve(
        self,
        game: str,
        capability: str,
        task: str | None = None,
        *,
        pinned: str | None = None,
        allow_historical: bool = False,
        require_dim: int | None = None,
        require_encoder: str | None = None,
        verify_hash: bool = True,
    ) -> Resolution:
        """Return the loaded artefact, or raise ``RepresentationRefusal``.

        ``pinned`` names an id exactly and bypasses task selection. ``task``
        filters records that declare one; a record with no declared task answers
        every task. ``allow_historical`` makes history readable, which is a
        reporting and replay privilege, not a serving one.
        """
        record = self._select(game, capability, task=task, pinned=pinned)
        if not record.exists():
            raise RepresentationRefusal(
                RefusalCode.MISSING,
                game=game,
                capability=capability,
                detail=f"absent: {self._rel(record.path)}",
                representation_id=record.id,
            )
        if record.status is Status.HISTORICAL and not allow_historical:
            raise RepresentationRefusal(
                RefusalCode.HISTORICAL_ONLY,
                game=game,
                capability=capability,
                detail=record.notes or f"{record.name} is kept as history",
                representation_id=record.id,
            )
        loaded, code, detail = self._inspect(
            record,
            require_dim=require_dim,
            require_encoder=require_encoder,
            verify_hash=verify_hash,
        )
        if code is not None or loaded is None:
            raise RepresentationRefusal(
                code or RefusalCode.UNREADABLE,
                game=game,
                capability=capability,
                detail=detail,
                representation_id=record.id,
            )
        return Resolution(
            representation=record,
            loaded=loaded,
            hash_checked=verify_hash and record.sha256 is not None,
        )

    def _select(
        self, game: str, capability: str, *, task: str | None, pinned: str | None
    ) -> Representation:
        records = self.manifest.select(game, capability)
        if pinned is not None:
            for record in records:
                if record.id == pinned:
                    return record
            raise RepresentationRefusal(
                RefusalCode.MISSING,
                game=game,
                capability=capability,
                detail=f"no declared representation with id {pinned!r}",
                representation_id=pinned,
            )
        if task is not None:
            records = [record for record in records if not record.tasks or task in record.tasks]
        servable = [
            record for record in records if record.served and record.status is not Status.HISTORICAL
        ]
        if servable:
            # The manifest refuses to build with two servable records for one
            # (game, capability), so this cannot hide a choice.
            return servable[0]
        if records:
            return records[0]
        raise RepresentationRefusal(
            RefusalCode.MISSING,
            game=game,
            capability=capability,
            detail=(
                f"nothing declared for game={game!r} capability={capability!r}"
                + (f" task={task!r}" if task else "")
            ),
        )

    def _inspect(
        self,
        record: Representation,
        *,
        require_dim: int | None = None,
        require_encoder: str | None = None,
        verify_hash: bool = True,
    ) -> tuple[Loaded | None, RefusalCode | None, str]:
        if not record.exists():
            return None, RefusalCode.MISSING, f"absent: {self._rel(record.path)}"
        loader = LOADERS.get(record.capability)
        if loader is None:
            return None, RefusalCode.NO_LOADER, f"no loader registered for {record.capability!r}"
        try:
            loaded = loader(record.path)
        except ImportError as exc:
            return None, RefusalCode.NO_LOADER, f"{record.capability}: {exc}"
        except Exception as exc:  # every read failure is one class
            return None, RefusalCode.UNREADABLE, f"{type(exc).__name__}: {exc}"

        if record.dim is not None and loaded.dim is not None and loaded.dim != record.dim:
            return (
                None,
                RefusalCode.DIM_MISMATCH,
                f"declared dim {record.dim}, file has {loaded.dim}",
            )
        if require_dim is not None and loaded.dim is not None and loaded.dim != require_dim:
            return (
                None,
                RefusalCode.DIM_MISMATCH,
                f"caller requires dim {require_dim}, artefact has {loaded.dim}",
            )
        effective_encoder = loaded.encoder or record.encoder
        if (
            loaded.encoder is not None
            and record.encoder is not None
            and loaded.encoder != record.encoder
        ):
            return (
                None,
                RefusalCode.ENCODER_MISMATCH,
                f"artefact records encoder {loaded.encoder!r}, declared {record.encoder!r}",
            )
        if require_encoder is not None and effective_encoder != require_encoder:
            return (
                None,
                RefusalCode.ENCODER_MISMATCH,
                f"caller requires encoder {require_encoder!r}, resolved {effective_encoder!r}",
            )
        if verify_hash and record.sha256 is not None:
            actual = record.actual_sha256()
            if actual != record.sha256:
                return (
                    None,
                    RefusalCode.HASH_MISMATCH,
                    f"declared {record.sha256[:12]}..., file hashes to {actual[:12]}...",
                )
        detail_parts: list[str] = []
        if record.encoder is not None and loaded.encoder is None:
            detail_parts.append("encoder not recorded by the artefact")
        if record.sha256 is None:
            detail_parts.append("unpinned (derived): identity = declared encoder")
        if loaded.kind in {"keyed_vectors", "dense_index"} and loaded.names:
            detail_parts.append(f"{loaded.size} names x {loaded.dim}")
        elif loaded.kind == "edge_csv":
            header = getattr(loaded.payload, "header", ())
            if header:
                detail_parts.append(f"columns: {','.join(header)}")
        elif loaded.kind == "weights" and isinstance(loaded.payload, dict):
            recorded = loaded.payload.get("ndcg_at_10")
            if isinstance(recorded, float):
                detail_parts.append(f"recorded nDCG@10={recorded:.4f} (unvalidated here)")
        return loaded, None, "; ".join(detail_parts)

    def verify(self, *, include_hash: bool = True) -> VerifyTable:
        """Every declared representation, with the code serving would raise."""
        rows: list[VerifyRow] = []
        for record in self.manifest:
            _loaded, code, detail = self._inspect(record, verify_hash=include_hash)
            if code is None and record.status is Status.HISTORICAL:
                code = RefusalCode.HISTORICAL_ONLY
                detail = "readable with allow_historical=True; never served by default"
            rows.append(VerifyRow(representation=record, code=code, detail=detail))
        return VerifyTable(rows=tuple(rows))


_DEFAULT_REGISTRY: RepresentationRegistry | None = None


def default_registry() -> RepresentationRegistry:
    """The registry for this checkout; the manifest is built on first use."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = RepresentationRegistry(default_manifest())
    return _DEFAULT_REGISTRY


def resolve(game: str, capability: str, task: str | None = None, **kwargs: object) -> Resolution:
    """``default_registry().resolve(...)`` for callers that hold no registry."""
    return default_registry().resolve(game, capability, task, **kwargs)  # type: ignore[arg-type]


def verify(**kwargs: object) -> VerifyTable:
    """``default_registry().verify(...)`` for ``python -m ml.representations``."""
    return default_registry().verify(**kwargs)  # type: ignore[arg-type]
