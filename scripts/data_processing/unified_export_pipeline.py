#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Unified export and enhancement pipeline for deck data.

Consolidates:
- export_and_unify_all_decks.py
- export_decks_metadata.py
- export_missing_decks.py
- enhance_exported_decks.py

Stages:
1. Export: Extract decks from raw .zst files
2. Enhance: Normalize, deduplicate, validate
3. Final: Backfill metadata, add timestamps
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
 sys.path.insert(0, str(src_dir))

from ml.utils.paths import PATHS


def export_decks_from_raw(
 game: str,
 source_name: str,
 canonical_dir: Path,
 output_file: Path,
) -> int:
 """Export decks from canonical storage using Go tool."""
 if not canonical_dir.exists():
 print(f"Warning: Data directory not found: {canonical_dir}")
 return 0

 if output_file.exists():
 count = sum(1 for _ in open(output_file))
 print(f"Warning: {output_file} exists with {count:,} decks, skipping...")
 return count

 # Build export-hetero if needed
 go_tool = Path("src/backend/cmd/export-hetero/main.go")
 if not go_tool.exists():
 print(f"Error: Export tool not found: {go_tool}")
 return 0

 print(f"Exporting {game}/{source_name} from {canonical_dir}...")

 # Build tool using utility
 try:
 from ml.utils.export_tools import build_export_tool
 binary_path = build_export_tool(
 "export-hetero",
 go_tool,
 )
 except Exception as e:
 print(f"Error: Failed to build: {e}")
 return 0

 # Run export
 output_file.parent.mkdir(parents=True, exist_ok=True)
 export_result = subprocess.run(
 [str(binary_path), str(canonical_dir), str(output_file)],
 capture_output=True,
 text=True,
 )

 if export_result.returncode != 0:
 print(f"Error: Export failed: {export_result.stderr}")
 return 0

 count = sum(1 for _ in open(output_file)) if output_file.exists() else 0
 print(f"✓ Exported {count:,} decks")
 return count


def enhance_decks(input_file: Path, output_file: Path) -> dict[str, Any]:
 """Enhance decks with normalization and deduplication."""
 from scripts.enhance_exported_decks import enhance_decks as enhance_func

 print(f"Enhancing decks from {input_file}...")
 stats = enhance_func(input_file, output_file, deduplicate=True, filter_invalid=True)
 print(f"✓ Enhanced: {stats['final_count']:,} decks")
 return stats


def run_pipeline(
 skip_export: bool = False,
 skip_enhance: bool = False,
 output_dir: Path | None = None,
 unified_file: Path | None = None,
) -> int:
 """Run unified export and enhancement pipeline."""
 if output_dir is None:
 output_dir = Path("data/decks")
 if unified_file is None:
 unified_file = PATHS.processed / "decks_all_final.jsonl"

 output_dir.mkdir(parents=True, exist_ok=True)
 unified_file.parent.mkdir(parents=True, exist_ok=True)

 print("=" * 70)
 print("Unified Export & Enhancement Pipeline")
 print("=" * 70)
 print()

 # Define canonical data sources
 canonical_base = Path("src/backend/data-full/games")

 deck_sources = {
 "magic": [
 ("mtgtop8", canonical_base / "magic/mtgtop8/collections"),
 ("goldfish", canonical_base / "magic/goldfish"),
 ("deckbox", canonical_base / "magic/deckbox"),
 ],
 "pokemon": [
 ("limitless", canonical_base / "pokemon/limitless-web"),
 ],
 "yugioh": [
 ("ygoprodeck", canonical_base / "yugioh/ygoprodeck-tournament"),
 ],
 "digimon": [
 ("limitless-web", canonical_base / "digimon/digimon-limitless-web"),
 ],
 "onepiece": [
 ("limitless-web", canonical_base / "onepiece/onepiece-limitless-web"),
 ],
 "riftbound": [
 ("riftcodex", canonical_base / "riftbound/riftcodex"),
 ("riftboundgg", canonical_base / "riftbound/riftboundgg"),
 ("riftmana", canonical_base / "riftbound/riftmana"),
 ],
 }

 # Stage 1: Export
 game_files: dict[str, list[Path]] = {}
 total_exported = 0

 if not skip_export:
 print("Stage 1: Exporting decks from canonical storage")
 print("-" * 70)

 for game, sources in deck_sources.items():
 game_files[game] = []

 for source_name, canonical_dir in sources:
 output_file = output_dir / f"{game}_{source_name}_decks.jsonl"
 count = export_decks_from_raw(game, source_name, canonical_dir, output_file)
 if count > 0:
 game_files[game].append(output_file)
 total_exported += count

 print(f"\n✓ Exported {total_exported:,} decks total")
 print()
 else:
 # Load existing files
 for game in deck_sources.keys():
 game_files[game] = []
 for pattern in [f"{game}_*_decks.jsonl"]:
 for file_path in output_dir.glob(pattern):
 if file_path not in game_files[game]:
 game_files[game].append(file_path)

 # Stage 2: Unify
 print("Stage 2: Unifying all decks")
 print("-" * 70)

 unified_count = 0
 temp_unified = unified_file.parent / f"{unified_file.stem}_temp.jsonl"

 with open(temp_unified, "w") as out:
 for game, files in game_files.items():
 for file_path in files:
 if not file_path.exists():
 continue

 count = 0
 with open(file_path) as f:
 for line in f:
 if line.strip():
 deck = json.loads(line)
 # Add game field if missing
 if "game" not in deck:
 deck["game"] = game
 json.dump(deck, out)
 out.write("\n")
 count += 1

 print(f" {game}/{file_path.name}: {count:,} decks")
 unified_count += count

 print(f"\n✓ Unified {unified_count:,} decks")
 print()

 # Stage 3: Enhance
 if not skip_enhance:
 print("Stage 3: Enhancing decks")
 print("-" * 70)

 stats = enhance_decks(temp_unified, unified_file)

 # Clean up temp file
 temp_unified.unlink()

 print()
 print("=" * 70)
 print("Pipeline Complete")
 print("=" * 70)
 print(f"Final output: {unified_file}")
 print(f"Final count: {stats['final_count']:,} decks")
 print(f" - Duplicates removed: {stats['duplicates_removed']:,}")
 print(f" - Invalid removed: {stats['invalid_removed']:,}")
 print(f" - Source backfilled: {stats['source_backfilled']:,}")
 else:
 # Just rename temp to final
 temp_unified.rename(unified_file)
 print(f"✓ Saved {unified_count:,} decks to {unified_file}")

 return 0


def main() -> int:
 """Main entry point."""
 parser = argparse.ArgumentParser(
 description="Unified export and enhancement pipeline"
 )
 parser.add_argument(
 "--skip-export",
 action="store_true",
 help="Skip export, use existing files",
 )
 parser.add_argument(
 "--skip-enhance",
 action="store_true",
 help="Skip enhancement, just unify",
 )
 parser.add_argument(
 "--output-dir",
 type=Path,
 default=Path("data/decks"),
 help="Output directory for per-game files",
 )
 parser.add_argument(
 "--unified-file",
 type=Path,
 help="Unified output file (default: data/processed/decks_all_final.jsonl)",
 )

 args = parser.parse_args()

 return run_pipeline(
 skip_export=args.skip_export,
 skip_enhance=args.skip_enhance,
 output_dir=args.output_dir,
 unified_file=args.unified_file,
 )


if __name__ == "__main__":
 sys.exit(main())
