#!/usr/bin/env python3
"""
Complete hand annotations using browser tool.

Generates browser annotation interfaces for incomplete hand annotation batches.
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.annotation.browser_annotate import create_browser_annotation_interface


def find_incomplete_batches(annotations_dir: Path, game: str | None = None) -> list[Path]:
    """Find hand annotation batches with incomplete annotations."""
    incomplete = []
    
    pattern = "hand_batch_*.yaml"
    if game:
        pattern = f"hand_batch_{game}*.yaml"
    
    for batch_file in annotations_dir.glob(pattern):
        # Check completion
        import yaml
        with open(batch_file) as f:
            data = yaml.safe_load(f)
        
        tasks = data.get("tasks", [])
        total_candidates = 0
        graded_candidates = 0
        
        for task in tasks:
            for cand in task.get("candidates", []):
                total_candidates += 1
                if cand.get("relevance") is not None:
                    graded_candidates += 1
        
        if total_candidates > 0 and graded_candidates < total_candidates:
            completion_rate = graded_candidates / total_candidates
            incomplete.append((batch_file, completion_rate, total_candidates - graded_candidates))
    
    # Sort by completion rate (lowest first)
    incomplete.sort(key=lambda x: x[1])
    return [f for f, _, _ in incomplete]


def create_browser_interfaces_for_batch(
    batch_file: Path,
    max_queries: int = 20,
    output_dir: Path | None = None,
) -> list[Path]:
    """Create browser annotation interfaces for incomplete queries in a batch."""
    import yaml
    
    with open(batch_file) as f:
        data = yaml.safe_load(f)
    
    tasks = data.get("tasks", [])
    output_dir = output_dir or batch_file.parent
    
    created_files = []
    query_count = 0
    
    for task in tasks:
        if query_count >= max_queries:
            break
        
        query = task.get("query", "")
        if not query:
            continue
        
        # Check if query is incomplete
        candidates = task.get("candidates", [])
        incomplete = [c for c in candidates if c.get("relevance") is None]
        
        if not incomplete:
            continue  # Query already complete
        
        # Create browser interface for this query
        candidate_names = [c.get("card", "") for c in incomplete if c.get("card")]
        if not candidate_names:
            continue
        
        # Limit candidates for browser interface (too many is overwhelming)
        candidate_names = candidate_names[:20]
        
        html_file = output_dir / f"browser_annotation_{query.replace(' ', '_').replace('/', '_')}.html"
        
        try:
            create_browser_annotation_interface(
                query,
                candidate_names,
                html_file,
            )
            created_files.append(html_file)
            query_count += 1
            print(f"  Created interface for query {query_count}: {query} ({len(candidate_names)} candidates)")
        except Exception as e:
            print(f"  Error creating interface for {query}: {e}")
    
    return created_files


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Complete hand annotations using browser tool"
    )
    parser.add_argument(
        "--batch",
        type=Path,
        help="Specific batch file to complete",
    )
    parser.add_argument(
        "--game",
        type=str,
        help="Game to process (magic, pokemon, yugioh)",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=20,
        help="Maximum number of queries to create interfaces for",
    )
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=project_root / "annotations",
        help="Annotations directory",
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("COMPLETE HAND ANNOTATIONS WITH BROWSER TOOL")
    print("=" * 80)
    print()
    
    if args.batch:
        # Process specific batch
        if not args.batch.exists():
            print(f"Error: Batch file not found: {args.batch}")
            return 1
        
        print(f"Processing batch: {args.batch.name}")
        created = create_browser_interfaces_for_batch(
            args.batch,
            args.max_queries,
        )
        
        print(f"\n✓ Created {len(created)} browser annotation interfaces")
        print("\nNext steps:")
        print("1. Open the HTML files in a browser")
        print("2. Complete annotations (rate 0-4 for each candidate)")
        print("3. Download the JSON results")
        print("4. Convert using: python scripts/annotation/browser_annotate.py convert")
        
    else:
        # Find incomplete batches
        incomplete = find_incomplete_batches(args.annotations_dir, args.game)
        
        if not incomplete:
            print("No incomplete batches found")
            return 0
        
        print(f"Found {len(incomplete)} incomplete batches:")
        for batch_file in incomplete:
            print(f"  - {batch_file.name}")
        
        # Process first incomplete batch
        if incomplete:
            print(f"\nProcessing first incomplete batch: {incomplete[0].name}")
            created = create_browser_interfaces_for_batch(
                incomplete[0],
                args.max_queries,
            )
            
            print(f"\n✓ Created {len(created)} browser annotation interfaces")
            print("\nNext steps:")
            print("1. Open the HTML files in a browser")
            print("2. Complete annotations")
            print("3. Download JSON and convert")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


