#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
# ]
# ///
"""
Add missing enhanced field columns to enrichment CSV.

The CSV was created before enhanced fields were added to the script.
This adds the columns so they can be populated.
"""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    import pandas as pd
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

def add_enhanced_columns(input_csv: Path, output_csv: Path) -> None:
    """Add enhanced field columns to CSV."""
    df = pd.read_csv(input_csv)
    
    # Enhanced fields to add
    enhanced_fields = {
        'power': '',
        'toughness': '',
        'set': '',
        'set_name': '',
        'oracle_text': '',
        'keywords': '',
    }
    
    # Add missing columns
    added = []
    for field, default_value in enhanced_fields.items():
        if field not in df.columns:
            df[field] = default_value
            added.append(field)
    
    if added:
        print(f"Added columns: {', '.join(added)}")
        df.to_csv(output_csv, index=False)
        print(f"✅ Updated CSV saved to {output_csv}")
    else:
        print("✅ All enhanced field columns already exist")
        if input_csv != output_csv:
            df.to_csv(output_csv, index=False)

def main() -> int:
    parser = argparse.ArgumentParser(description="Add enhanced field columns to CSV")
    parser.add_argument("--input", type=str, required=True, help="Input CSV")
    parser.add_argument("--output", type=str, help="Output CSV (default: same as input)")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("Missing dependencies: pandas")
        return 1
    
    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path
    
    add_enhanced_columns(input_path, output_path)
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())

