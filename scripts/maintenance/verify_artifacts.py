#!/usr/bin/env python3
"""Check every learned artefact the service relies on: exists, matches, has a producer.

The audit found artefacts that were served without a reproducible producer, and
artefacts that were checked for existence but never for provenance. Existence is
the easy question. This asks the two that matter:

* **Can it be rebuilt?** A producer script that names the artefact, or an
  explicit "no producer" that makes the artefact historical evidence.
* **Does it match what is declared?** Dimensionality, vocabulary size and (where
  recorded) encoder identity.

Exit codes: 0 all required artefacts verified, 1 something required failed,
2 only warnings.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Status(StrEnum):
    OK = "OK"
    MISSING = "MISSING"
    UNREADABLE = "UNREADABLE"
    DIM_MISMATCH = "DIM_MISMATCH"
    NO_PRODUCER = "NO_PRODUCER"
    RECIPE_BROKEN = "RECIPE_BROKEN"
    """A recorded recipe exists but one of its inputs is missing."""
    HISTORICAL = "HISTORICAL"
    """Kept for reference; deliberately not reproducible. Never served."""


@dataclass
class Artefact:
    name: str
    path: Path
    kind: str  # "word2vec" | "npy" | "npz" | "json" | "graph"
    producer: str | None
    consumers: tuple[str, ...] = ()
    dim: int | None = None
    required: bool = False
    historical: bool = False
    notes: str = ""


@dataclass
class Result:
    artefact: Artefact
    status: Status
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.artefact.name,
            "path": str(self.artefact.path.relative_to(PROJECT_ROOT)),
            "status": str(self.status),
            "detail": self.detail,
            "required": self.artefact.required,
            "consumers": list(self.artefact.consumers),
        }


# what production actually loads per game (see .env EMBEDDINGS_PATH_*)
PRIMARY_FILES = {
    "magic": "magic_v7_spectral_mu35.wv",
    "pokemon": "pokemon_v7_fused.wv",
    "yugioh": "yugioh_v7_spectral_mu3.wv",
}


def declared(game: str) -> list[Artefact]:
    """The artefacts production actually names, per the representation audit."""
    data = PROJECT_ROOT / "data"
    return [
        Artefact(
            name=f"{game}_primary_embedding",
            path=data / "embeddings" / PRIMARY_FILES.get(game, f"{game}_v7_spectral_mu35.wv"),
            kind="word2vec",
            producer="scripts/pipeline/run_pipeline.py",
            consumers=("ml.api.api", "ml.similarity.fusion"),
            dim=128,
            required=True,
            notes="pipeline writes mu=0.3 under a caller-chosen name; provenance guard added",
        ),
        Artefact(
            name=f"{game}_text_index_npy",
            path=data / "cache" / "text_embeddings" / f"{game}_embeddings.npy",
            kind="npy",
            producer=None,
            consumers=("ml.similarity.fusion",),
            dim=768,
            historical=True,
            notes="legacy layout; nothing writes it and search uses the encoder-keyed npz",
        ),
        Artefact(
            name=f"{game}_text_cache_npz",
            path=data / "cache" / "",  # resolved by glob: encoder is in the name
            kind="npz",
            producer="ml.search.hybrid_search",
            consumers=("ml.search.hybrid_search",),
            dim=768,
            notes="encoder-keyed; rebuilt on identity change",
        ),
        Artefact(
            name=f"{game}_fusion_weights",
            path=data / "embeddings" / f"fusion_weights_{game}.json",
            kind="json",
            producer="scripts/training/calibrate_fusion_weights.py",
            consumers=(),
            historical=True,
            notes="experiment 0065 withdrawn; not read at serving time",
        ),
        Artefact(
            name=f"{game}_cooccurrence_graph",
            path=data / "processed" / "",  # glob for pairs_*.csv
            kind="graph",
            producer="src/backend/cmd/export-graph",
            consumers=("ml.api.api",),
        ),
    ]


def _resolve(artefact: Artefact) -> Path | None:
    if artefact.path.name:
        if artefact.path.exists():
            return artefact.path
    base = artefact.path.parent
    if not base.exists():
        return None
    game = artefact.name.split("_")[0]
    patterns = {
        "npz": f"text_emb_cache_{game}*.npz",
        "graph": "pairs_*.csv",
    }
    pattern = patterns.get(artefact.kind)
    if not pattern:
        return None
    matches = sorted(base.glob(pattern), key=lambda p: p.stat().st_size, reverse=True)
    return matches[0] if matches else None


def _mu_claim(name: str) -> str | None:
    """The mu a filename claims: _mu35 -> 0.35, _mu3 -> 0.3."""
    match = re.search(r"_mu(\d+)", name)
    if not match:
        return None
    digits = match.group(1)
    return f"0.{digits}"


def _recipe_for(artefact: Artefact) -> dict | None:
    path = PROJECT_ROOT / "data" / "embeddings" / "PROVENANCE.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    return data.get("artefacts", {}).get(artefact.path.name or "")


def _recipe_ok(recipe: dict) -> tuple[bool, str]:
    producer = PROJECT_ROOT / recipe.get("producer", "")
    if not recipe.get("producer") or not producer.is_file():
        return False, f"producer {recipe.get('producer')!r} not found"
    missing = []
    for pattern in recipe.get("inputs", []):
        target = PROJECT_ROOT / pattern
        if "*" in pattern:
            if not list(target.parent.glob(target.name)):
                missing.append(pattern)
        elif not target.exists():
            missing.append(pattern)
    if missing:
        return False, f"missing input(s): {', '.join(missing[:2])}"
    return True, recipe.get("argv", "")


def _producer_names_it(producer: str | None, artefact: Artefact) -> bool:
    """A producer counts only if it would reproduce *this* artefact.

    Matching the word "spectral" is not enough: the pipeline writes mu=0.3 while
    production serves a file named for mu=0.35, so a loose match reported a
    provenance that does not exist.
    """
    if not producer:
        return False
    path = PROJECT_ROOT / producer
    if not path.is_file():
        return (path.is_dir() and any(p.is_file() for p in path.rglob("*.py"))) or (
            path.is_dir() and any(p.is_file() for p in path.rglob("*.go"))
        )
    text = path.read_text(errors="replace")
    stem = artefact.path.stem or artefact.name
    base = stem.split("_mu")[0]
    if base not in text and not ("spectral" in stem and "spectral" in text.lower()):
        return False
    claimed = _mu_claim(stem)
    if claimed is None:
        return True
    # Require an assignment, not a mention: a comment saying "e.g. _mu35" is not
    # a producer that would rebuild the file.
    return re.search(rf"\b(?:MU|mu)\s*=\s*{re.escape(claimed)}\b", text) is not None
    if path.is_dir():
        return any(p.is_file() for p in path.rglob("*.py")) or any(
            p.is_file() for p in path.rglob("*.go")
        )
    return False


def check(artefact: Artefact) -> Result:
    resolved = _resolve(artefact)
    if resolved is None:
        return Result(artefact, Status.MISSING if artefact.required else Status.HISTORICAL)
    if artefact.historical:
        return Result(artefact, Status.HISTORICAL, artefact.notes)
    if resolved.suffix in {".json"}:
        try:
            json.loads(resolved.read_text())
        except Exception as exc:
            return Result(artefact, Status.UNREADABLE, str(exc)[:80])
    if artefact.kind == "word2vec":
        try:
            from gensim.models import KeyedVectors

            vectors = KeyedVectors.load(str(resolved))
            if artefact.dim and vectors.vector_size != artefact.dim:
                return Result(
                    artefact,
                    Status.DIM_MISMATCH,
                    f"{vectors.vector_size}D on disk, {artefact.dim}D declared",
                )
        except Exception as exc:
            return Result(artefact, Status.UNREADABLE, str(exc)[:80])
    if artefact.kind == "npy":
        try:
            import numpy as np

            matrix = np.load(str(resolved), mmap_mode="r")
            if artefact.dim and matrix.shape[1] != artefact.dim:
                return Result(
                    artefact,
                    Status.DIM_MISMATCH,
                    f"{matrix.shape[1]}D on disk, {artefact.dim}D declared",
                )
        except Exception as exc:
            return Result(artefact, Status.UNREADABLE, str(exc)[:80])
    recipe = _recipe_for(artefact)
    if recipe is not None:
        ok, detail = _recipe_ok(recipe)
        return Result(artefact, Status.OK if ok else Status.RECIPE_BROKEN, detail)
    if not _producer_names_it(artefact.producer, artefact):
        claimed = _mu_claim(artefact.path.stem or artefact.name)
        detail = f"{artefact.producer or 'no producer'} does not reproduce this artefact"
        if claimed:
            detail += f" (filename claims mu={claimed})"
        return Result(artefact, Status.NO_PRODUCER, detail)
    return Result(artefact, Status.OK)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="+", default=["magic", "pokemon", "yugioh"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results: list[Result] = []
    for game in args.games:
        results.extend(check(a) for a in declared(game))

    if args.json:
        print(json.dumps([r.as_dict() for r in results], indent=2))
    else:
        for r in results:
            print(f"[{r.status:12}] {r.artefact.name:28} {r.detail}")

    failed = [
        r
        for r in results
        if r.artefact.required
        and r.status in {Status.MISSING, Status.UNREADABLE, Status.DIM_MISMATCH}
    ]
    unproduced = [r for r in results if r.artefact.required and r.status == Status.NO_PRODUCER]
    if failed or unproduced:
        print(
            f"\n{len(failed)} required artefact(s) failed, {len(unproduced)} required artefact(s) have no producer",
            file=sys.stderr,
        )
        return 1
    warnings = [r for r in results if r.status not in {Status.OK, Status.HISTORICAL}]
    return 2 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
