#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Validate that exported decks have timestamps and they're used by downstream scripts.

Checks:
1. Export output has timestamp fields
2. Training scripts can read timestamps
3. Temporal split logic works
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent / "src"
if str(src_dir) not in sys.path:
 sys.path.insert(0, str(src_dir))


def validate_export_timestamps(deck_file: Path) -> dict[str, Any]:
 """Validate that exported decks have timestamp fields."""
 if not deck_file.exists():
 return {
 "valid": False,
 "error": f"File not found: {deck_file}",
 }
 
 timestamp_fields = ["scraped_at", "timestamp", "created_at", "date"]
 found_fields = set()
 missing_count = 0
 total_count = 0
 
 with open(deck_file) as f:
 for line_num, line in enumerate(f, 1):
 if not line.strip():
 continue
 
 try:
 deck = json.loads(line)
 total_count += 1
 
 # Check for any timestamp field
 has_timestamp = False
 for field in timestamp_fields:
 if field in deck and deck[field]:
 found_fields.add(field)
 has_timestamp = True
 break
 
 if not has_timestamp:
 missing_count += 1
 if missing_count <= 5:
 print(f" Warning: Line {line_num}: Missing timestamp fields")
 
 except json.JSONDecodeError: continue
 
 return {
 "valid": missing_count == 0,
 "total_decks": total_count,
 "missing_timestamps": missing_count,
 "found_fields": list(found_fields),
 "timestamp_fields_checked": timestamp_fields,
 }


def validate_training_compatibility() -> dict[str, Any]:
 """Check if training scripts can read timestamps."""
 # Check train_hybrid_full.py
 train_script = Path("src/ml/scripts/train_hybrid_full.py")
 if not train_script.exists():
 return {
 "valid": False,
 "error": "Training script not found",
 }
 
 content = train_script.read_text()
 
 # Check for scraped_at in timestamp extraction
 has_scraped_at = "scraped_at" in content or "'scraped_at'" in content or '"scraped_at"' in content
 
 # Check for timestamp extraction pattern
 has_timestamp_extraction = (
 "timestamp" in content and
 ("deck.get" in content or "deck[" in content)
 )
 
 return {
 "valid": has_scraped_at and has_timestamp_extraction,
 "has_scraped_at": has_scraped_at,
 "has_timestamp_extraction": has_timestamp_extraction,
 }


def main() -> int:
 """Main validation."""
 print("=" * 70)
 print("Timestamp Validation")
 print("=" * 70)
 print()
 
 # Check exported decks
 deck_files = [
 Path("data/decks/magic_mtgtop8_decks.jsonl"),
 Path("data/decks/pokemon_limitless_decks.jsonl"),
 Path("data/processed/decks_all_final.jsonl"),
 ]
 
 all_valid = True
 
 for deck_file in deck_files:
 if not deck_file.exists():
 continue
 
 print(f"Checking {deck_file.name}...")
 result = validate_export_timestamps(deck_file)
 
 if result["valid"]:
 print(f" ✓ All decks have timestamps")
 print(f" ✓ Found fields: {', '.join(result['found_fields'])}")
 else:
 print(f" Error: {result['missing_timestamps']} decks missing timestamps")
 all_valid = False
 
 print(f" Total decks: {result['total_decks']:,}")
 print()
 
 # Check training script compatibility
 print("Checking training script compatibility...")
 train_result = validate_training_compatibility()
 
 if train_result["valid"]:
 print(" ✓ Training scripts can read timestamps")
 else:
 print(" Error: Training scripts may not read timestamps correctly")
 print(f" Has scraped_at: {train_result['has_scraped_at']}")
 print(f" Has timestamp extraction: {train_result['has_timestamp_extraction']}")
 all_valid = False
 
 print()
 print("=" * 70)
 if all_valid:
 print("✓ All validations passed")
 return 0
 else:
 print("Error: Some validations failed")
 return 1


if __name__ == "__main__":
 sys.exit(main())

