#!/usr/bin/env python3
"""Materialize a multi-relation card graph (cooccurrence, text, tag, attribute).

The serving graph was co-occurrence only. This writes SQLite edges with a
relation column so an agent can ask for all evidence about a card, and so the
union retriever has a persisted edge store instead of recomputing lists.

Usage:
    scripts/graph/build_unified_graph.py --game magic
    scripts/graph/build_unified_graph.py --game pokemon --out /tmp/p.db
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ml.utils.paths import PATHS


BASIC_LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}


def _cache(game: str) -> Path:
    return PATHS.data / "cache" / f"text_emb_cache_cards_{game}_intfloat-e5-base-v2"


GAMES: dict[str, dict[str, object]] = {
    "magic": {
        "cache": "text_emb_cache_cards_magic_intfloat-e5-base-v2",
        "attributes": "card_attributes_magic_enriched.csv",
        "attribute_fields": ("creature_types",),
        "tags": "magic_tags.json",
    },
    "pokemon": {
        "cache": "text_emb_cache_cards_pokemon_intfloat-e5-base-v2",
        "attributes": "card_attributes_pokemon_enriched.csv",
        "attribute_fields": ("subtypes", "keywords"),
        "tags": "pokemon_tags.json",
    },
    "yugioh": {
        "cache": "text_emb_cache_cards_yugioh_intfloat-e5-base-v2",
        "attributes": "card_attributes_yugioh_enriched.csv",
        "attribute_fields": ("creature_types",),
        "tags": "yugioh_tags.json",
    },
}


def tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t]


def weighted_jaccard(left: set[str], right: set[str], weights: dict[str, float]) -> float:
    """Jaccard with rare labels weighted up, so "Supporter" is not a clique."""
    shared = left & right
    if not shared:
        return 0.0
    union = left | right
    numerator = sum(weights.get(item, 1.0) for item in shared)
    denominator = sum(weights.get(item, 1.0) for item in union)
    return numerator / denominator if denominator else 0.0


def cooccurrence_source(game: str) -> Path | None:
    graphs = PATHS.graphs
    preferred = graphs / f"{game}_merged_all.edg"
    if preferred.exists():
        return preferred
    candidates = sorted(graphs.glob(f"pairs_enriched_{game}_*.edg"))
    return candidates[0] if candidates else None


def read_edges(path: Path) -> dict[str, list[tuple[str, float]]]:
    """Read a TSV pair file, tolerating quoted fields from upstream scrapes."""
    raw: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) < 3:
                continue
            left, right = row[0].strip(), row[1].strip()
            if not left or not right or left == right:
                continue
            try:
                weight = float(row[2])
            except ValueError:
                continue
            raw[left].append((right, weight))
            raw[right].append((left, weight))
    return raw


def build(
    game: str,
    out: Path,
    top_k: int,
    max_cards: int,
    include_cooccurrence: bool = True,
    include_text: bool = True,
    attribute_fields: list[str] | None = None,
    filter_lands: bool = True,
) -> int:
    config = GAMES[game]
    cache = PATHS.data / "cache" / str(config["cache"])
    names_path = Path(f"{cache}.names.json")
    if not names_path.exists():
        raise SystemExit(f"missing text cache names: {names_path}")
    all_names = json.loads(names_path.read_text())
    index = {name: i for i, name in enumerate(all_names)}
    names = all_names[:max_cards] if max_cards else all_names

    edges: dict[tuple[str, str, str], float] = {}
    keep = set(names)

    def add(src: str, dst: str, relation: str, weight: float) -> None:
        if src == dst or dst not in keep or src not in keep:
            return
        if filter_lands and game == "magic" and (src in BASIC_LANDS or dst in BASIC_LANDS):
            return
        key = (src, dst, relation)
        if weight > edges.get(key, 0.0):
            edges[key] = float(weight)

    if include_cooccurrence:
        source = cooccurrence_source(game)
        if source is None:
            print(f"no co-occurrence source for {game}; skipping", flush=True)
        else:
            raw = read_edges(source)
            for card, neighbours in raw.items():
                if card not in index:
                    continue
                ceiling = max(weight for _, weight in neighbours) or 1.0
                for other, weight in sorted(neighbours, key=lambda pair: -pair[1])[:top_k]:
                    add(card, other, "cooccurrence", weight / ceiling)
            print(f"cooccurrence from {source.name} for {len(raw)} cards", flush=True)

    if include_text:
        matrix = np.load(f"{cache}.npz")["matrix"].astype(np.float32)
        matrix = matrix / np.maximum(np.linalg.norm(matrix, axis=1)[:, None], 1e-9)
        for start in range(0, len(names), 256):
            chunk = names[start : start + 256]
            rows = [index[name] for name in chunk]
            scores = matrix[rows] @ matrix.T
            for row, name in enumerate(chunk):
                kept = 0
                for position in np.argsort(scores[row])[::-1]:
                    other = all_names[int(position)]
                    if other == name:
                        continue
                    add(name, other, "text", float(scores[row, int(position)]))
                    kept += 1
                    if kept >= top_k:
                        break
            print(f"text {min(start + 256, len(names))}/{len(names)}", flush=True)

    tags_name = config.get("tags")
    if tags_name:
        tags_path = PATHS.processed / str(tags_name)
        if tags_path.exists():
            tag_map = json.loads(tags_path.read_text())
            keep = set(names)
            tag_sets = {name: set(tags) for name, tags in tag_map.items() if name in keep}
            inverted: dict[str, set[str]] = defaultdict(set)
            for name, tag_values in tag_sets.items():
                for label in tag_values:
                    inverted[label].add(name)
            weights = {
                label: 1.0 / math.log(1.0 + len(cards))
                for label, cards in inverted.items()
                if len(cards) > 1
            }
            for name, tag_values in tag_sets.items():
                candidates: set[str] = set()
                for label in tag_values:
                    candidates |= inverted[label]
                scored = []
                for other in candidates:
                    if other == name:
                        continue
                    score = weighted_jaccard(tag_values, tag_sets[other], weights)
                    if score:
                        scored.append((score, other))
                for score, other in sorted(scored, reverse=True)[:top_k]:
                    add(name, other, "tag", score)
            print(f"tag neighbours for {len(tag_sets)} cards", flush=True)
        else:
            print(f"no tag artifact for {game} ({tags_name}); skipping", flush=True)

    fields = attribute_fields or list(config["attribute_fields"])  # type: ignore[arg-type]
    attributes_path = PATHS.processed / str(config["attributes"])
    if fields and attributes_path.exists():
        with attributes_path.open(newline="", encoding="utf-8", errors="replace") as handle:
            rows = list(csv.DictReader(handle))
        kind_map: dict[str, set[str]] = {}
        kind_index: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            name = row.get("name", "")
            if name not in keep:
                continue
            kinds: set[str] = set()
            for field in attribute_fields or [str(f) for f in config["attribute_fields"]]:
                kinds |= set(tokens(row.get(field, "")))
            if kinds:
                kind_map[name] = kinds
                for kind in kinds:
                    kind_index[kind].add(name)
        weights = {
            kind: 1.0 / math.log(1.0 + len(cards))
            for kind, cards in kind_index.items()
            if len(cards) > 1
        }
        for name, kinds in kind_map.items():
            candidates: set[str] = set()
            for kind in kinds:
                candidates |= kind_index[kind]
            scored = []
            for other in candidates:
                if other == name:
                    continue
                score = weighted_jaccard(kinds, kind_map.get(other, set()), weights)
                if score:
                    scored.append((score, other))
            for score, other in sorted(scored, reverse=True)[:top_k]:
                add(name, other, "attribute", score)
        print(f"attribute neighbours for {len(kind_map)} cards", flush=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    connection = sqlite3.connect(out)
    connection.execute(
        "CREATE TABLE edges (src TEXT, dst TEXT, relation TEXT, weight REAL, "
        "PRIMARY KEY (src, dst, relation))"
    )
    connection.executemany(
        "INSERT OR REPLACE INTO edges VALUES (?, ?, ?, ?)",
        [(src, dst, relation, weight) for (src, dst, relation), weight in edges.items()],
    )
    connection.execute("CREATE INDEX idx_edges_src ON edges(src, relation, weight DESC)")
    connection.commit()
    write_meta(connection)
    counts = connection.execute("SELECT relation, COUNT(*) FROM edges GROUP BY relation").fetchall()
    connection.close()
    print(f"wrote {out}: {len(edges)} edges {dict(counts)}")
    return 0


def write_meta(connection: sqlite3.Connection) -> None:
    """Store relation counts so serving does not scan 2M edges per request."""
    rows = connection.execute(
        "SELECT relation, COUNT(*), AVG(weight), MAX(weight) FROM edges GROUP BY relation"
    ).fetchall()
    nodes = connection.execute("SELECT COUNT(DISTINCT src) FROM edges").fetchone()[0]
    payload = {
        "nodes": nodes,
        "relations": {
            relation: {
                "edges": count,
                "mean_weight": round(float(mean), 4),
                "max_weight": round(float(maximum), 4),
            }
            for relation, count, mean, maximum in rows
        },
    }
    connection.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    connection.execute("INSERT OR REPLACE INTO meta VALUES ('stats', ?)", (json.dumps(payload),))
    connection.commit()


def annotate_existing(out: Path) -> int:
    """Add the meta table to a graph built before it existed."""
    if not out.exists():
        raise SystemExit(f"missing graph: {out}")
    connection = sqlite3.connect(out)
    write_meta(connection)
    connection.close()
    print(f"annotated {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", default="magic", choices=sorted(GAMES))
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--max-cards", type=int, default=0, help="Smoke test limit")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--skip-cooccurrence", action="store_true")
    parser.add_argument("--skip-text", action="store_true")
    parser.add_argument(
        "--only-meta",
        action="store_true",
        help="Write the stats table into an existing graph and exit",
    )
    parser.add_argument(
        "--keep-lands",
        action="store_true",
        help="Include basic lands in Magic edges (they dominate co-occurrence)",
    )
    parser.add_argument(
        "--attribute-fields",
        default=None,
        help="Comma-separated CSV columns to build the attribute relation from",
    )
    args = parser.parse_args()
    out = args.out or (PATHS.graphs / f"unified_{args.game}.db")
    if args.only_meta:
        return annotate_existing(out)
    fields = (
        [field.strip() for field in args.attribute_fields.split(",") if field.strip()]
        if args.attribute_fields
        else None
    )
    return build(
        game=args.game,
        out=out,
        top_k=args.top_k,
        max_cards=args.max_cards,
        include_cooccurrence=not args.skip_cooccurrence,
        include_text=not args.skip_text,
        attribute_fields=fields,
        filter_lands=not args.keep_lands,
    )


if __name__ == "__main__":
    sys.exit(main())
