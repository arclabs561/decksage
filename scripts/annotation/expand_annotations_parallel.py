#!/usr/bin/env python3
"""
Expand annotations using both browser-based and parallel synthetic LLM methods.

Runs:
1. Browser-based annotation (E2E via MCP browser tools)
2. Parallel synthetic LLM judges (multiple models/prompts)
3. Validates all new annotations
4. Integrates with existing annotations
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.annotation.llm_annotator import LLMAnnotator
    from ml.experimental.multi_perspective_judge import MultiPerspectiveJudge
    from ml.scripts.parallel_multi_judge import generate_labels_parallel

    HAS_LLM = True
except ImportError as e:
    HAS_LLM = False
    print(f"Warning: LLM tools not available: {e}")


async def generate_llm_annotations_parallel(
    num_annotations: int = 50,
    game: str = "magic",
    output_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Generate LLM annotations using parallel multi-judge system.
    
    Args:
        num_annotations: Number of similarity annotations to generate
        game: Game to generate annotations for
        output_dir: Output directory for annotations
        
    Returns:
        List of annotation dictionaries
    """
    if not HAS_LLM:
        print("LLM tools not available, skipping LLM annotation generation")
        return []
    
    if not os.getenv("OPENROUTER_API_KEY"):
        print("Warning: OPENROUTER_API_KEY not set, skipping LLM annotations")
        return []
    
    output_dir = output_dir or Path("annotations")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print("GENERATING PARALLEL LLM ANNOTATIONS")
    print("=" * 80)
    print(f"Game: {game}")
    print(f"Target: {num_annotations} annotations")
    print()
    
    # Initialize annotator
    annotator = LLMAnnotator(output_dir=output_dir)
    
    # Generate similarity annotations
    print("Generating similarity annotations...")
    similarity_annotations = await annotator.annotate_similarity_pairs(
        num_pairs=num_annotations,
        strategy="diverse",
    )
    
    print(f"Generated {len(similarity_annotations)} similarity annotations")
    
    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"{game}_parallel_llm_annotations_{timestamp}.jsonl"
    
    with open(output_file, "w") as f:
        for ann in similarity_annotations:
            f.write(json.dumps(ann.model_dump()) + "\n")
    
    print(f"Saved to: {output_file}")
    
    return [ann.model_dump() for ann in similarity_annotations]


