#!/usr/bin/env python3
"""Enrich existing annotations with graph DB data.

Takes existing annotation files and adds:
- Graph features (Jaccard, co-occurrence, graph distance)
- Card attribute comparison
- Contextual analysis (archetype, format, temporal)
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.annotation.graph_enricher import enrich_annotation_with_graph
from ml.data.incremental_graph import IncrementalCardGraph
from ml.utils.paths import PATHS


def load_card_attributes() -> dict[str, dict[str, any]] | None:
    """Load card attributes from CSV."""
    try:
        import pandas as pd

        attrs_path = PATHS.card_attributes
        if not attrs_path.exists():
            print("Warning: Card attributes file not found")
            return None

        df = pd.read_csv(attrs_path)
        
        # Find name column
        name_col = None
        for col in ["NAME", "name", "card_name", "Card"]:
            if col in df.columns:
                name_col = col
                break
        
        if not name_col:
            print("Warning: Could not find name column in card attributes")
            return None

        card_attributes = {}
        for idx, row in df.iterrows():
            card_name = str(row[name_col]).strip()
            if card_name:
                card_attributes[card_name] = {
                    "power": row.get("power"),
                    "toughness": row.get("toughness"),
                    "oracle_text": row.get("oracle_text"),
                    "keywords": row.get("keywords"),
                    "rarity": row.get("rarity"),
                    "mana_cost": row.get("mana_cost"),
                    "color_identity": row.get("color_identity"),
                    "cmc": row.get("cmc"),
                    "type": row.get("type") or row.get("type_line"),
                    "subtypes": row.get("subtypes"),
                }

        print(f"Loaded attributes for {len(card_attributes):,} cards")
        return card_attributes
    except Exception as e:
        print(f"Warning: Could not load card attributes: {e}")
        return None


def enrich_annotations_file(
    input_path: Path,
    output_path: Path | None = None,
    graph: IncrementalCardGraph | None = None,
    card_attributes: dict[str, dict[str, any]] | None = None,
    lazy_graph_path: Path | None = None,
    game: str | None = None,
) -> int:
    """Enrich annotations in a file with graph data."""
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1

    output_path = output_path or input_path.with_suffix(".enriched.jsonl")
    
    print(f"Enriching annotations from: {input_path}")
    print(f"Output: {output_path}")

    enriched_count = 0
    total_count = 0
    errors = []

    # Use atomic write
    temp_file = output_path.with_suffix(output_path.suffix + ".tmp")

    print(f"Processing annotations...")
    print(f"  Using {'lazy graph loading' if lazy_graph_path else 'full graph' if graph else 'no graph'}")
    if lazy_graph_path:
        print(f"  Graph DB: {lazy_graph_path}")
        if game:
            print(f"  Game filter: {game}")
    
    start_time = time.time()
    last_log_time = start_time
    
    # Reuse lazy graph enricher for all annotations (much faster)
    lazy_enricher = None
    if lazy_graph_path and lazy_graph_path.exists():
        try:
            from ml.annotation.lazy_graph_enricher import LazyGraphEnricher
            lazy_enricher = LazyGraphEnricher(lazy_graph_path, game=game)
            lazy_enricher.__enter__()  # Manually enter context
            print(f"  ✓ Reusing graph connection for all annotations")
        except Exception as e:
            print(f"  ⚠️  Could not initialize lazy enricher: {e}")
            lazy_enricher = None
    
    try:
        with open(input_path, "r") as f_in, open(temp_file, "w") as f_out:
            for line_num, line in enumerate(f_in, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    annotation = json.loads(line)
                    total_count += 1

                    # Progress tracking with timing
                    current_time = time.time()
                    elapsed = current_time - start_time
                    time_since_last_log = current_time - last_log_time
                    
                    # Log every 5 annotations or every 3 seconds, whichever comes first
                    should_log = (
                        total_count % 5 == 0 or 
                        total_count == 1 or 
                        time_since_last_log >= 3.0
                    )
                    
                    if should_log:
                        rate = total_count / elapsed if elapsed > 0.1 else 0
                        pct_enriched = (enriched_count / total_count * 100) if total_count > 0 else 0
                        print(f"  [{total_count:4d}] Enriched: {enriched_count:4d} ({pct_enriched:5.1f}%) | "
                              f"Time: {elapsed:6.1f}s | Rate: {rate:5.2f} ann/s", flush=True)
                        last_log_time = current_time

                    # Enrich annotation
                    enrich_start = time.time()
                    card1 = annotation.get("card1", "")[:30]  # Truncate for logging
                    card2 = annotation.get("card2", "")[:30]
                    
                    # Use lazy graph enricher if available, otherwise use full graph
                    if lazy_enricher:
                        try:
                            # Extract graph features using lazy loading
                            if annotation.get("card1") and annotation.get("card2"):
                                graph_features = lazy_enricher.extract_graph_features(
                                    annotation["card1"], annotation["card2"]
                                )
                                
                                # Use standard enrichment for card attributes and contextual
                                enriched = enrich_annotation_with_graph(
                                    annotation, None, card_attributes  # Pass None for graph
                                )
                                
                                # Add lazy-loaded graph features
                                if graph_features:
                                    enriched["graph_features"] = graph_features.model_dump() if hasattr(graph_features, "model_dump") else graph_features.__dict__
                                    
                                    # Log interesting enrichments occasionally
                                    if total_count % 25 == 0 and graph_features.cooccurrence_count > 0:
                                        enrich_time = (time.time() - enrich_start) * 1000
                                        print(f"    → {card1} ↔ {card2}: "
                                              f"co-occur={graph_features.cooccurrence_count}, "
                                              f"jaccard={graph_features.jaccard_similarity:.3f}, "
                                              f"{enrich_time:.0f}ms", flush=True)
                            else:
                                enriched = enrich_annotation_with_graph(
                                    annotation, graph, card_attributes
                                )
                        except Exception as e:
                            print(f"  [{total_count}] ⚠️  Lazy enrichment failed for {card1}↔{card2}: {e}", flush=True)
                            # Fallback to standard enrichment
                            enriched = enrich_annotation_with_graph(
                                annotation, graph, card_attributes
                            )
                    else:
                        enriched = enrich_annotation_with_graph(
                            annotation, graph, card_attributes
                        )

                    # Check if enrichment added data
                    has_enrichment = bool(
                        enriched.get("graph_features") or 
                        enriched.get("card_comparison") or 
                        enriched.get("contextual_analysis")
                    )
                    if has_enrichment:
                        enriched_count += 1

                    # Write enriched annotation
                    f_out.write(json.dumps(enriched, ensure_ascii=False) + "\n")

                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON: {e}")
                except Exception as e:
                    errors.append(f"Line {line_num}: Error enriching: {e}")
    finally:
        # Clean up lazy enricher if we created it
        if lazy_enricher:
            try:
                lazy_enricher.__exit__(None, None, None)  # Manually exit context
            except Exception:
                pass

    # Atomic write
    total_time = time.time() - start_time
    temp_file.replace(output_path)

    print(f"\n{'=' * 80}")
    print(f"✅ ENRICHMENT COMPLETE")
    print(f"{'=' * 80}")
    print(f"Total annotations: {total_count}")
    print(f"Enriched: {enriched_count} ({enriched_count/total_count*100:.1f}%)" if total_count > 0 else "No annotations processed")
    print(f"Total time: {total_time:.1f}s")
    if total_count > 0:
        print(f"Average time per annotation: {total_time/total_count*1000:.1f}ms")
        print(f"Rate: {total_count/total_time:.1f} annotations/second")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for error in errors[:10]:  # Show first 10 errors
            print(f"  {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
    print(f"{'=' * 80}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enrich existing annotations with graph DB data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Enrich a single annotation file
  python3 scripts/annotation/enrich_existing_annotations.py \\
    --input annotations/magic_llm_annotations.jsonl

  # Enrich with custom output path
  python3 scripts/annotation/enrich_existing_annotations.py \\
    --input annotations/magic_llm_annotations.jsonl \\
    --output annotations/magic_llm_annotations_enriched.jsonl

  # Enrich all annotation files in a directory
  python3 scripts/annotation/enrich_existing_annotations.py \\
    --input-dir annotations/ \\
    --output-dir annotations/enriched/
        """,
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Input annotation file (JSONL)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output annotation file (default: input.enriched.jsonl)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="Input directory (enriches all .jsonl files)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory (for --input-dir mode)",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=None,
        help="Graph database path (default: data/graphs/incremental_graph.db)",
    )
    parser.add_argument(
        "--skip-graph",
        action="store_true",
        help="Skip graph enrichment (only card attributes)",
    )
    parser.add_argument(
        "--lazy-graph",
        action="store_true",
        help="Use lazy graph loading (query SQLite directly, don't load all data)",
    )
    parser.add_argument(
        "--game",
        type=str,
        help="Game filter for graph queries (magic, pokemon, yugioh, etc.)",
    )

    args = parser.parse_args()

    # Load graph (or prepare for lazy loading)
    lazy_graph_path = None
    graph = None
    if not args.skip_graph:
        graph_path = args.graph or PATHS.incremental_graph_db
        if graph_path.exists():
            if args.lazy_graph:
                print(f"Using lazy graph loading from: {graph_path}")
                lazy_graph_path = graph_path
                graph = None  # Use lazy loading instead
            else:
                print(f"Loading full graph from: {graph_path}")
                print("  (This may take a while for large graphs...)")
                graph = IncrementalCardGraph(graph_path=graph_path, use_sqlite=True)
                print(f"  Loaded {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        else:
            print(f"Warning: Graph database not found: {graph_path}")
            print("  Continuing without graph features...")

    # Load card attributes
    card_attributes = load_card_attributes()

    # Process files
    if args.input:
        # Single file mode
        return enrich_annotations_file(
            args.input, args.output, graph, card_attributes,
            lazy_graph_path=lazy_graph_path,
            game=args.game,
        )
    elif args.input_dir:
        # Directory mode
        if not args.input_dir.exists():
            print(f"Error: Input directory not found: {args.input_dir}")
            return 1

        output_dir = args.output_dir or args.input_dir / "enriched"
        output_dir.mkdir(parents=True, exist_ok=True)

        jsonl_files = list(args.input_dir.glob("*.jsonl"))
        if not jsonl_files:
            print(f"No .jsonl files found in: {args.input_dir}")
            return 1

        print(f"Found {len(jsonl_files)} annotation files")
        for jsonl_file in jsonl_files:
            output_file = output_dir / jsonl_file.name
            print(f"\nProcessing: {jsonl_file.name}")
            enrich_annotations_file(
                jsonl_file, output_file, graph, card_attributes,
                lazy_graph_path=lazy_graph_path,
                game=args.game,
            )

        print(f"\n✅ Enriched {len(jsonl_files)} files")
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())

