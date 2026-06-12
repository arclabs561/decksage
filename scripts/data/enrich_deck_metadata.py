# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Enrich deck JSONL files with consistent format and archetype metadata.

Reads each JSONL file in --input-dir, extracts/normalizes format and archetype
fields from URLs, deck_ids, and existing metadata, then writes enriched copies
to --output-dir. Prints distribution stats to stdout.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Format normalization
# ---------------------------------------------------------------------------

FORMAT_CANONICAL = {
    "standard": "Standard",
    "modern": "Modern",
    "pioneer": "Pioneer",
    "legacy": "Legacy",
    "vintage": "Vintage",
    "pauper": "Pauper",
    "commander": "Commander",
    "edh": "Commander",
    "historic": "Historic",
    "alchemy": "Alchemy",
    "explorer": "Explorer",
    "brawl": "Brawl",
    "master duel": "Master Duel",
    "tcg": "TCG",
    "ocg": "OCG",
    "glc": "GLC",
    "expanded": "Expanded",
    "ex": "EX",
    "ex2": "EX2",
    "sumlot": "SumLot",
    "custom": "Custom",
}


def normalize_format(raw: str) -> str:
    if not raw:
        return ""
    key = raw.strip().lower()
    return FORMAT_CANONICAL.get(key, raw.strip())


# ---------------------------------------------------------------------------
# Archetype cleaning
# ---------------------------------------------------------------------------

# Single-letter color codes or "Imported Deck" are not useful archetypes.
_COLOR_ONLY = re.compile(r"^[WUBRGC]{1,5}$")
_BAD_ARCHETYPE_PREFIX = "?="


def is_bad_archetype(arch: str) -> bool:
    if not arch:
        return True
    if arch.startswith("Imported Deck"):
        return True
    if arch.startswith(_BAD_ARCHETYPE_PREFIX):
        return True
    if _COLOR_ONLY.match(arch):
        return True
    return False


def slug_to_title(slug: str) -> str:
    """Convert a URL slug like 'mono-red-aggro' to 'Mono Red Aggro'."""
    return " ".join(w.capitalize() for w in slug.split("-"))


# ---------------------------------------------------------------------------
# Per-source enrichment
# ---------------------------------------------------------------------------


def enrich_magic_goldfish(deck: dict) -> dict:
    """Magic Goldfish decks already have format + archetype, but some archetypes
    are garbage (color-only, 'Imported Deck', '?=...' paths). Clean those."""
    deck["format"] = normalize_format(deck.get("format", ""))
    arch = deck.get("archetype", "")
    if is_bad_archetype(arch):
        deck["archetype"] = ""
    return deck


def enrich_magic_commander(deck: dict) -> dict:
    """Commander decks from Archidekt. Format is always Commander, archetype
    is the commander name (already populated)."""
    deck["format"] = "Commander"
    # Archetype is commander name -- keep as-is if present.
    return deck


def enrich_pokemon_limitless(deck: dict) -> dict:
    """Limitless API decks -- format + archetype already present, normalize format."""
    deck["format"] = normalize_format(deck.get("format", ""))
    return deck


def enrich_pokemon_limitless_web(deck: dict) -> dict:
    """Limitless web-scraped decks -- format/archetype empty.
    These are all from the Standard-legal tournament site. Default to Standard."""
    if not deck.get("format"):
        deck["format"] = "Standard"
    else:
        deck["format"] = normalize_format(deck["format"])
    # Archetype is not recoverable from URL alone; leave empty.
    return deck


def enrich_pokemon_base(deck: dict) -> dict:
    """decks_pokemon.jsonl -- format + archetype already populated."""
    deck["format"] = normalize_format(deck.get("format", ""))
    return deck


def enrich_yugioh_masterduelmeta(deck: dict) -> dict:
    """Master Duel Meta decks -- format + archetype populated.
    URL pattern: /top-decks/<rank>/<month-year>/<archetype>/<player>/
    Can extract format from the 'rank' segment if needed."""
    deck["format"] = normalize_format(deck.get("format", "Master Duel"))
    # Archetype already populated from scrape.
    return deck


def enrich_yugioh_ygoprodeck(deck: dict) -> dict:
    """YGOProDeck tournament decks -- format/archetype empty.
    deck_id has pattern '<archetype-slug>-<numeric-id>'.
    URL: https://ygoprodeck.com/deck/<slug>-<id>
    Format is TCG by default (ygoprodeck is TCG-focused)."""
    if not deck.get("format"):
        deck["format"] = "TCG"
    else:
        deck["format"] = normalize_format(deck["format"])

    if not deck.get("archetype"):
        did = deck.get("deck_id", "")
        # Strip trailing numeric ID
        parts = did.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            deck["archetype"] = slug_to_title(parts[0])

    return deck


def enrich_riftbound(deck: dict) -> dict:
    """Riftbound decks -- minimal data, skip."""
    return deck


