#!/usr/bin/env python3
"""Rebuild deck derived training corpora: deck identity, name resolution, pair edges.

Three separable stages, each streaming:

  dedupe   per-source deduplication keyed on a normalised deck identity
           (the sorted card multiset), keeping the earliest record
  resolve  map deck card names onto ``card_attributes_{game}_enriched.csv``
  pairs    co-occurrence edge list in the ``pairs_large.csv`` schema

Why name resolution needs care here: the training pipeline itself performs no
name normalisation at all. ``scripts/training/build_unified_graph.py`` passes
deck and edgelist names verbatim into ``IncrementalCardGraph.add_edge`` (which
only sorts the two names), ``src/ml/utils/data_loading.load_edgelist`` yields
them unmodified, and the metadata join is an exact string lookup. So
``pipeline_key`` -- strip, nothing else -- is the *measured* baseline rule below.
Every other rule in ``NameIndex.resolve`` is an explicitly named repair that
has to earn its rows by a uniqueness check against the metadata table.

Usage (from the repository root):

    .venv/bin/python scripts/training/corpora_rebuild.py dedupe \\
        --game magic --out-dir data-local/corpora-rebuild-20261030
    .venv/bin/python scripts/training/corpora_rebuild.py resolve --out-dir ...
    .venv/bin/python scripts/training/corpora_rebuild.py pairs \\
        --game magic --out-dir data-local/corpora-rebuild-20261030
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data"
PROCESSED = DATA / "processed"

# Mirrors the ``deck_jsonl`` lists in scripts/training/build_unified_graph.py.
# decks_magic_commander.jsonl is not in that list and is therefore excluded.
TRAINING_CORPORA: dict[str, list[str]] = {
    "magic": [
        "decks_magic_goldfish.jsonl",
        "decks_magic_commander_combined.jsonl",
        "decks_magic_commander_extended.jsonl",
        "decks_magic_commander_seq.jsonl",
        "decks_magic_mtgtop8.jsonl",
        "decks_magic_moxfield_commander.jsonl",
        "decks_magic_moxfield_modern.jsonl",
        "decks_magic_moxfield_pioneer.jsonl",
        "decks_magic_moxfield_standard.jsonl",
        "decks_magic_archidekt_commander.jsonl",
        "decks_magic_archidekt_modern.jsonl",
    ],
    "yugioh": [
        "decks_yugioh_resolved.jsonl",
        "decks_yugioh_ygoprodeck-tournament.jsonl",
        "decks_yugioh_masterduelmeta.jsonl",
    ],
    "pokemon": [
        "decks_pokemon.jsonl",
        "decks_pokemon_limitless.jsonl",
        "decks_pokemon_limitless_expanded.jsonl",
        "decks_pokemon_limitless-web.jsonl",
        "decks_pokemon_limitless-web-expanded.jsonl",
    ],
}

NUMERIC_ID_RE = re.compile(r"^Card_\d+$")


# ── Name keys ───────────────────────────────────────────────────────────────


def pipeline_key(name: str) -> str:
    """Return the key the training pipeline actually matches on.

    Evidence: build_unified_graph.add_edge sorts raw names; load_edgelist
    yields raw names; the card_attributes join is a plain dict/set lookup.
    """
    return (name or "").strip()


def loose_key(name: str) -> str:
    """NFKC + whitespace collapse + casefold (the audit's second tier)."""
    folded = unicodedata.normalize("NFKC", name or "").strip()
    return " ".join(folded.split()).casefold()


def accent_key(name: str) -> str:
    """NFKD with combining marks dropped, then casefold (diacritic-insensitive)."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.split()).casefold()


# Typographic variants that card databases disagree about: en/em dashes in
# Yu-Gi-Oh! and Pokemon names ("Gold Pride – Nytro Head" vs "-"), curly
# apostrophes ("Fabled Realm’s Revival") and curly double quotes
# ("Gigantic “Champion” Sargas"). Folding them is a lookup-only repair: the
# canonical output is always the metadata spelling.
_PUNCT_MAP = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u00b4": "'",
    "\u0060": "'",
}


def punct_fold(name: str) -> str:
    """Fold typographic punctuation variants, then collapse and casefold."""
    folded = "".join(_PUNCT_MAP.get(ch, ch) for ch in (name or ""))
    folded = unicodedata.normalize("NFKC", folded)
    return " ".join(folded.split()).casefold()


def face_split(name: str) -> list[str]:
    """Split a Magic multi-face name on `` // `` or `` / ``."""
    for sep in (" // ", " / "):
        if sep in name:
            return [part.strip() for part in name.split(sep) if part.strip()]
    return [name]


def iter_deck_cards(deck: dict[str, Any]) -> Iterator[tuple[str, int]]:
    """Yield (name, count) for both deck layouts used in data/decks/."""
    for card in deck.get("cards") or []:
        if isinstance(card, dict):
            name = (card.get("name") or "").strip()
            count = card.get("count", 1)
        else:
            name, count = str(card).strip(), 1
        if name:
            yield name, int(count or 0)
    for partition in deck.get("partitions") or []:
        for card in partition.get("cards") or []:
            if isinstance(card, dict):
                name = (card.get("name") or "").strip()
                count = card.get("count", 1)
            else:
                name, count = str(card).strip(), 1
            if name:
                yield name, int(count or 0)


def deck_signature(cards: Iterable[tuple[str, int]]) -> str:
    """Stable identity of a deck: sha256 over its sorted (name, count) multiset."""
    counts: Counter[str] = Counter()
    for name, count in cards:
        if count > 0:
            counts[name] += count
    payload = "\n".join(f"{n}\t{c}" for n, c in sorted(counts.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── Resolution ──────────────────────────────────────────────────────────────


class NameIndex:
    """Metadata name index with uniqueness-guarded repair rules.

    Each rule resolves only when the key maps to exactly one metadata name;
    an ambiguous key is left unresolved and counted separately.
    """

    def __init__(self, names: Iterable[str], aliases: dict[str, str] | None = None) -> None:
        self.exact: set[str] = set()
        # Exact raw-name -> canonical-name repairs that are NOT metadata rows,
        # e.g. ygoprodeck passcode placeholders mapped through an in-repo
        # resolved twin of the same decks. Consulted before "exact".
        self.aliases: dict[str, str] = dict(aliases or {})
        self._loose: dict[str, str] = {}
        self._loose_ambiguous: set[str] = set()
        self._accent: dict[str, str] = {}
        self._accent_ambiguous: set[str] = set()
        self._punct: dict[str, str] = {}
        self._punct_ambiguous: set[str] = set()
        self._face: dict[str, str] = {}
        self._face_ambiguous: set[str] = set()
        for name in names:
            name = pipeline_key(name)
            if not name or name in self.exact:
                continue
            self.exact.add(name)

        for name in self.exact:
            self._add(self._loose, self._loose_ambiguous, loose_key(name), name)
            self._add(self._accent, self._accent_ambiguous, accent_key(name), name)
            self._add(self._punct, self._punct_ambiguous, punct_fold(name), name)
            faces = face_split(name)
            # "X // X" rows are the empty shells documented in the metadata
            # audit (no mana cost, text, power or image). They must not make a
            # genuine "X // Y" face look ambiguous.
            if len(faces) > 1 and len(set(faces)) > 1:
                for face in faces:
                    self._add(self._face, self._face_ambiguous, loose_key(face), name)

    @staticmethod
    def _add(table: dict[str, str], ambiguous: set[str], key: str, canonical: str) -> None:
        if not key or key in ambiguous:
            return
        if key in table and table[key] != canonical:
            del table[key]
            ambiguous.add(key)
            return
        table[key] = canonical

    def resolve(self, name: str) -> tuple[str | None, str]:
        """Return (canonical name | None, rule that fired)."""
        key = pipeline_key(name)
        if key in self.aliases:
            return self.aliases[key], "placeholder_join"
        if key in self.exact:
            return key, "exact"
        if loose_key(key) in self._loose:
            return self._loose[loose_key(key)], "casefold"
        if accent_key(key) in self._accent:
            return self._accent[accent_key(key)], "accent"
        # Typographic punctuation only: curly quotes, en/em dashes. Guarded by
        # uniqueness, so it cannot collapse genuinely distinct cards.
        if punct_fold(key) in self._punct:
            return self._punct[punct_fold(key)], "punct_variant"

        # "Quoted" yugioh rows: metadata stores Infernoble Arms - Durendal as
        # '"Infernoble Arms - Durendal"'. Only a quoting artifact is repaired.
        if not _is_quoted(key) and _is_quoted_pair(key):
            quoted = f'"{key}"'
            if quoted in self.exact:
                return quoted, "strip_quotes"

        # Slash separator: "Wear/Tear" -> "Wear // Tear".
        if "//" not in key and key.count("/") == 1:
            left, right = (part.strip() for part in key.split("/"))
            joined = f"{left} // {right}"
            if joined in self.exact:
                return joined, "slash_separator"

        # Yu-Gi-Oh angle-bracket set codes: "Maliss Q White Binder" ->
        # "Maliss <Q> White Binder". The bracketed token is exactly one or two
        # capital letters and the bare prefix must not already be a card.
        match = re.match(r"^(?P<prefix>\S.*?) (?P<code>[A-Z]{1,2}) (?P<rest>\S.*)$", key)
        if match:
            bracketed = f"{match['prefix']} <{match['code']}> {match['rest']}"
            if bracketed in self.exact and match["prefix"] not in self.exact:
                return bracketed, "ygo_angle"

        # Digimon ACE suffix: "Zephagamon ACE" -> "Zephagamon" (metadata has no
        # ACE rows). Only when the bare base exists and is unambiguous.
        if key.endswith(" ACE"):
            base = key[: -len(" ACE")].strip()
            if base in self.exact:
                return base, "ace_suffix"

        # Back/front face only: "Timbercrown Pathway" -> "Cragcrown Pathway //
        # Timbercrown Pathway". Last tier, because it rewrites identity.
        face_hit = self._face.get(loose_key(key))
        if face_hit is not None:
            return face_hit, "face_split"

        return None, "unresolved"


def _is_quoted(name: str) -> bool:
    return len(name) > 2 and name.startswith('"') and name.endswith('"')


def _is_quoted_pair(name: str) -> bool:
    return '"' not in name


def load_metadata_names(game: str) -> list[str]:
    """Read the name column of card_attributes_{game}_enriched.csv, streaming."""
    path = PROCESSED / f"card_attributes_{game}_enriched.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    names: list[str] = []
    with open(path, newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or "").strip()
            if name:
                names.append(name)
    return names


# ── Deck streaming ──────────────────────────────────────────────────────────


def iter_decks(paths: Iterable[Path]) -> Iterator[tuple[Path, int, dict[str, Any]]]:
    """Stream (path, 1-based line number, deck) tuples."""
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield path, line_no, json.loads(line)
                except json.JSONDecodeError:
                    continue


def rel(path: Path) -> str:
    """Path relative to the repository root, for reports."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def corpus_paths(filenames: Iterable[str]) -> list[Path]:
    return [DATA / "decks" / name for name in filenames]


# ── Stage: dedupe ───────────────────────────────────────────────────────────


def _timestamp(deck: dict[str, Any]) -> str | None:
    for field in ("created_at", "created", "scraped_at", "updated_at"):
        value = deck.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def dedupe_source(source: Path, output: Path) -> dict[str, Any]:
    """Write a deduplicated copy of one deck file, keeping the earliest record.

    "Earliest" is first occurrence in the stream, which is the only order this
    pass can guarantee while streaming. ``kept_not_earliest_by_timestamp``
    measures how often the stream order disagrees with ``created_at`` so the
    caveat is quantified rather than assumed away.
    """
    seen: dict[str, str | None] = {}
    records = 0
    kept = 0
    dropped_id = 0
    dropped_list = 0
    out_of_order = 0
    seen_ids: set[str] = set()
    with (
        open(source, encoding="utf-8", errors="replace") as handle,
        open(output, "w", encoding="utf-8") as out,
    ):
        for line in handle:
            if not line.strip():
                continue
            records += 1
            try:
                deck = json.loads(line)
            except json.JSONDecodeError:
                continue
            deck_id = str(deck.get("deck_id") or deck.get("id") or "")
            if deck_id and deck_id in seen_ids:
                dropped_id += 1
            else:
                if deck_id:
                    seen_ids.add(deck_id)
            signature = deck_signature(iter_deck_cards(deck))
            stamp = _timestamp(deck)
            if signature in seen:
                dropped_list += 1
                first = seen[signature]
                if first and stamp and stamp < first:
                    out_of_order += 1
                continue
            seen[signature] = stamp
            kept += 1
            out.write(json.dumps(deck, ensure_ascii=False) + "\n")
    return {
        "source": rel(source),
        "output": rel(output),
        "records_before": records,
        "records_after": kept,
        "dropped_duplicate_list": dropped_list,
        "duplicate_share": round(dropped_list / records, 4) if records else 0.0,
        "records_sharing_deck_id": dropped_id,
        "rows_removed": records - kept,
        "kept_not_earliest_by_timestamp": out_of_order,
    }


# ── Stage: pairs ────────────────────────────────────────────────────────────


def build_pairs(
    decks: Iterable[tuple[str, dict[str, Any]]],
    resolve: Any = None,
    drop_unresolved: bool = False,
) -> dict[str, Any]:
    """Accumulate COUNT_SET / COUNT_MULTISET over streamed (deck_id, deck) pairs."""
    set_counts: dict[int, int] = defaultdict(int)
    multi_counts: dict[int, int] = defaultdict(int)
    names: list[str] = []
    ids: dict[str, int] = {}
    unresolved: Counter[str] = Counter()
    resolved_rows = 0
    dropped_rows = 0
    decks_used = 0

    def name_id(name: str) -> int:
        idx = ids.get(name)
        if idx is None:
            idx = len(names)
            ids[name] = idx
            names.append(name)
        return idx

    for _deck_id, deck in decks:
        counts: dict[int, int] = defaultdict(int)
        for card_name, count in iter_deck_cards(deck):
            if count <= 0 or NUMERIC_ID_RE.match(card_name):
                continue
            if resolve is not None:
                canonical, _rule = resolve(card_name)
                if canonical is None:
                    unresolved[card_name] += 1
                    dropped_rows += count
                    if drop_unresolved:
                        continue
                    canonical = card_name
                else:
                    resolved_rows += 1
            else:
                canonical = card_name
            counts[name_id(canonical)] += count
        if not counts:
            continue
        decks_used += 1
        ordered = sorted(counts)
        for i, left in enumerate(ordered):
            left_count = counts[left]
            for right in ordered[i + 1 :]:
                key = (left << 32) | right
                set_counts[key] += 1
                multi_counts[key] += left_count * counts[right]

    return {
        "names": names,
        "set_counts": set_counts,
        "multi_counts": multi_counts,
        "decks_used": decks_used,
        "resolved_rows": resolved_rows,
        "dropped_rows": dropped_rows,
        "unresolved_unique": len(unresolved),
        "unresolved_rows": sum(unresolved.values()),
        "unresolved_top": unresolved.most_common(20),
    }


def write_pairs_csv(result: dict[str, Any], output: Path) -> int:
    names = result["names"]
    set_counts = result["set_counts"]
    multi_counts = result["multi_counts"]
    rows = 0
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["NAME_1", "NAME_2", "COUNT_SET", "COUNT_MULTISET"])
        for key in sorted(set_counts, key=lambda k: (names[k >> 32], names[k & 0xFFFFFFFF])):
            writer.writerow(
                [names[key >> 32], names[key & 0xFFFFFFFF], set_counts[key], multi_counts[key]]
            )
            rows += 1
    return rows


def weight_summary(values: Iterable[int]) -> dict[str, Any]:
    """Bounded distribution summary without materialising the whole corpus twice."""
    total = 0
    count = 0
    maximum = 0
    hist = Counter()
    for value in values:
        total += value
        count += 1
        maximum = max(maximum, value)
        if value == 1:
            hist["1"] += 1
        elif value <= 3:
            hist["2-3"] += 1
        elif value <= 10:
            hist["4-10"] += 1
        elif value <= 100:
            hist["11-100"] += 1
        else:
            hist["101+"] += 1
    return {
        "rows": count,
        "total_weight": total,
        "mean": round(total / count, 4) if count else 0.0,
        "max": maximum,
        "histogram": dict(hist),
    }


# ── CLI ─────────────────────────────────────────────────────────────────────


def _write_manifest_entry(out_dir: Path, path: Path, note: str) -> None:
    manifest_path = out_dir / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text()) if manifest_path.exists() else {"artifacts": []}
    )
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    manifest["artifacts"] = [a for a in manifest["artifacts"] if a["path"] != rel(path)]
    manifest["artifacts"].append(
        {
            "path": rel(path),
            "sha256": digest.hexdigest(),
            "bytes": path.stat().st_size,
            "note": note,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def cmd_dedupe(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = args.sources or [
        "decks_magic_archidekt_modern.jsonl",
        "decks_magic_moxfield_commander.jsonl",
        "decks_magic_archidekt_commander.jsonl",
    ]
    report = []
    for filename in sources:
        source = DATA / "decks" / filename
        output = out_dir / filename.replace(".jsonl", "_dedup.jsonl")
        stats = dedupe_source(source, output)
        _write_manifest_entry(out_dir, output, f"deduplicated copy of {filename}")
        report.append(stats)
        print(json.dumps(stats, indent=2))
    report_path = out_dir / "dedupe_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    _write_manifest_entry(out_dir, report_path, "per-source deduplication counts")
    return 0


def measure_resolution(files: list[Path], index: NameIndex) -> tuple[dict[str, Any], Counter[str]]:
    """Count card-name rows per resolution rule for a streamed set of deck files."""
    rule_rows: Counter[str] = Counter()
    rule_unique: dict[str, set[str]] = defaultdict(set)
    unresolved: Counter[str] = Counter()
    rows = 0
    for _path, _line, deck in iter_decks(files):
        for name, count in iter_deck_cards(deck):
            if count <= 0:
                continue
            rows += 1
            canonical, rule = index.resolve(name)
            if canonical is None:
                unresolved[name] += 1
            else:
                rule_rows[rule] += 1
                rule_unique[rule].add(name)
    summary = {
        "files": [rel(f) for f in files],
        "card_rows": rows,
        "resolved_rows": rows - sum(unresolved.values()),
        "by_rule_rows": dict(sorted(rule_rows.items(), key=lambda kv: -kv[1])),
        "by_rule_unique_names": {k: len(v) for k, v in sorted(rule_unique.items())},
        "unresolved_rows": sum(unresolved.values()),
        "unresolved_unique": len(unresolved),
        "unresolved_top": unresolved.most_common(25),
    }
    return summary, unresolved


def cmd_resolve(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    dump_path = out_dir / "unresolved_names.csv"
    with open(dump_path, "w", newline="", encoding="utf-8") as dump_handle:
        dump = csv.writer(dump_handle)
        dump.writerow(["game", "scope", "name", "card_rows"])
        for game, index in _game_indexes(args.game):
            dedup_files = sorted(out_dir.glob(f"decks_{game}_*_dedup.jsonl"))
            entry: dict[str, Any] = {}
            for scope, files in (
                ("deduplicated_corpora", dedup_files),
                ("training_corpus", corpus_paths(TRAINING_CORPORA.get(game, []))),
            ):
                if not files:
                    continue
                summary, unresolved = measure_resolution(files, index)
                entry[scope] = summary
                for name, count in sorted(unresolved.items(), key=lambda kv: -kv[1]):
                    dump.writerow([game, scope, name, count])
            report[game] = entry
            print(json.dumps(entry, indent=2)[:4000])
    path = out_dir / "resolve_report.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    _write_manifest_entry(out_dir, path, "per-rule resolution counts")
    _write_manifest_entry(out_dir, dump_path, "every unresolved card name and its row count")
    return 0


def _game_indexes(game: str, out_dir: Path | None = None) -> list[tuple[str, NameIndex]]:
    games = [game] if game != "all" else ["magic", "pokemon", "yugioh"]
    indexes: list[tuple[str, NameIndex]] = []
    for g in games:
        aliases = load_placeholder_map(out_dir, g) if out_dir else {}
        indexes.append((g, NameIndex(load_metadata_names(g), aliases)))
    return indexes


def load_placeholder_map(out_dir: Path, game: str) -> dict[str, str]:
    """Load an in-repo placeholder -> canonical name map, if one was built."""
    path = out_dir / f"placeholder_map_{game}.csv"
    if not path.exists():
        return {}
    aliases: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("placeholder") and row.get("canonical"):
                aliases[row["placeholder"]] = row["canonical"]
    return aliases


def build_placeholder_map(out_dir: Path, game: str) -> dict[str, Any] | None:
    """Derive placeholder -> canonical names from a resolved twin corpus.

    The ygoprodeck export writes passcodes as ``Card_<id>``; the repository also
    holds a resolved copy of the same decks with identical ``deck_id`` and card
    order. Joining positionally yields an exact, ambiguity-checked id -> name
    map without network access. A placeholder whose join is ambiguous or whose
    target is not in the metadata table is left out of the map.
    """
    resolved = DATA / "decks" / "decks_yugioh_resolved.jsonl"
    raw = DATA / "decks" / "decks_yugioh_ygoprodeck-tournament.jsonl"
    if game != "yugioh" or not (resolved.exists() and raw.exists()):
        return None

    def load(path: Path) -> dict[str, dict[str, Any]]:
        decks: dict[str, dict[str, Any]] = {}
        for _p, _line, deck in iter_decks([path]):
            decks[str(deck.get("deck_id") or deck.get("id") or "")] = deck
        return decks

    resolved_decks = load(resolved)
    candidates: Counter[str] = Counter()
    targets: dict[str, set[str]] = defaultdict(set)
    joined = 0
    for _p, _line, deck in iter_decks([raw]):
        twin = resolved_decks.get(str(deck.get("deck_id") or deck.get("id") or ""))
        if twin is None:
            continue
        cards = list(iter_deck_cards(deck))
        twin_cards = list(iter_deck_cards(twin))
        if len(cards) != len(twin_cards):
            continue
        joined += 1
        for (raw_name, _count), (canonical, _tcount) in zip(cards, twin_cards):
            if raw_name == canonical or not NUMERIC_ID_RE.match(raw_name):
                continue
            candidates[raw_name] += 1
            targets[raw_name].add(canonical)

    metadata = set(load_metadata_names(game))
    rows: list[tuple[str, str, int]] = []
    ambiguous: list[tuple[str, list[str], int]] = []
    missing: list[tuple[str, str, int]] = []
    for placeholder, count in sorted(candidates.items(), key=lambda kv: -kv[1]):
        options = sorted(targets[placeholder])
        if len(options) > 1:
            ambiguous.append((placeholder, options, count))
        elif options[0] not in metadata:
            missing.append((placeholder, options[0], count))
        else:
            rows.append((placeholder, options[0], count))

    map_path = out_dir / f"placeholder_map_{game}.csv"
    with open(map_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["placeholder", "canonical", "tournament_deck_rows"])
        writer.writerows(rows)
    _write_manifest_entry(
        out_dir, map_path, "placeholder -> canonical names derived from the resolved twin corpus"
    )
    summary = {
        "decks_joined": joined,
        "placeholders_seen": len(candidates),
        "mapped": len(rows),
        "mapped_rows": sum(r[2] for r in rows),
        "ambiguous": [{"placeholder": p, "options": o, "rows": c} for p, o, c in ambiguous],
        "target_missing_from_metadata": [
            {"placeholder": p, "target": t, "rows": c} for p, t, c in missing
        ],
    }
    report_path = out_dir / f"placeholder_map_{game}.json"
    report_path.write_text(json.dumps(summary, indent=2) + chr(10))
    _write_manifest_entry(out_dir, report_path, "placeholder map build summary")
    return summary


def cmd_pairs(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    game = args.game
    index = NameIndex(load_metadata_names(game))
    paths = corpus_paths(TRAINING_CORPORA[game])

    def all_decks() -> Iterator[tuple[str, dict[str, Any]]]:
        for _path, line_no, deck in iter_decks(paths):
            yield str(deck.get("deck_id") or f"line{line_no}"), deck

    def deduped_decks() -> Iterator[tuple[str, dict[str, Any]]]:
        seen: set[str] = set()
        for deck_id, deck in all_decks():
            signature = deck_signature(iter_deck_cards(deck))
            if signature in seen:
                continue
            seen.add(signature)
            yield deck_id, deck

    def summarise(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "decks_used": result["decks_used"],
            "rows": len(result["set_counts"]),
            "nodes": len(result["names"]),
            "count_set": weight_summary(result["set_counts"].values()),
            "count_multiset": weight_summary(result["multi_counts"].values()),
        }

    raw = build_pairs(all_decks())
    raw_summary = summarise(raw)
    del raw

    baseline = build_pairs(deduped_decks())
    baseline_summary = summarise(baseline)
    baseline_csv = out_dir / f"pairs_{game}_baseline.csv"
    write_pairs_csv(baseline, baseline_csv)
    del baseline

    rebuilt = build_pairs(deduped_decks(), resolve=index.resolve, drop_unresolved=True)
    rebuilt_summary = summarise(rebuilt)
    rebuilt_csv = out_dir / f"pairs_{game}_rebuilt.csv"
    write_pairs_csv(rebuilt, rebuilt_csv)

    report = {
        "game": game,
        "input_files": [rel(p) for p in paths],
        "undeduped_raw_names": raw_summary,
        "deduped_raw_names": baseline_summary,
        "deduped_resolved": rebuilt_summary,
        "unresolved": {
            "unique": rebuilt["unresolved_unique"],
            "card_rows": rebuilt["unresolved_rows"],
            "copies_dropped": rebuilt["dropped_rows"],
            "top": rebuilt["unresolved_top"],
        },
    }
    _write_manifest_entry(out_dir, baseline_csv, f"{game} pairs from deduplicated decks, raw names")
    _write_manifest_entry(out_dir, rebuilt_csv, f"{game} pairs from deduplicated + resolved decks")
    pairs_report = out_dir / f"pairs_{game}_report.json"
    pairs_report.write_text(json.dumps(report, indent=2) + "\n")
    _write_manifest_entry(out_dir, pairs_report, f"{game} pair-build summary")
    print(json.dumps(report, indent=2, default=str)[:6000])
    return 0


def load_test_tokens(game: str) -> dict[tuple[str, str], str]:
    """Map (a, b) test-pair tokens to the bucket they came from."""
    path = DATA / "test_sets" / f"annotated_{game}_v2.json"
    payload = json.loads(path.read_text())
    tokens: dict[tuple[str, str], str] = {}
    for query, buckets in payload["queries"].items():
        for bucket, candidates in buckets.items():
            if isinstance(candidates, dict):
                # "modes" maps candidate -> label; "annotations" is one record.
                candidates = (
                    candidates.keys() if bucket == "modes" else [candidates.get("candidate")]
                )
            if not isinstance(candidates, list):
                candidates = [candidates]
            for candidate in candidates:
                if not isinstance(candidate, str) or not candidate or not query:
                    continue
                key = tuple(sorted((query, candidate)))
                tokens.setdefault(key, bucket)  # type: ignore[arg-type]
    return tokens


def cmd_leakage(args: argparse.Namespace) -> int:
    """Measure how many annotated test pairs already exist as edges."""
    index = NameIndex(load_metadata_names(args.game))
    tokens = load_test_tokens(args.game)
    resolved_tokens = set()
    for a, b in tokens:
        ca, _ = index.resolve(a)
        cb, _ = index.resolve(b)
        if ca is not None and cb is not None:
            resolved_tokens.add(tuple(sorted((ca, cb))))

    hits = 0
    resolved_hits = 0
    rows = 0
    csv_path = Path(args.csv)
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            rows += 1
            if len(row) < 2:
                continue
            key = tuple(sorted((row[0], row[1])))
            if key in tokens:
                hits += 1
            if key in resolved_tokens:
                resolved_hits += 1
    report = {
        "csv": rel(csv_path),
        "game": args.game,
        "edge_rows": rows,
        "test_pair_tokens": len(tokens),
        "test_pair_tokens_resolved": len(resolved_tokens),
        "distinct_test_pairs_present_raw": hits,
        "distinct_test_pairs_present_resolved": resolved_hits,
        "share_of_test_tokens_raw": round(hits / len(tokens), 4) if tokens else 0.0,
        "share_of_test_tokens_resolved": round(resolved_hits / len(resolved_tokens), 4)
        if resolved_tokens
        else 0.0,
    }
    label = f"{csv_path.parent.name}_{csv_path.stem}"
    out = Path(args.out_dir) / f"leakage_{args.game}_{label}.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    _write_manifest_entry(Path(args.out_dir), out, "test-set edge overlap")
    print(json.dumps(report, indent=2))
    return 0


def cmd_audit_edges(args: argparse.Namespace) -> int:
    """Duplicates, self-edges and unresolved endpoints in an edge CSV."""
    index = NameIndex(load_metadata_names(args.game))
    seen: set[tuple[str, str]] = set()
    rows = 0
    self_edges = 0
    duplicates = 0
    unresolved_rows = 0
    unresolved_names: Counter[str] = Counter()
    csv_path = Path(args.csv)
    is_edg = csv_path.suffix == ".edg"
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as handle:
        # Names are read verbatim: the Go exporter writes raw names into .edg,
        # and csv.reader already unescapes CSV quoting. Stripping quote
        # characters here would corrupt cards whose real name has quotes.
        reader = (
            csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)
            if is_edg
            else csv.reader(handle)
        )
        if not is_edg:
            next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            rows += 1
            a, b = row[0], row[1]
            if a == b:
                self_edges += 1
            key = tuple(sorted((a, b)))
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)
            bad = False
            for name in key:
                if pipeline_key(name) not in index.exact:
                    canonical, _rule = index.resolve(name)
                    if canonical is None:
                        unresolved_names[name] += 1
                        bad = True
            if bad:
                unresolved_rows += 1
    defect = duplicates + unresolved_rows
    report = {
        "csv": rel(csv_path),
        "game": args.game,
        "rows": rows,
        "unique_unordered_pairs": len(seen),
        "duplicate_rows": duplicates,
        "self_edges": self_edges,
        "unresolved_rows": unresolved_rows,
        "unresolved_unique_names": len(unresolved_names),
        "unresolved_top": unresolved_names.most_common(10),
        "defect_rows": defect,
        "defect_fraction": round(defect / rows, 5) if rows else 0.0,
    }
    label = f"{csv_path.parent.name}_{csv_path.stem}"
    out = Path(args.out_dir) / f"edges_{args.game}_{label}.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    _write_manifest_entry(Path(args.out_dir), out, "edge-list defect measurement")
    print(json.dumps(report, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    dedupe = sub.add_parser("dedupe", help="deduplicate deck JSONL files")
    dedupe.add_argument("--out-dir", required=True)
    dedupe.add_argument("--sources", nargs="*", default=None)
    dedupe.set_defaults(func=cmd_dedupe)

    resolve = sub.add_parser("resolve", help="measure name resolution per rule")
    resolve.add_argument("--out-dir", required=True)
    resolve.add_argument("--game", default="all")
    resolve.set_defaults(func=cmd_resolve)

    pairs = sub.add_parser("pairs", help="rebuild a co-occurrence edge list")
    pairs.add_argument("--out-dir", required=True)
    pairs.add_argument("--game", required=True)
    pairs.set_defaults(func=cmd_pairs)

    leakage = sub.add_parser("leakage", help="test-set pair overlap with an edge CSV")
    leakage.add_argument("--csv", required=True)
    leakage.add_argument("--game", required=True)
    leakage.add_argument("--out-dir", required=True)
    leakage.set_defaults(func=cmd_leakage)

    audit = sub.add_parser("audit-edges", help="duplicate and unresolved edge rows")
    audit.add_argument("--csv", required=True)
    audit.add_argument("--game", required=True)
    audit.add_argument("--out-dir", required=True)
    audit.set_defaults(func=cmd_audit_edges)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
