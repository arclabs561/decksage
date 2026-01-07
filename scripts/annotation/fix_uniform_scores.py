#!/usr/bin/env python3
"""Fix annotations with uniform similarity scores.

Detects and flags annotations where all scores are identical (likely generation issue).
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def detect_uniform_scores(file_path: Path) -> dict:
    """Detect if annotations have uniform similarity scores."""
    annotations = []
    with open(file_path) as f:
        for line in f:
            line = line.strip()
            if line:
                annotations.append(json.loads(line))
    
    if not annotations:
        return {"error": "No annotations found"}
    
    scores = [a.get("similarity_score") for a in annotations if a.get("similarity_score") is not None]
    
    unique_scores = set(scores)
    is_uniform = len(unique_scores) == 1 and len(annotations) > 5
    
    return {
        "total": len(annotations),
        "unique_scores": len(unique_scores),
        "is_uniform": is_uniform,
        "score_value": list(unique_scores)[0] if is_uniform else None,
        "score_range": (min(scores), max(scores)) if scores else None,
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Detect uniform similarity scores")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input annotation file (JSONL)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to fix by flagging for regeneration (creates .needs_regeneration file)",
    )
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        return 1
    
    result = detect_uniform_scores(args.input)
    
    if "error" in result:
        print(f"Error: {result['error']}")
        return 1
    
    print(f"File: {args.input.name}")
    print(f"Total annotations: {result['total']}")
    print(f"Unique similarity scores: {result['unique_scores']}")
    print(f"Score range: {result['score_range']}")
    
    if result["is_uniform"]:
        print(f"\n⚠️  WARNING: All annotations have uniform similarity_score: {result['score_value']}")
        print("   This indicates a generation issue - LLM may not be generating diverse scores.")
        print("   Recommendation: Regenerate annotations with improved prompt/model.")
        
        if args.fix:
            flag_file = args.input.with_suffix(args.input.suffix + ".needs_regeneration")
            with open(flag_file, "w") as f:
                f.write(f"Uniform scores detected: {result['score_value']}\n")
                f.write(f"Total annotations: {result['total']}\n")
                f.write("Action: Regenerate with improved LLM prompt/model\n")
            print(f"\n✅ Flagged for regeneration: {flag_file}")
    else:
        print("\n✅ Score diversity is good")
    
    return 0 if not result["is_uniform"] else 1


if __name__ == "__main__":
    sys.exit(main())

