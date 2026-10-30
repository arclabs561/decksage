#!/usr/bin/env python3
"""Screen annotation corpora for structurally impossible or implausible judgments.

The screen is deterministic and read-only. It loads the card metadata the repo
already ships under ``data/processed`` and flags rule-based contradictions in
JSON and JSONL annotation corpora. Each hit carries a rule id, a severity, the
card names, the score, the field values that triggered it, and the source file
plus line (JSONL) or record path (JSON).

Two rules are unambiguous enough to curate: self-pairs and duplicate pairs
inside one file whose scores disagree materially. Curation writes copies under
an output directory; inputs are never modified. Every input and output is
hashed in the ledger.

A hit is a review candidate. Counts are not an error rate: the screen can only
see contradictions expressible against local metadata, and a missing hit is not
evidence that a judgment is correct.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.utils.paths import PATHS


try:  # Canonical bands; duplicated only as an import fallback.
    from ml.contracts.annotations import BUCKET_BANDS
except ImportError:  # pragma: no cover - the package is installed in this repo
    BUCKET_BANDS = {
        "highly_relevant": (0.70, 1.01),
        "relevant": (0.50, 0.70),
        "somewhat_relevant": (0.30, 0.50),
        "marginally_relevant": (0.15, 0.30),
        "irrelevant": (0.0, 0.15),
    }


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# A pair record must carry two names under one of these key pairs.
NAME_KEY_PAIRS = (
    ("card1", "card2"),
    ("query", "candidate"),
    ("card_a", "card_b"),
    ("card_a_name", "card_b_name"),
    ("a", "b"),
)
SCORE_KEYS = ("similarity_score", "consensus_score", "score", "similarity")
BUCKETS = tuple(BUCKET_BANDS)

# Thresholds. The same number is used across games so a count is comparable.
HIGH_SCORE = 0.70
SUBSTITUTION_SCORE = 0.60
MAGIC_KIND_SCORE = 0.85
YUGIOH_TYPE_SCORE = 0.85
DUPLICATE_DELTA = 0.30
DUPLICATE_DELTA_HIGH = 0.50

RULES: dict[str, dict[str, str]] = {
    "self_pair": {
        "severity": "high",
        "description": "A card is judged against itself.",
    },
    "kind_conflict": {
        "severity": "medium/high",
        "description": (
            "A creature is judged against a Trainer/Energy/Spell/Trap with a high score "
            "under a substitution intent."
        ),
    },
    "evolution_conflict": {
        "severity": "medium/high",
        "description": (
            "Different Pokemon evolution stages are judged as substitutes with a high score."
        ),
    },
    "type_conflict": {
        "severity": "medium/high",
        "description": (
            "Pokemon energy types or Yu-Gi-Oh attributes differ, with a high substitution score."
        ),
    },
    "score_evidence_conflict": {
        "severity": "medium",
        "description": (
            "A high score has no oracle text for at least one card and no name-token overlap."
        ),
    },
    "duplicate_conflict": {
        "severity": "medium/high",
        "description": (
            "The same unordered pair is judged more than once in one file with materially "
            "different scores."
        ),
    },
    "bucket_mismatch": {
        "severity": "low",
        "description": (
            "The record's own score falls outside the band of the bucket it claims or is listed in."
        ),
    },
}

# Kinds that cannot substitute for a creature in each game. Magic is narrower:
# artifacts and enchantments are permanent support and cross-type substitution
# is sometimes arguable, so only non-permanent spells are screened.
NON_CREATURE_KINDS = {
    "magic": {"instant", "sorcery"},
    "pokemon": {"trainer", "energy"},
    "yugioh": {"spell", "trap"},
}
EVOLUTION_STAGES = {"basic": 0, "stage1": 1, "stage2": 2}
POKEMON_ENERGY_TYPES = (
    "Colorless",
    "Grass",
    "Fire",
    "Water",
    "Lightning",
    "Psychic",
    "Fighting",
    "Darkness",
    "Metal",
    "Dragon",
    "Fairy",
)


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_name(name: str) -> str:
    """Fold case, punctuation and spacing so key lookups are stable.

    Unicode alphanumerics are kept: ``Miracle Sphere α`` and ``Miracle Sphere
    γ`` are different cards, and an ASCII-only filter collapses them.
    """
    return "".join(character for character in name.casefold() if character.isalnum())


def identity_name(name: str) -> str:
    """Card identity for self/duplicate checks.

    Case and decorative separators are folded, but symbols that distinguish
    cards are kept: ``Nidoran ♀``/``♂``, ``Unown [?]``/``[!]``, ``Ditto ◇`` and
    ``Miracle Sphere α``/``γ`` must not collapse into one card.
    """
    folded = re.sub(r"[\s\-_.,'\"]+", " ", name.casefold())
    return folded.strip()


def name_tokens(name: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", name.casefold()) if len(token) >= 3}


def pair_key(card_a: str, card_b: str) -> tuple[str, str]:
    left, right = identity_name(card_a), identity_name(card_b)
    return (left, right) if left <= right else (right, left)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class CardMeta:
    """The few metadata fields the screen can reason about."""

    name: str
    game: str
    kind: str
    stage: str | None = None
    energy_type: str | None = None
    attribute: str | None = None
    oracle_text: str = ""
    type_line: str = ""


@dataclass
class PairRecord:
    card_a: str
    card_b: str
    score: float
    game: str
    mode: str | None
    is_substitute: bool
    relevance: str | None
    bucket_membership: str | None
    source_file: str
    line: int | None
    record_path: str
    raw: dict[str, Any] = field(repr=False, default_factory=dict)


@dataclass
class Hit:
    rule_id: str
    severity: str
    game: str
    card_a: str
    card_b: str
    score: float | None
    evidence: dict[str, Any]
    source_file: str
    line: int | None
    record_path: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "game": self.game,
            "card_a": self.card_a,
            "card_b": self.card_b,
            "score": self.score,
            "evidence": self.evidence,
            "source_file": self.source_file,
            "line": self.line,
            "record_path": self.record_path,
        }


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def _pokemon_stage(type_line: str) -> str | None:
    head = type_line.removeprefix("Pokémon").strip()
    if head.startswith("Basic"):
        return "basic"
    if head.startswith("Stage 1"):
        return "stage1"
    if head.startswith("Stage 2"):
        return "stage2"
    return None


def _pokemon_energy_type(row: dict[str, str]) -> str | None:
    text = row.get("oracle_text") or ""
    match = re.search(r"\b(" + "|".join(POKEMON_ENERGY_TYPES) + r")\s*-\s*HP\b", text)
    if match:
        return match.group(1)
    leading = re.match(r"Pokémon[^-]*-+\s*([A-Za-z]+)\s*-", text)
    if leading and leading.group(1) in POKEMON_ENERGY_TYPES:
        return leading.group(1)
    return None


def _magic_kind(type_line: str) -> str:
    lowered = type_line.casefold()
    if "creature" in lowered:
        return "creature"
    for kind in ("instant", "sorcery", "artifact", "enchantment", "planeswalker", "land"):
        if kind in lowered:
            return kind
    return "other"


def load_metadata(
    metadata_dir: Path,
) -> tuple[dict[str, dict[str, CardMeta]], list[dict[str, Any]]]:
    """Load per-game name -> metadata from the enriched CSVs the repo ships."""
    files = {
        "magic": metadata_dir / "card_attributes_magic_enriched.csv",
        "pokemon": metadata_dir / "card_attributes_pokemon_enriched.csv",
        "yugioh": metadata_dir / "card_attributes_yugioh_enriched.csv",
    }
    fallback = {"magic": metadata_dir / "card_attributes_enriched.csv"}
    import csv

    lookup: dict[str, dict[str, CardMeta]] = {}
    ledger: list[dict[str, Any]] = []
    for game, path in files.items():
        by_name: dict[str, CardMeta] = {}
        rows = 0
        if not path.exists() and game in fallback:
            path = fallback[game]
        if not path.exists():
            ledger.append({"game": game, "path": str(path), "exists": False, "rows": 0})
            lookup[game] = by_name
            continue
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            for row in csv.DictReader(handle):
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                type_line = (row.get("type") or "").strip()
                if game == "pokemon":
                    supertype = (row.get("supertype") or "").strip()
                    if type_line.startswith("Pokémon") or supertype == "Pokémon":
                        kind = "creature"
                    elif type_line.startswith("Trainer"):
                        kind = "trainer"
                    elif type_line.startswith("Energy"):
                        kind = "energy"
                    else:
                        kind = "other"
                    meta = CardMeta(
                        name=name,
                        game=game,
                        kind=kind,
                        stage=_pokemon_stage(type_line),
                        energy_type=_pokemon_energy_type(row),
                        oracle_text=(row.get("oracle_text") or "").strip(),
                        type_line=type_line,
                    )
                elif game == "magic":
                    meta = CardMeta(
                        name=name,
                        game=game,
                        kind=_magic_kind(type_line),
                        oracle_text=(row.get("oracle_text") or "").strip(),
                        type_line=type_line,
                    )
                else:
                    category = (row.get("card_category") or "").strip().casefold()
                    kind = {"monster": "creature", "spell": "spell", "trap": "trap"}.get(
                        category, "other"
                    )
                    meta = CardMeta(
                        name=name,
                        game=game,
                        kind=kind,
                        attribute=(row.get("attribute") or "").strip() or None,
                        oracle_text=(row.get("oracle_text") or "").strip(),
                        type_line=type_line,
                    )
                by_name.setdefault(normalize_name(name), meta)
                rows += 1
        lookup[game] = by_name
        ledger.append(
            {
                "game": game,
                "path": display_path(path),
                "exists": True,
                "rows": rows,
                "sha256": sha256_file(path),
            }
        )
    return lookup, ledger


def metadata_for(table: dict[str, dict[str, CardMeta]], game: str, name: str) -> CardMeta | None:
    return table.get(game, {}).get(normalize_name(name))


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------


def infer_game(path: Path, record_game: Any, context_game: Any) -> str:
    for value in (record_game, context_game):
        if isinstance(value, str) and value.casefold() in ("magic", "pokemon", "yugioh"):
            return value.casefold()
    lowered = path.name.casefold()
    for game in ("magic", "pokemon", "yugioh", "digimon", "onepiece"):
        if game in lowered:
            return game
    return "unknown"


def resolve_score(record: dict[str, Any]) -> float | None:
    for key in SCORE_KEYS:
        value = record.get(key)
        if is_number(value):
            return float(value)
    consensus = record.get("consensus")
    if isinstance(consensus, dict):
        for key in SCORE_KEYS:
            value = consensus.get(key)
            if is_number(value):
                return float(value)
    return None


def extract_names(record: dict[str, Any]) -> tuple[str, str] | None:
    for left, right in NAME_KEY_PAIRS:
        first, second = record.get(left), record.get(right)
        if isinstance(first, str) and isinstance(second, str) and first.strip() and second.strip():
            return first.strip(), second.strip()
    return None


def _bucket_map(entry: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for bucket in BUCKETS:
        members = entry.get(bucket)
        if isinstance(members, list):
            for member in members:
                if isinstance(member, str):
                    mapping[normalize_name(member)] = bucket
    return mapping


def walk_json(
    node: Any,
    *,
    path: Path,
    record_path: str,
    game: str,
    bucket_map: dict[str, str],
    line: int | None = None,
) -> Iterator[PairRecord]:
    if isinstance(node, dict):
        local_game = node.get("game") if isinstance(node.get("game"), str) else game
        local_buckets = bucket_map
        if any(bucket in node and isinstance(node.get(bucket), list) for bucket in BUCKETS):
            local_buckets = _bucket_map(node)
        names = extract_names(node)
        score = resolve_score(node)
        if names is not None and score is not None and 0.0 <= score <= 1.0:
            card_a, card_b = names
            mode = node.get("mode") if isinstance(node.get("mode"), str) else None
            relevance = node.get("relevance") if isinstance(node.get("relevance"), str) else None
            yield PairRecord(
                card_a=card_a,
                card_b=card_b,
                score=score,
                game=infer_game(path, local_game, game),
                mode=mode,
                is_substitute=bool(node.get("is_substitute") is True),
                relevance=relevance,
                bucket_membership=local_buckets.get(normalize_name(card_b)),
                source_file=display_path(path),
                line=line,
                record_path=record_path,
                raw=node,
            )
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                child_path = f"{record_path}.{key}" if record_path else str(key)
                yield from walk_json(
                    value,
                    path=path,
                    record_path=child_path,
                    game=local_game,
                    bucket_map=local_buckets,
                    line=line,
                )
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child_path = f"{record_path}[{index}]"
            yield from walk_json(
                value,
                path=path,
                record_path=child_path,
                game=game,
                bucket_map=bucket_map,
                line=line,
            )


def records_from_json(path: Path) -> Iterator[PairRecord]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return
    game_hint = ""
    if isinstance(data, dict):
        meta_block = data.get("meta")
        for candidate in (
            data.get("game"),
            meta_block.get("game") if isinstance(meta_block, dict) else None,
        ):
            if isinstance(candidate, str):
                game_hint = candidate
                break
        # Consensus files key labels by "card_a||card_b"; only the continuous
        # score is numeric, the Dawid-Skene and GLAD blocks hold band strings.
        continuous = data.get("continuous_consensus")
        if isinstance(continuous, dict):
            for key, value in continuous.items():
                if "||" not in key or not isinstance(value, dict):
                    continue
                score = value.get("consensus_score")
                if not is_number(score) or not 0.0 <= float(score) <= 1.0:
                    continue
                card_a, card_b = (part.strip() for part in key.split("||", 1))
                yield PairRecord(
                    card_a=card_a,
                    card_b=card_b,
                    score=float(score),
                    game=infer_game(path, game_hint, ""),
                    mode=None,
                    is_substitute=False,
                    relevance=None,
                    bucket_membership=None,
                    source_file=display_path(path),
                    line=None,
                    record_path=f"continuous_consensus.{key}",
                    raw=value,
                )
    yield from walk_json(data, path=path, record_path="", game=game_hint, bucket_map={})


def records_from_jsonl(path: Path) -> Iterator[PairRecord]:
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield from walk_json(
                    record,
                    path=path,
                    record_path="",
                    game="",
                    bucket_map={},
                    line=line_number,
                )
            elif isinstance(record, list):
                yield from walk_json(
                    record,
                    path=path,
                    record_path="",
                    game="",
                    bucket_map={},
                    line=line_number,
                )


def discover_corpora(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
            continue
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix not in {".json", ".jsonl"}:
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            if "archive" in path.parts:
                continue
            files.append(path)
    return files


def load_records(path: Path) -> list[PairRecord]:
    if path.suffix == ".jsonl":
        return list(records_from_jsonl(path))
    return list(records_from_json(path))


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def is_ineligible(record: PairRecord) -> bool:
    """Known-failed, synthetic or cosine-fallback records are already excluded."""
    raw = record.raw
    provenance = raw.get("_provenance")
    return bool(
        raw.get("error") is True
        or raw.get("synthetic") is True
        or raw.get("llm_model") == "cosine_fallback"
        or (isinstance(provenance, dict) and provenance.get("augmentation"))
    )


def substitution_intent(record: PairRecord) -> bool:
    """True when the record asks for substitution, not synergy or meta.

    An explicit synergy/meta mode wins over a stray ``is_substitute`` flag:
    otherwise a record that contradicts itself is charged to the wrong rule.
    """
    mode = (record.mode or "").casefold()
    if mode in {"substitution", "substitute"}:
        return True
    if mode in {"synergy", "meta", "unknown"}:
        return False
    return record.is_substitute


def check_self_pair(record: PairRecord, meta: dict[str, dict[str, CardMeta]]) -> Hit | None:
    del meta
    if identity_name(record.card_a) != identity_name(record.card_b):
        return None
    return Hit(
        rule_id="self_pair",
        severity="high",
        game=record.game,
        card_a=record.card_a,
        card_b=record.card_b,
        score=record.score,
        evidence={"identity_name": identity_name(record.card_a)},
        source_file=record.source_file,
        line=record.line,
        record_path=record.record_path,
    )


def check_kind_conflict(record: PairRecord, meta: dict[str, dict[str, CardMeta]]) -> Hit | None:
    left = metadata_for(meta, record.game, record.card_a)
    right = metadata_for(meta, record.game, record.card_b)
    if left is None or right is None:
        return None
    threshold = MAGIC_KIND_SCORE if record.game == "magic" else HIGH_SCORE
    if record.score < threshold or not substitution_intent(record):
        return None
    support = NON_CREATURE_KINDS.get(record.game, set())
    kinds = (left.kind, right.kind)
    if not (("creature" in kinds) and (kinds[0] in support or kinds[1] in support)):
        return None
    return Hit(
        rule_id="kind_conflict",
        severity="high" if record.score >= 0.80 else "medium",
        game=record.game,
        card_a=record.card_a,
        card_b=record.card_b,
        score=record.score,
        evidence={
            "kind_a": left.kind,
            "kind_b": right.kind,
            "type_line_a": left.type_line,
            "type_line_b": right.type_line,
            "mode": record.mode,
            "is_substitute": record.is_substitute,
            "threshold": threshold,
        },
        source_file=record.source_file,
        line=record.line,
        record_path=record.record_path,
    )


def check_evolution_conflict(
    record: PairRecord, meta: dict[str, dict[str, CardMeta]]
) -> Hit | None:
    if record.game != "pokemon" or not substitution_intent(record):
        return None
    left = metadata_for(meta, record.game, record.card_a)
    right = metadata_for(meta, record.game, record.card_b)
    if left is None or right is None or left.stage is None or right.stage is None:
        return None
    if left.stage == right.stage:
        return None
    if EVOLUTION_STAGES[left.stage] == EVOLUTION_STAGES[right.stage]:
        return None
    if record.score < SUBSTITUTION_SCORE:
        return None
    return Hit(
        rule_id="evolution_conflict",
        severity="high" if record.score >= 0.75 else "medium",
        game=record.game,
        card_a=record.card_a,
        card_b=record.card_b,
        score=record.score,
        evidence={
            "stage_a": left.stage,
            "stage_b": right.stage,
            "type_line_a": left.type_line,
            "type_line_b": right.type_line,
            "mode": record.mode,
            "is_substitute": record.is_substitute,
            "threshold": SUBSTITUTION_SCORE,
        },
        source_file=record.source_file,
        line=record.line,
        record_path=record.record_path,
    )


def check_type_conflict(record: PairRecord, meta: dict[str, dict[str, CardMeta]]) -> Hit | None:
    if not substitution_intent(record):
        return None
    left = metadata_for(meta, record.game, record.card_a)
    right = metadata_for(meta, record.game, record.card_b)
    if left is None or right is None:
        return None
    if record.game == "pokemon":
        if (
            left.energy_type is None
            or right.energy_type is None
            or left.energy_type == right.energy_type
        ):
            return None
        if record.score < HIGH_SCORE:
            return None
        fields = {"energy_type_a": left.energy_type, "energy_type_b": right.energy_type}
        threshold = HIGH_SCORE
    elif record.game == "yugioh":
        if left.attribute is None or right.attribute is None or left.attribute == right.attribute:
            return None
        if record.score < YUGIOH_TYPE_SCORE:
            return None
        fields = {"attribute_a": left.attribute, "attribute_b": right.attribute}
        threshold = YUGIOH_TYPE_SCORE
    else:
        return None
    fields.update(
        {
            "mode": record.mode,
            "is_substitute": record.is_substitute,
            "threshold": threshold,
        }
    )
    return Hit(
        rule_id="type_conflict",
        severity="high" if record.score >= 0.90 else "medium",
        game=record.game,
        card_a=record.card_a,
        card_b=record.card_b,
        score=record.score,
        evidence=fields,
        source_file=record.source_file,
        line=record.line,
        record_path=record.record_path,
    )


def check_score_evidence(record: PairRecord, meta: dict[str, dict[str, CardMeta]]) -> Hit | None:
    if record.score < HIGH_SCORE:
        return None
    if len(normalize_name(record.card_a)) < 2 or len(normalize_name(record.card_b)) < 2:
        return None
    left = metadata_for(meta, record.game, record.card_a)
    right = metadata_for(meta, record.game, record.card_b)
    if left is not None and right is not None:
        if left.oracle_text and right.oracle_text:
            return None
    if name_tokens(record.card_a) & name_tokens(record.card_b):
        return None
    metadata_present = left is not None and right is not None
    return Hit(
        rule_id="score_evidence_conflict",
        # Absent metadata cannot be distinguished from absent evidence, so it
        # is a coverage note, not a medium-severity judgment contradiction.
        severity="medium" if metadata_present else "low",
        game=record.game,
        card_a=record.card_a,
        card_b=record.card_b,
        score=record.score,
        evidence={
            "metadata_a": left is not None,
            "metadata_b": right is not None,
            "metadata_missing": not metadata_present,
            "oracle_text_a_empty": left is None or not left.oracle_text,
            "oracle_text_b_empty": right is None or not right.oracle_text,
            "name_overlap": [],
            "threshold": HIGH_SCORE,
        },
        source_file=record.source_file,
        line=record.line,
        record_path=record.record_path,
    )


def expected_bucket(score: float) -> str:
    for bucket, (low, high) in BUCKET_BANDS.items():
        if low <= score < high:
            return bucket
    return "irrelevant" if score < 0.15 else "highly_relevant"


def check_bucket_mismatch(record: PairRecord, meta: dict[str, dict[str, CardMeta]]) -> Hit | None:
    del meta
    expected = expected_bucket(record.score)
    claimed = record.relevance
    membership = record.bucket_membership
    mismatched_relevance = claimed is not None and claimed != expected
    mismatched_membership = claimed is None and membership is not None and membership != expected
    if not (mismatched_relevance or mismatched_membership):
        return None
    return Hit(
        rule_id="bucket_mismatch",
        severity="low",
        game=record.game,
        card_a=record.card_a,
        card_b=record.card_b,
        score=record.score,
        evidence={
            "claimed_bucket": claimed,
            "bucket_membership": membership,
            "expected_bucket": expected,
            "bands": {name: list(band) for name, band in BUCKET_BANDS.items()},
        },
        source_file=record.source_file,
        line=record.line,
        record_path=record.record_path,
    )


RECORD_RULES = (
    check_self_pair,
    check_kind_conflict,
    check_evolution_conflict,
    check_type_conflict,
    check_score_evidence,
    check_bucket_mismatch,
)


def duplicate_hits(records: list[PairRecord]) -> list[Hit]:
    # Mode is part of the key: the same pair can legitimately score high for
    # synergy and low for substitution, so only same-task repeats are compared.
    groups: dict[tuple[str, tuple[str, str], str], list[PairRecord]] = defaultdict(list)
    for record in records:
        mode = (record.mode or "unknown").casefold()
        groups[(record.game, pair_key(record.card_a, record.card_b), mode)].append(record)
    hits: list[Hit] = []
    for (game, _key, mode), group in groups.items():
        if len(group) < 2:
            continue
        scores = [record.score for record in group]
        delta = max(scores) - min(scores)
        if delta < DUPLICATE_DELTA:
            continue
        first = group[0]
        hits.append(
            Hit(
                rule_id="duplicate_conflict",
                severity="high" if delta >= DUPLICATE_DELTA_HIGH else "medium",
                game=game,
                card_a=first.card_a,
                card_b=first.card_b,
                score=max(scores),
                evidence={
                    "occurrences": len(group),
                    "mode": mode,
                    "scores": scores,
                    "delta": round(delta, 6),
                    "lines": [record.line for record in group],
                    "record_paths": [record.record_path for record in group],
                },
                source_file=first.source_file,
                line=first.line,
                record_path=first.record_path,
            )
        )
    return hits


def resolve_game(record: PairRecord, meta: dict[str, dict[str, CardMeta]]) -> None:
    """Infer a missing game from the metadata that contains both card names."""
    if record.game in meta:
        return
    left, right = normalize_name(record.card_a), normalize_name(record.card_b)
    matches = [game for game, table in meta.items() if left in table and right in table]
    if len(matches) == 1:
        record.game = matches[0]


def screen_records(records: list[PairRecord], meta: dict[str, dict[str, CardMeta]]) -> list[Hit]:
    hits: list[Hit] = []
    seen: set[tuple[str, str, str, str, int | None]] = set()
    for record in records:
        resolve_game(record, meta)
        for rule in RECORD_RULES:
            hit = rule(record, meta)
            if hit is None:
                continue
            marker = (hit.rule_id, hit.source_file, hit.card_a, hit.card_b, hit.line)
            if marker in seen:
                continue
            seen.add(marker)
            hits.append(hit)
    hits.extend(duplicate_hits(records))
    return hits


# ---------------------------------------------------------------------------
# Curation (copy-first)
# ---------------------------------------------------------------------------


def _drop_reason(
    record: dict[str, Any],
    self_pairs: set[tuple[str, str]],
    conflicting: set[tuple[tuple[str, str], str]],
) -> dict[str, Any] | None:
    names = extract_names(record)
    if names is None:
        return None
    key = pair_key(*names)
    score = resolve_score(record)
    if key in self_pairs:
        return {
            "reason": "self_pair",
            "card_a": names[0],
            "card_b": names[1],
            "score": score,
        }
    mode = record.get("mode") if isinstance(record.get("mode"), str) else "unknown"
    if (key, mode.casefold()) in conflicting:
        return {
            "reason": "duplicate_conflict",
            "card_a": names[0],
            "card_b": names[1],
            "score": score,
            "mode": mode,
        }
    return None


def _curate_json(
    data: Any,
    key_prefix: str,
    self_pairs: set[tuple[str, str]],
    conflicting: set[tuple[tuple[str, str], str]],
    removed: list[dict[str, Any]],
) -> Any:
    """Filter a parsed copy in place, recording each removal with its path."""
    if isinstance(data, list):
        kept = []
        for index, item in enumerate(data):
            if isinstance(item, dict):
                reason = _drop_reason(item, self_pairs, conflicting)
                if reason is not None:
                    reason["record_path"] = f"{key_prefix}[{index}]"
                    removed.append(reason)
                    continue
            kept.append(item)
        return kept
    if isinstance(data, dict):
        for key, value in list(data.items()):
            child = f"{key_prefix}.{key}" if key_prefix else str(key)
            if isinstance(value, list):
                data[key] = _curate_json(value, child, self_pairs, conflicting, removed)
            elif isinstance(value, dict):
                data[key] = _curate_json(value, child, self_pairs, conflicting, removed)
    return data


def curate_corpus(
    path: Path, records: list[PairRecord], output_path: Path
) -> tuple[Path, list[dict]]:
    """Write a copy with self-pairs removed, and only self-pairs removed.

    Duplicate score dispersion is reported in a separate ledger instead of
    curated: repeated annotation rounds are a corpus design property, dropping
    every disagreeing member would delete roughly 40% of the checkpoint files,
    and no score inside a conflicting group is privileged.
    """
    self_pairs: set[tuple[str, str]] = {
        pair_key(record.card_a, record.card_b)
        for record in records
        if identity_name(record.card_a) == identity_name(record.card_b)
    }
    conflicting: set[tuple[tuple[str, str], str]] = set()
    removed: list[dict] = []

    if path.suffix == ".jsonl":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with (
            path.open(encoding="utf-8", errors="replace") as source,
            output_path.open("w", encoding="utf-8") as target,
        ):
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    target.write(line)
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    target.write(line)
                    continue
                if not isinstance(record, dict):
                    target.write(line)
                    continue
                reason = _drop_reason(record, self_pairs, conflicting)
                if reason is None:
                    target.write(line)
                    continue
                reason["line"] = line_number
                removed.append(reason)
    else:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        curated = _curate_json(data, "", self_pairs, conflicting, removed)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(curated, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    return output_path, removed


def write_duplicate_ledger(hits: list[Hit], output_path: Path) -> int:
    """One JSONL row per conflicting duplicate group, with every occurrence."""
    rows = [hit for hit in hits if hit.rule_id == "duplicate_conflict"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for hit in rows:
            handle.write(json.dumps(hit.as_dict(), ensure_ascii=False) + "\n")
    return len(rows)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def select_sample(hits: list[Hit], size: int) -> list[Hit]:
    """Round-robin across rules so no single rule dominates a small sample."""
    buckets: dict[str, list[Hit]] = {rule: [] for rule in RULES}
    for hit in hits:
        buckets[hit.rule_id].append(hit)
    sample: list[Hit] = []
    depth = 0
    while len(sample) < size and any(len(items) > depth for items in buckets.values()):
        for rule in RULES:
            items = buckets[rule]
            if depth < len(items) and len(sample) < size:
                sample.append(items[depth])
        depth += 1
    return sample


def summarize(hits: list[Hit]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {rule: {} for rule in RULES}
    for hit in hits:
        summary[hit.rule_id][hit.game] = summary[hit.rule_id].get(hit.game, 0) + 1
    return summary


def print_table(summary: dict[str, dict[str, int]]) -> None:
    games = sorted({game for per_rule in summary.values() for game in per_rule})
    header = ["rule", *games, "total"]
    width = max(len(header[0]), *(len(rule) for rule in summary))
    print(f"{header[0]:<{width}} " + " ".join(f"{game:>8}" for game in games) + f" {'total':>7}")
    for rule, per_game in summary.items():
        total = sum(per_game.values())
        cells = " ".join(f"{per_game.get(game, 0):>8}" for game in games)
        print(f"{rule:<{width}} {cells} {total:>7}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=PATHS.data / "annotations",
        help="annotation corpora directory (JSON and JSONL)",
    )
    parser.add_argument(
        "--test-sets-dir",
        type=Path,
        default=PATHS.data / "test_sets",
        help="evaluation test-set directory",
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=PATHS.data / "processed",
        help="directory holding card_attributes_*_enriched.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data-local/contradiction-screen-20261028",
        help="ledger, report JSON and curated copies; never inside data/",
    )
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument(
        "--curate",
        action="store_true",
        help="write filtered copies for self-pairs and conflicting duplicates",
    )
    args = parser.parse_args()

    output_dir: Path = args.output_dir
    data_dir = PROJECT_ROOT / "data"
    if (
        data_dir.resolve() in output_dir.resolve().parents
        or output_dir.resolve() == data_dir.resolve()
    ):
        parser.error("output dir must not be inside data/")
    output_dir.mkdir(parents=True, exist_ok=True)

    meta, meta_ledger = load_metadata(args.metadata_dir)
    corpora = discover_corpora([args.annotations_dir, args.test_sets_dir])

    all_hits: list[Hit] = []
    input_ledger: list[dict[str, Any]] = []
    curated_ledger: list[dict[str, Any]] = []
    for path in corpora:
        if not path.is_file():
            continue
        loaded = load_records(path)
        if not loaded:
            continue
        records = [record for record in loaded if not is_ineligible(record)]
        skipped = len(loaded) - len(records)
        hits = screen_records(records, meta)
        all_hits.extend(hits)
        input_ledger.append(
            {
                "path": display_path(path),
                "records": len(records),
                "ineligible_skipped": skipped,
                "hits": len(hits),
                "sha256": sha256_file(path),
            }
        )
        if args.curate and any(hit.rule_id == "self_pair" for hit in hits):
            relative = path.relative_to(PROJECT_ROOT)
            output_path = output_dir / "curated" / relative
            written, removed = curate_corpus(path, records, output_path)
            curated_ledger.append(
                {
                    "source": str(relative),
                    "output": display_path(written),
                    "output_sha256": sha256_file(written),
                    "removed": removed,
                }
            )

    duplicate_ledger = write_duplicate_ledger(
        all_hits, output_dir / "ledger" / "duplicate_conflicts.jsonl"
    )

    all_hits.sort(
        key=lambda hit: (
            SEVERITY_ORDER.get(hit.severity, 9),
            -(hit.score or 0.0),
            hit.source_file,
            hit.line or 0,
        )
    )
    summary = summarize(all_hits)
    sample_hits = select_sample(all_hits, args.sample_size)
    sample = [hit.as_dict() for hit in sample_hits]

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "rules": RULES,
        "thresholds": {
            "high_score": HIGH_SCORE,
            "substitution_score": SUBSTITUTION_SCORE,
            "magic_kind_score": MAGIC_KIND_SCORE,
            "yugioh_type_score": YUGIOH_TYPE_SCORE,
            "duplicate_delta": DUPLICATE_DELTA,
        },
        "metadata": meta_ledger,
        "inputs": input_ledger,
        "summary": summary,
        "ineligible_skipped": sum(row["ineligible_skipped"] for row in input_ledger),
        "total_hits": len(all_hits),
        "sample": sample,
        "hits": [hit.as_dict() for hit in all_hits],
        "curated": curated_ledger,
        "duplicate_ledger": {
            "path": str(
                (output_dir / "ledger/duplicate_conflicts.jsonl").relative_to(PROJECT_ROOT)
            ),
            "groups": duplicate_ledger,
        },
    }
    report_path = output_dir / "report.json"
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(f"corpora={len(input_ledger)} records={sum(row['records'] for row in input_ledger)}")
    print_table(summary)
    print(f"\ntop {len(sample)} by severity/score:")
    for hit in sample:
        location = (
            f"{hit['source_file']}:{hit['line']}"
            if hit["line"] is not None
            else f"{hit['source_file']} {hit['record_path']}"
        )
        print(
            f"  [{hit['severity']}] {hit['rule_id']} {hit['game']} "
            f"{hit['card_a']!r} vs {hit['card_b']!r} score={hit['score']} at {location}"
        )
    hash_lines: list[str] = []
    for row in input_ledger:
        hash_lines.append(f"{row['sha256']}  {row['path']}")
    for row in meta_ledger:
        if row.get("sha256"):
            hash_lines.append(f"{row['sha256']}  {row['path']}")
    hash_lines.append(f"{sha256_file(report_path)}  {display_path(report_path)}")
    ledger_path = output_dir / "ledger" / "duplicate_conflicts.jsonl"
    if ledger_path.exists():
        hash_lines.append(f"{sha256_file(ledger_path)}  {display_path(ledger_path)}")
    for row in curated_ledger:
        hash_lines.append(f"{row['output_sha256']}  {row['output']}")
    sums_path = output_dir / "SHA256SUMS.txt"
    sums_path.write_text("\n".join(sorted(hash_lines)) + "\n", encoding="utf-8")
    print(f"hashes={display_path(sums_path)} lines={len(hash_lines)}")

    print(f"\nreport={report_path.relative_to(PROJECT_ROOT)}")
    print(f"report_sha256={sha256_file(report_path)}")
    for row in input_ledger:
        print(f"input_sha256={row['sha256']} {row['path']}")
    for row in curated_ledger:
        print(f"curated_sha256={row['output_sha256']} {row['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
