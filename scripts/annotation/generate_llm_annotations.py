#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-ai>=0.0.12",
# ]
# ///
"""
Generate LLM annotations for card similarity using REAL LLM calls.

Uses llm_annotator.py infrastructure for real similarity judgments.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Load .env if it exists
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except Exception:
    pass

# Add src to path
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from ml.annotation.llm_annotator import LLMAnnotator
    from ml.utils.paths import PATHS

    HAS_LLM_ANNOTATOR = True
except ImportError as e:
    HAS_LLM_ANNOTATOR = False
    print(f"Warning: Could not import LLMAnnotator: {e}")
    print("This script requires pydantic-ai and proper setup")


async def generate_annotations_for_game(
    game: str,
    output_file: Path,
    num_annotations: int = 50,
    strategy: str = "diverse",
    batch_size: int = 10,
) -> int:
    """Generate REAL LLM annotations for a game."""
    if not HAS_LLM_ANNOTATOR:
        print(f"Error: LLM annotator not available. Install dependencies.")
        return 0

    print(f"Generating REAL LLM annotations for {game}...")
    print(f"  Strategy: {strategy}")
    print(f"  Target: {num_annotations} annotations")

    # Check for API key before starting
    if not os.getenv("OPENROUTER_API_KEY"):
        print(f"❌ Error: OPENROUTER_API_KEY not set")
        print("   Set in .env file or: export OPENROUTER_API_KEY=your-key")
        return 0

    start_time = time.time()

    try:
        # Use the real LLM annotator with game filtering
        print(f"  Initializing LLM annotator...")
        annotator = LLMAnnotator(output_dir=output_file.parent, game=game)
        print(f"  Loaded {len(annotator.decks)} decks")

        # Generate similarity annotations
        print(f"  Starting annotation generation (this may take a while)...")
        similarity_annotations = await annotator.annotate_similarity_pairs(
            num_pairs=num_annotations,
            strategy=strategy,
            batch_size=batch_size,
        )
        print(f"  Generated {len(similarity_annotations)} annotations")

        # Convert to unified format and save
        output_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = output_file.with_suffix(output_file.suffix + ".tmp")

        count = 0
        with open(temp_file, "w") as f:
            for ann in similarity_annotations:
                # Convert Pydantic model to dict
                if hasattr(ann, "model_dump"):
                    ann_dict = ann.model_dump()
                else:
                    ann_dict = dict(ann)

                # Extract card names for error messages
                card1 = ann_dict.get("card1", "unknown")
                card2 = ann_dict.get("card2", "unknown")

                # Ensure required fields for UnifiedAnnotation validation
                ann_dict["game"] = game
                if "source" not in ann_dict or not ann_dict["source"]:
                    ann_dict["source"] = "llm"
                
                # Fix similarity_score - handle various input formats
                if "similarity_score" not in ann_dict or ann_dict["similarity_score"] is None:
                    # Try to extract from confidence field
                    if "confidence" in ann_dict:
                        conf_value = ann_dict["confidence"]
                        # Handle boolean (True/False) - convert to 0.5/0.0
                        if isinstance(conf_value, bool):
                            ann_dict["similarity_score"] = 0.5 if conf_value else 0.0
                            print(f"  Warning: Converted boolean confidence to similarity_score for {card1} vs {card2}")
                        elif isinstance(conf_value, (int, float)):
                            ann_dict["similarity_score"] = float(conf_value)
                        else:
                            # Unknown type - use fallback but warn
                            ann_dict["similarity_score"] = 0.5
                            print(f"  Warning: Unknown confidence type {type(conf_value)}, using fallback 0.5")
                    else:
                        # No confidence field - this should not happen with proper LLM generation
                        ann_dict["similarity_score"] = 0.5  # Default fallback
                        print(f"  Warning: Missing similarity_score and confidence for {card1} vs {card2}, using fallback 0.5")
                
                # Validate similarity_score is in valid range
                if not (0.0 <= ann_dict["similarity_score"] <= 1.0):
                    print(f"  Warning: similarity_score {ann_dict['similarity_score']} out of range, clamping to [0.0, 1.0]")
                    ann_dict["similarity_score"] = max(0.0, min(1.0, ann_dict["similarity_score"]))

                # Write as JSONL
                f.write(json.dumps(ann_dict, ensure_ascii=False) + "\n")
                count += 1

        # Atomic write
        temp_file.replace(output_file)

        elapsed = time.time() - start_time
        rate = count / elapsed if elapsed > 0 else 0
        
        print(f"✅ [{game.upper()}] Generated {count} annotations in {elapsed:.1f}s ({rate:.1f} ann/s)")
        print(f"   Saved to: {output_file}")
        return count

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ [{game.upper()}] Error after {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        return 0


async def main_async() -> int:
    """Async main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate REAL LLM annotations for card similarity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 50 Magic annotations
  python3 scripts/annotation/generate_llm_annotations.py --game magic --num-annotations 50

  # Generate annotations for all games
  python3 scripts/annotation/generate_llm_annotations.py --game all --num-annotations 30
        """,
    )
    parser.add_argument(
        "--game",
        choices=["magic", "pokemon", "yugioh", "digimon", "onepiece", "riftbound", "all"],
        default="magic",
        help="Game to generate annotations for",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for annotations (default: annotations/)",
    )
    parser.add_argument(
        "--num-annotations",
        type=int,
        default=50,
        help="Number of annotations per game",
    )
    parser.add_argument(
        "--strategy",
        choices=["diverse", "focused"],
        default="diverse",
        help="Annotation strategy",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Batch size for parallel annotation generation (default: 20, increase for faster processing)",
    )

    args = parser.parse_args()

    if not HAS_LLM_ANNOTATOR:
        print("Error: LLM annotator not available")
        print("Install dependencies: uv sync")
        return 1

    # Determine output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = project_root / "annotations"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("GENERATING REAL LLM ANNOTATIONS")
    print("=" * 80)
    print()

    games = []
    if args.game == "all":
        games = ["magic", "pokemon", "yugioh", "riftbound"]
    else:
        games = [args.game]

    # Generate annotations for all games in parallel
    if len(games) > 1:
        print(f"Generating annotations for {len(games)} games in parallel...")
        tasks = [
            generate_annotations_for_game(
                game=game,
                output_file=output_dir / f"{game}_llm_annotations.jsonl",
                num_annotations=args.num_annotations,
                strategy=args.strategy,
                batch_size=args.batch_size,
            )
            for game in games
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_generated = sum(r if not isinstance(r, Exception) else 0 for r in results)
    else:
        # Single game - no need for parallel execution
        total_generated = 0
        for game in games:
            output_file = output_dir / f"{game}_llm_annotations.jsonl"
            count = await generate_annotations_for_game(
                game=game,
                output_file=output_file,
                num_annotations=args.num_annotations,
                strategy=args.strategy,
                batch_size=args.batch_size,
            )
            total_generated += count
        print()

    print("=" * 80)
    print(f"Generated {total_generated} total REAL LLM annotations")
    print("=" * 80)

    return 0 if total_generated > 0 else 1


def main() -> int:
    """Main entry point."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