# Map source -> enrichment function
SOURCE_ENRICHERS = {
    "goldfish": enrich_magic_goldfish,
    "archidekt": enrich_magic_commander,
    "limitless": enrich_pokemon_limitless,
    "limitless-web": enrich_pokemon_limitless_web,
    "masterduelmeta": enrich_yugioh_masterduelmeta,
    "ygoprodeck-tournament": enrich_yugioh_ygoprodeck,
    "riftmana": enrich_riftbound,
    "riftcodex": enrich_riftbound,
}

# Filename -> game mapping
GAME_MAP = {
    "magic": "magic",
    "pokemon": "pokemon",
    "yugioh": "yugioh",
    "riftbound": "riftbound",
}


def detect_game(filename: str) -> str:
    for key, game in GAME_MAP.items():
        if key in filename:
            return game
    return "unknown"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def process_file(inpath: Path, outpath: Path) -> dict:
    """Process one JSONL file. Returns stats dict."""
    stats = {
        "total": 0,
        "format_filled": 0,
        "archetype_filled": 0,
        "format_added": 0,
        "archetype_added": 0,
        "formats": Counter(),
        "archetypes": Counter(),
    }

    lines = inpath.read_text().splitlines()
    if not lines:
        return stats

    out_lines = []
    for line in lines:
        if not line.strip():
            continue
        deck = json.loads(line)
        stats["total"] += 1

        old_fmt = deck.get("format", "")
        old_arch = deck.get("archetype", "")

        source = deck.get("source", "")
        enricher = SOURCE_ENRICHERS.get(source)
        if enricher:
            deck = enricher(deck)
        else:
            # Generic: just normalize format
            deck["format"] = normalize_format(deck.get("format", ""))

        new_fmt = deck.get("format", "")
        new_arch = deck.get("archetype", "")

        if new_fmt:
            stats["format_filled"] += 1
            stats["formats"][new_fmt] += 1
        if new_arch:
            stats["archetype_filled"] += 1
            stats["archetypes"][new_arch] += 1

        if new_fmt and not old_fmt:
            stats["format_added"] += 1
        if new_arch and (not old_arch or is_bad_archetype(old_arch)) and new_arch != old_arch:
            stats["archetype_added"] += 1

        out_lines.append(json.dumps(deck, ensure_ascii=False))

    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text("\n".join(out_lines) + "\n" if out_lines else "")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Enrich deck metadata.")
    parser.add_argument("--input-dir", required=True, help="Directory with deck JSONL files")
    parser.add_argument("--output-dir", required=True, help="Output directory for enriched files")
    args = parser.parse_args()

    indir = Path(args.input_dir)
    outdir = Path(args.output_dir)

    if not indir.is_dir():
        print(f"Error: {indir} is not a directory", file=sys.stderr)
        sys.exit(1)

    all_stats = {}
    for f in sorted(indir.glob("*.jsonl")):
        outpath = outdir / f.name
        stats = process_file(f, outpath)
        if stats["total"] > 0:
            all_stats[f.name] = stats

    # Print report
    print("=" * 72)
    print("DECK METADATA ENRICHMENT REPORT")
    print("=" * 72)

    grand_total = 0
    grand_fmt = 0
    grand_arch = 0
    grand_fmt_added = 0
    grand_arch_added = 0

    for fname, stats in all_stats.items():
        game = detect_game(fname)
        print(f"\n--- {fname} [{game}] ---")
        print(f"  Total decks: {stats['total']}")
        print(
            f"  Format filled: {stats['format_filled']}/{stats['total']}"
            f"  (added: {stats['format_added']})"
        )
        print(
            f"  Archetype filled: {stats['archetype_filled']}/{stats['total']}"
            f"  (added/fixed: {stats['archetype_added']})"
        )

        if stats["formats"]:
            print("  Formats:")
            for fmt, cnt in stats["formats"].most_common(10):
                print(f"    {cnt:6d}  {fmt}")

        if stats["archetypes"]:
            top = stats["archetypes"].most_common(8)
            print(f"  Top archetypes ({len(stats['archetypes'])} unique):")
            for arch, cnt in top:
                print(f"    {cnt:6d}  {arch}")

        grand_total += stats["total"]
        grand_fmt += stats["format_filled"]
        grand_arch += stats["archetype_filled"]
        grand_fmt_added += stats["format_added"]
        grand_arch_added += stats["archetype_added"]

    print(f"\n{'=' * 72}")
    print(f"GRAND TOTAL: {grand_total} decks")
    print(f"  Formats filled:    {grand_fmt}/{grand_total} ({grand_fmt_added} newly added)")
    print(f"  Archetypes filled: {grand_arch}/{grand_total} ({grand_arch_added} newly added/fixed)")
    print("=" * 72)


if __name__ == "__main__":
    main()