async def generate_multi_judge_annotations(
    query_cards: list[str],
    candidates_per_query: int = 10,
    output_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Generate annotations using multi-judge system with different perspectives.
    
    Args:
        query_cards: List of query cards to annotate
        candidates_per_query: Number of candidates per query
        output_dir: Output directory for annotations
        
    Returns:
        List of annotation dictionaries
    """
    if not HAS_LLM:
        print("LLM tools not available, skipping multi-judge annotation generation")
        return []
    
    if not os.getenv("OPENROUTER_API_KEY"):
        print("Warning: OPENROUTER_API_KEY not set, skipping multi-judge annotations")
        return []
    
    output_dir = output_dir or Path("annotations")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print("GENERATING MULTI-JUDGE ANNOTATIONS")
    print("=" * 80)
    print(f"Queries: {len(query_cards)}")
    print(f"Candidates per query: {candidates_per_query}")
    print()
    
    # Initialize multi-perspective judge
    multi_judge = MultiPerspectiveJudge(annotation_dir=output_dir)
    
    all_annotations = []
    
    for query_card in query_cards:
        print(f"Processing query: {query_card}")
        
        # Get candidates (simplified - in practice, use embedding similarity)
        # For now, we'll use the LLM annotator to get candidates
        try:
            annotator = LLMAnnotator(output_dir=output_dir)
            # Generate a batch of similarity pairs that include this query
            similarity_annotations = await annotator.annotate_similarity_pairs(
                num_pairs=candidates_per_query,
                strategy="focused",  # Focus on specific cards
            )
            
            # Extract candidates from similarity annotations
            candidates = []
            for ann in similarity_annotations[:candidates_per_query]:
                if ann.card1 == query_card:
                    candidates.append(ann.card2)
                elif ann.card2 == query_card:
                    candidates.append(ann.card1)
            
            if not candidates:
                print(f"  ⚠ No candidates found for {query_card}, skipping")
                continue
            
            # Generate multi-perspective judgments
            judgments = await multi_judge.judge_multi_perspective(
                query_card=query_card,
                candidate_cards=candidates[:candidates_per_query],
            )
            
            # Convert judgments to annotations
            for judgment in judgments:
                annotations = multi_judge._judgment_to_annotations(judgment)
                all_annotations.extend(annotations)
            
            print(f"  Generated {len(judgments)} judgments for {query_card}")
            
        except Exception as e:
            print(f"  ⚠ Error processing {query_card}: {e}")
            continue
    
    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"multi_judge_annotations_{timestamp}.jsonl"
    
    with open(output_file, "w") as f:
        for ann in all_annotations:
            f.write(json.dumps(ann) + "\n")
    
    print(f"\nSaved {len(all_annotations)} multi-judge annotations to: {output_file}")
    
    return all_annotations


async def generate_browser_annotations(
    batch_file: Path | None = None,
    output_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Generate browser-based annotations using MCP browser tools.
    
    Note: This is a placeholder - actual browser annotation requires
    interactive MCP browser tools which need to be called separately.
    
    Args:
        batch_file: YAML batch file for annotation
        output_dir: Output directory for annotations
        
    Returns:
        List of annotation dictionaries
    """
    output_dir = output_dir or Path("annotations")
    
    print("=" * 80)
    print("BROWSER-BASED ANNOTATION")
    print("=" * 80)
    print()
    print("Note: Browser-based annotation requires interactive MCP browser tools.")
    print("Please use the browser_annotate.py tool separately to generate HTML files,")
    print("then annotate in browser and convert the results.")
    print()
    
    # Check for existing browser annotation results
    browser_files = list(output_dir.glob("browser_annotation_*.json"))
    if browser_files:
        print(f"Found {len(browser_files)} browser annotation result files:")
        all_annotations = []
        for file_path in browser_files:
            try:
                with open(file_path) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_annotations.extend(data)
                    elif isinstance(data, dict) and "annotations" in data:
                        all_annotations.extend(data["annotations"])
                print(f"  {file_path.name}: {len(all_annotations)} annotations")
            except Exception as e:
                print(f"  ⚠ Error loading {file_path.name}: {e}")
        
        return all_annotations
    
    print("No browser annotation results found.")
    return []


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Expand annotations using browser and parallel LLM methods"
    )
    parser.add_argument(
        "--game",
        choices=["magic", "pokemon", "yugioh", "digimon", "onepiece", "riftbound", "all"],
        default="magic",
        help="Game to generate annotations for",
    )
    parser.add_argument(
        "--num-llm-annotations",
        type=int,
        default=50,
        help="Number of LLM similarity annotations to generate",
    )
    parser.add_argument(
        "--num-queries",
        type=int,
        default=5,
        help="Number of queries for multi-judge annotations",
    )
    parser.add_argument(
        "--candidates-per-query",
        type=int,
        default=10,
        help="Number of candidates per query for multi-judge",
    )
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Directory for annotation files",
    )
    parser.add_argument(
        "--skip-browser",
        action="store_true",
        help="Skip browser-based annotation",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM annotation generation",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="Validate annotations after generation",
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("EXPANDING ANNOTATIONS - PARALLEL GENERATION")
    print("=" * 80)
    print()
    
    all_new_annotations = []
    
    # 1. Generate browser annotations (if not skipped)
    if not args.skip_browser:
        print("\n" + "=" * 80)
        browser_annotations = await generate_browser_annotations(
            output_dir=args.annotations_dir,
        )
        all_new_annotations.extend(browser_annotations)
        print(f"Browser annotations: {len(browser_annotations)}")
    
    # 2. Generate parallel LLM annotations (if not skipped)
    if not args.skip_llm and HAS_LLM:
        print("\n" + "=" * 80)
        games = [args.game] if args.game != "all" else ["magic", "pokemon", "yugioh"]
        
        for game in games:
            llm_annotations = await generate_llm_annotations_parallel(
                num_annotations=args.num_llm_annotations,
                game=game,
                output_dir=args.annotations_dir,
            )
            all_new_annotations.extend(llm_annotations)
    
    # 3. Generate multi-judge annotations (if not skipped)
    if not args.skip_llm and HAS_LLM:
        print("\n" + "=" * 80)
        # Select query cards (simplified - in practice, use diverse selection)
        query_cards = [
            "Lightning Bolt",
            "Sol Ring",
            "Brainstorm",
            "Path to Exile",
            "Counterspell",
        ][:args.num_queries]
        
        multi_judge_annotations = await generate_multi_judge_annotations(
            query_cards=query_cards,
            candidates_per_query=args.candidates_per_query,
            output_dir=args.annotations_dir,
        )
        all_new_annotations.extend(multi_judge_annotations)
    
    print("\n" + "=" * 80)
    print("GENERATION SUMMARY")
    print("=" * 80)
    print(f"Total new annotations: {len(all_new_annotations)}")
    
    # 4. Validate annotations
    if args.validate and all_new_annotations:
        print("\n" + "=" * 80)
        print("VALIDATING ANNOTATIONS")
        print("=" * 80)
        
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                'annotation_models',
                project_root / 'src' / 'ml' / 'utils' / 'annotation_models.py'
            )
            if spec and spec.loader:
                annotation_models = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(annotation_models)
                
                valid, invalid, errors = annotation_models.validate_annotations_batch(
                    all_new_annotations,
                    strict=False,
                )
                
                print(f"Valid annotations: {len(valid)}")
                print(f"Invalid annotations: {len(invalid)}")
                if errors:
                    print(f"Errors: {len(errors)}")
                    for error in errors[:10]:
                        print(f"  - {error}")
        except Exception as e:
            print(f"Validation failed: {e}")
    
    # 5. Integrate with existing annotations
    print("\n" + "=" * 80)
    print("INTEGRATING WITH EXISTING ANNOTATIONS")
    print("=" * 80)
    
    try:
        # Use the integration script
        import subprocess
        result = subprocess.run(
            [
                sys.executable,
                str(project_root / "scripts" / "annotation" / "integrate_all_annotations.py"),
                "--output",
                str(args.annotations_dir / "expanded_integrated.jsonl"),
            ],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            print("✓ Integration successful")
        else:
            print(f"⚠ Integration had issues: {result.stderr}")
    except Exception as e:
        print(f"⚠ Integration failed: {e}")
    
    print("\n" + "=" * 80)
    print("EXPANSION COMPLETE")
    print("=" * 80)
    print(f"Total new annotations generated: {len(all_new_annotations)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


