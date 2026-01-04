#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
# "torch>=2.0.0",
# "torch-geometric>=2.4.0",
# "gensim>=4.3.0",
# "numpy",
# "pandas",
# "sentence-transformers",
# ]
# ///
"""
Full Hybrid Embedding Training Pipeline

Trains all three components of the hybrid system:
1. Incremental Graph (from decks_all_final.jsonl or pairs_large.csv)
2. GNN Embeddings (GraphSAGE on the graph)
3. Instruction-Tuned Embeddings (zero-shot, no training needed)

Designed for use with runctl:
- Local: For testing and small datasets
- AWS: For full training (recommended, 4-8x faster)
- Uses S3 paths for cloud training (--data-s3, --output-s3)
- Supports checkpointing for long runs (--checkpoint-interval)
- Can resume from checkpoints (--resume-from)

Primary training data:
- decks_all_final.jsonl (69K decks, recommended)
- pairs_large.csv (7.5M pairs, alternative)

All progress is shown (no tail/head piping per cursor rules).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..similarity.gnn_embeddings import CardGNNEmbedder
from ..similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
from ..utils.logging_config import log_exception, log_progress, setup_script_logging
from ..utils.paths import PATHS


logger = setup_script_logging()


def save_graph_progress(
    graph: IncrementalCardGraph,
    progress_dir: Path,
    stage: str,
) -> None:
    """Save intermediate graph building progress."""
    progress_dir = Path(progress_dir)
    progress_dir.mkdir(parents=True, exist_ok=True)

    progress_file = progress_dir / f"graph_progress_{stage}.json"
    stats = graph.get_statistics() if hasattr(graph, "get_statistics") else {}

    progress = {
        "stage": stage,
        "timestamp": datetime.now().isoformat(),
        "num_nodes": len(graph.nodes),
        "num_edges": len(graph.edges),
        "stats": stats,
    }

    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2)

    logger.info(f"Graph progress saved: {progress_file}")


def build_incremental_graph(
    decks_path: Path,
    graph_path: Path,
    use_temporal_split: bool = True,
    train_frac: float = 0.7,
    val_frac: float = 0.15,
    progress_dir: Path | None = None,
    use_sqlite: bool | None = None,
    game: str | None = None,
) -> IncrementalCardGraph:
    """
    Build incremental graph from decks with optional temporal split.

    Args:
    decks_path: Path to decks JSONL
    graph_path: Path to save graph
    use_temporal_split: If True, only use train/val decks (exclude test period)
    train_frac: Fraction of decks for training
    val_frac: Fraction of decks for validation

    Returns:
    IncrementalCardGraph (train+val only if use_temporal_split=True)
    """
    logger.info("=" * 70)
    logger.info("STEP 1: Building Incremental Graph")
    logger.info("=" * 70)

    # Load card attributes if available
    card_attributes = {}
    card_attrs_path = PATHS.card_attributes
    if card_attrs_path.exists():
        logger.info(f"Loading card attributes from {card_attrs_path}...")
        try:
            import pandas as pd

            attrs_df = pd.read_csv(card_attrs_path)
            # OPTIMIZATION: Use vectorized operations instead of iterrows() (60-200x faster)
            # Get name column (handle different column names)
            name_col = None
            for col in ["NAME", "name", "card_name", "Card"]:
                if col in attrs_df.columns:
                    name_col = col
                    break

            if name_col:
                # Vectorized processing: filter valid rows and create dictionary
                valid_mask = attrs_df[name_col].notna() & (
                    attrs_df[name_col].astype(str).str.strip() != ""
                )
                valid_df = attrs_df[valid_mask]

                # Build dictionary using vectorized operations
                for idx in valid_df.index:
                    row = valid_df.loc[idx]
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
                        }
            logger.info(f" Loaded attributes for {len(card_attributes):,} cards")
        except Exception as e:
            logger.warning(f" Could not load card attributes: {e}")

    # Auto-detect SQLite from extension
    if use_sqlite is None:
        use_sqlite = graph_path.suffix == ".db" if graph_path else False

    graph = IncrementalCardGraph(graph_path, card_attributes=card_attributes, use_sqlite=use_sqlite)

    if graph.nodes and len(graph.nodes) > 0:
        logger.info(f"Graph already exists: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        logger.info(" Use --rebuild to rebuild from scratch")
        return graph

    logger.info(f"Loading decks from {decks_path}...")
    if not decks_path.exists():
        raise FileNotFoundError(f"Decks file not found: {decks_path}")

    # Load all decks with timestamps
    all_decks = []
    with open(decks_path) as f:
        line_count = 0
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            line_count += 1
            if line_count % 10000 == 0:
                log_progress(logger, "deck_loading", progress=line_count)

            try:
                deck = json.loads(line)
                # Extract timestamp (check scraped_at first, then aliases for backward compatibility)
                timestamp_str = (
                    deck.get("scraped_at")
                    or deck.get("timestamp")
                    or deck.get("created_at")
                    or deck.get("date")
                )
                if timestamp_str:
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    except:
                        timestamp = datetime.now()
                else:
                    timestamp = datetime.now()

                deck["_parsed_timestamp"] = timestamp
                all_decks.append(deck)

            except json.JSONDecodeError as e:
                logger.warning(f" Skipping invalid JSON at line {line_num}: {e}")
                continue
            except Exception as e:
                logger.warning(f" Error processing deck at line {line_num}: {e}")
                continue

        log_progress(logger, "deck_loading", progress=len(all_decks), total=line_count)
    logger.info(f"Loaded {len(all_decks):,} decks")

    # Apply temporal split if requested
    if use_temporal_split:
        logger.info("Applying temporal split to prevent data leakage...")
    # Sort by timestamp
    sorted_decks = sorted(all_decks, key=lambda d: d["_parsed_timestamp"])

    n = len(sorted_decks)
    train_end = int(n * train_frac)
    val_end = train_end + int(n * val_frac)

    train_decks = sorted_decks[:train_end]
    val_decks = sorted_decks[train_end:val_end]
    test_decks = sorted_decks[val_end:]

    logger.info(
        f" Train: {len(train_decks):,} decks ({train_decks[0]['_parsed_timestamp'] if train_decks else 'N/A'} to {train_decks[-1]['_parsed_timestamp'] if train_decks else 'N/A'})"
    )
    logger.info(
        f" Val: {len(val_decks):,} decks ({val_decks[0]['_parsed_timestamp'] if val_decks else 'N/A'} to {val_decks[-1]['_parsed_timestamp'] if val_decks else 'N/A'})"
    )
    logger.info(
        f" Test: {len(test_decks):,} decks ({test_decks[0]['_parsed_timestamp'] if test_decks else 'N/A'} to {test_decks[-1]['_parsed_timestamp'] if test_decks else 'N/A'}) [EXCLUDED from graph]"
    )

    # Only use train/val decks for graph construction
    decks_to_use = train_decks + val_decks
    logger.info(f"✓ Using {len(decks_to_use):,} decks (train+val) for graph construction")

    # Validate temporal split to ensure no leakage
    if use_temporal_split:
        try:
            from ml.evaluation.leakage_analysis import validate_temporal_split

            is_valid, warnings = validate_temporal_split(
                decks_to_use, train_frac=train_frac, val_frac=val_frac
            )
            if is_valid:
                logger.info("✓ Temporal split validated - no leakage detected")
            else:
                # CRITICAL: Fail fast on data leakage - this corrupts evaluation
                error_msg = "CRITICAL: Temporal split validation failed - potential data leakage detected:\n"
                error_msg += "\n".join(f"  - {w}" for w in warnings)
                error_msg += "\n\nThis would invalidate evaluation results. Please fix deck timestamps or disable --use-temporal-split if intentional."
                logger.error(error_msg)
                raise ValueError(error_msg)
        except ValueError:
            # Re-raise validation failures
            raise
        except Exception as e:
            # For other exceptions (import errors, etc.), warn but allow continuation
            logger.warning(f"Warning: Could not validate temporal split: {e}")
            logger.warning(" Proceeding with caution - verify timestamps manually")
    else:
        logger.warning(
            "Warning: WARNING: Building graph from ALL decks - potential data leakage if test period included"
        )
        logger.warning(" Use --use-temporal-split to prevent leakage")
        decks_to_use = all_decks

    # Build graph from selected decks
    deck_count = 0
    for deck in decks_to_use:
        timestamp = deck["_parsed_timestamp"]
        deck_id = deck.get("deck_id") or deck.get("id") or f"deck_{deck_count}"

        # Extract format and metadata from deck structure
        format_value = None
        if "format" in deck:
            format_value = deck["format"]
        elif "type" in deck and isinstance(deck["type"], dict):
            inner = deck["type"].get("inner")
            if isinstance(inner, dict) and "format" in inner:
                format_value = inner["format"]

        # Extract other metadata
        event_date = (
            deck.get("event_date")
            or deck.get("eventDate")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("eventDate")
        )
        placement = deck.get("placement") or (
            deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
        ).get("placement")
        archetype = deck.get("archetype") or (
            deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
        ).get("archetype")

        # Extract enhanced tournament metadata
        tournament_type = (
            deck.get("tournament_type")
            or deck.get("tournamentType")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("tournamentType")
        )
        tournament_size = (
            deck.get("tournament_size")
            or deck.get("tournamentSize")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("tournamentSize")
        )
        location = deck.get("location") or (
            deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
        ).get("location")
        days_since_rotation = (
            deck.get("days_since_rotation")
            or deck.get("daysSinceRotation")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("daysSinceRotation")
        )
        days_since_ban = (
            deck.get("days_since_ban_update")
            or deck.get("daysSinceBanUpdate")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("daysSinceBanUpdate")
        )
        meta_share = (
            deck.get("meta_share")
            or deck.get("metaShare")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("metaShare")
        )

        # Set deck metadata before adding deck (for temporal tracking)
        deck_metadata = {}
        if format_value:
            deck_metadata["format"] = format_value
        if event_date:
            deck_metadata["event_date"] = event_date
        if placement:
            deck_metadata["placement"] = placement
        if archetype:
            deck_metadata["archetype"] = archetype
        if tournament_type:
            deck_metadata["tournament_type"] = tournament_type
        if tournament_size:
            deck_metadata["tournament_size"] = tournament_size
        if location:
            deck_metadata["location"] = location
        if days_since_rotation is not None:
            deck_metadata["days_since_rotation"] = days_since_rotation
        if days_since_ban is not None:
            deck_metadata["days_since_ban_update"] = days_since_ban
        if meta_share is not None:
            deck_metadata["meta_share"] = meta_share

        # Extract round results if available
        round_results = (
            deck.get("roundResults")
            or deck.get("round_results")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("roundResults")
        )
        if round_results:
            deck_metadata["round_results"] = round_results

        if deck_metadata:
            graph.set_deck_metadata(deck_id, deck_metadata)

        graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)
        deck_count += 1

    if deck_count % 10000 == 0:
        log_progress(
            logger,
            "deck_processing",
            progress=deck_count,
            total=len(decks_to_use),
        )

    log_progress(
        logger,
        "deck_processing",
        progress=deck_count,
        total=len(decks_to_use),
    )
    graph.save()

    # Save graph building progress
    if progress_dir:
        save_graph_progress(graph, progress_dir, "complete")

    stats = graph.get_statistics() if hasattr(graph, "get_statistics") else {}
    logger.info(f"✓ Graph built: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges")
    if stats:
        logger.info(f" Average degree: {stats.get('avg_degree', 0):.2f}")

    return graph


def train_gnn_embeddings(
    graph: IncrementalCardGraph,
    output_path: Path,
    model_type: str = "GraphSAGE",  # Options: GraphSAGE, LightGCN, GCN, GAT
    hidden_dim: int = 128,
    num_layers: int = 2,
    epochs: int = 100,
    lr: float = 0.01,
    instruction_embedder: InstructionTunedCardEmbedder | None = None,
    checkpoint_interval: int | None = None,
    resume_from: Path | None = None,
    use_contrastive: bool = False,
    contrastive_temperature: float = 0.07,
    contrastive_weight: float = 0.5,
    game: str | None = None,
) -> CardGNNEmbedder:
    """Train GNN embeddings on the graph."""
    logger.info("=" * 70)
    logger.info("STEP 2: Training GNN Embeddings")
    logger.info("=" * 70)

    # Export edgelist (filtered by game if specified)
    edgelist_path = PATHS.graphs / "hybrid_training_edgelist.edg"
    logger.info("Exporting edgelist...")
    if game:
        logger.info(f" Filtering by game: {game}")
    graph.export_edgelist(edgelist_path, min_weight=2, game=game)
    logger.info(f" Exported to {edgelist_path}")

    # Initialize instruction embedder for fallback
    if instruction_embedder is None:
        logger.info("Initializing instruction embedder for GNN fallback...")
        instruction_embedder = InstructionTunedCardEmbedder()

    # Initialize GNN embedder
    logger.info(
        f"Initializing GNN embedder (type={model_type}, dim={hidden_dim}, layers={num_layers})..."
    )
    gnn_embedder = CardGNNEmbedder(
        model_type=model_type,
        hidden_dim=hidden_dim,
        num_layers=num_layers,
        text_embedder=instruction_embedder,
    )

    # Train
    logger.info(f"Training GNN (epochs={epochs}, lr={lr})...")
    if checkpoint_interval:
        logger.info(f" Checkpointing every {checkpoint_interval} epochs")
    if resume_from:
        logger.info(f" Resuming from: {resume_from}")
    logger.info(" This may take a while...")

    # Save training stats before starting
    from ..training.progress_tracker import save_training_stats

    stats_dir = Path(output_path).parent / "training_progress"
    save_training_stats(
        stats_dir,
        {
            "model_type": model_type,
            "hidden_dim": hidden_dim,
            "num_layers": num_layers,
            "epochs": epochs,
            "learning_rate": lr,
            "edgelist_path": str(edgelist_path),
            "num_nodes": len(graph.nodes),
            "num_edges": len(graph.edges),
        },
    )

    gnn_embedder.train(
        edgelist_path,
        epochs=epochs,
        lr=lr,
        output_path=output_path,
        checkpoint_interval=checkpoint_interval,
        resume_from=resume_from,
        use_contrastive=use_contrastive,
        contrastive_temperature=contrastive_temperature,
        contrastive_weight=contrastive_weight,
    )

    logger.info(f"✓ GNN embeddings trained and saved to {output_path}")

    # Register training run in registry (if available)
    try:
        try:
            from ml.utils.training_registry import register_training_run
        except ImportError:
            from ..utils.training_registry import register_training_run

        # Extract version from output path if versioned, or auto-generate
        version = None
        if "_v" in output_path.stem:
            version = output_path.stem.split("_v")[-1]

        version = register_training_run(
            model_type="gnn",
            model_path=output_path,
            output_path=output_path,
            training_metadata={
                "model_type": model_type,
                "hidden_dim": hidden_dim,
                "num_layers": num_layers,
                "epochs": epochs,
                "lr": lr,
                "game": game,
                "num_nodes": len(graph.nodes) if hasattr(graph, "nodes") else None,
                "num_edges": len(graph.edges) if hasattr(graph, "edges") else None,
            },
            version=version,
        )
        logger.info(f"✓ Training run registered: version {version}")
    except Exception as e:
        logger.warning(f"Failed to register training run: {e}")

    return gnn_embedder


def setup_instruction_embeddings(
    model_name: str = "intfloat/e5-base-v2",
) -> InstructionTunedCardEmbedder:
    """Setup instruction-tuned embeddings (zero-shot, no training)."""
    logger.info("=" * 70)
    logger.info("STEP 3: Setting Up Instruction-Tuned Embeddings")
    logger.info("=" * 70)

    logger.info(f"Initializing {model_name}...")
    logger.info(" (This will download the model on first run)")
    embedder = InstructionTunedCardEmbedder(model_name=model_name)
    logger.info("✓ Instruction-tuned embeddings ready (zero-shot)")
    return embedder


def evaluate_components(
    graph: IncrementalCardGraph,
    gnn_embedder: CardGNNEmbedder | None,
    instruction_embedder: InstructionTunedCardEmbedder,
    test_set_path: Path,
) -> dict[str, Any]:
    """Quick evaluation of components."""
    logger.info("=" * 70)
    logger.info("STEP 4: Quick Evaluation")
    logger.info("=" * 70)

    if not test_set_path.exists():
        logger.warning(f"Test set not found: {test_set_path}")
        return {}

    with open(test_set_path) as f:
        test_data = json.load(f)

    test_set = test_data.get("queries", test_data)
    logger.info(f"Loaded test set: {len(test_set)} queries")

    results = {
        "test_set": str(test_set_path),
        "num_queries": len(test_set),
        "components": {},
    }

    # Test instruction-tuned
    logger.info("Testing instruction-tuned embeddings...")
    sample_queries = list(test_set.keys())[:5]
    for query in sample_queries:
        labels = (
            test_set[query].get("labels", [])
            if isinstance(test_set[query], dict)
            else test_set[query]
        )
        if labels:
            candidate = labels[0] if labels else query
            sim = instruction_embedder.similarity(query, candidate, instruction_type="substitution")
            logger.info(f" {query} <-> {candidate}: {sim:.4f}")

    results["components"]["instruction_tuned"] = {"tested": len(sample_queries)}

    # Test GNN if available
    if gnn_embedder:
        logger.info("Testing GNN embeddings...")
        for query in sample_queries:
            if query in gnn_embedder.embeddings:
                labels = (
                    test_set[query].get("labels", [])
                    if isinstance(test_set[query], dict)
                    else test_set[query]
                )
                if labels:
                    candidate = labels[0] if labels else query
                    if candidate in gnn_embedder.embeddings:
                        sim = gnn_embedder.similarity(query, candidate)
                        logger.info(f" {query} <-> {candidate}: {sim:.4f}")

    results["components"]["gnn"] = {"tested": len(sample_queries)}

    return results


def main() -> int:
    """Main training pipeline."""
    parser = argparse.ArgumentParser(description="Full hybrid embedding training pipeline")
    parser.add_argument(
        "--decks-path",
        type=Path,
        default=PATHS.decks_all_final,
        help="Path to decks JSONL file",
    )
    parser.add_argument(
        "--graph-path",
        type=Path,
        default=PATHS.graphs / "incremental_graph.db",
        help="Path to incremental graph (SQLite .db or JSON .json)",
    )
    parser.add_argument(
        "--use-sqlite",
        action="store_true",
        default=None,  # Auto-detect from extension
        help="Use SQLite storage (auto-detected from .db extension)",
    )
    parser.add_argument(
        "--game",
        type=str,
        choices=["MTG", "PKM", "YGO"],
        default=None,
        help="Filter graph by game for training",
    )
    parser.add_argument(
        "--gnn-output",
        type=Path,
        default=PATHS.embeddings / "gnn_graphsage.json",
        help="Output path for GNN embeddings",
    )
    parser.add_argument(
        "--model-type",
        type=str,
        default="GraphSAGE",
        choices=["GraphSAGE", "LightGCN", "GCN", "GAT"],
        help="GNN model type (GraphSAGE=inductive, LightGCN=recommendation-optimized)",
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=PATHS.test_magic,
        help="Test set for evaluation",
    )
    parser.add_argument(
        "--rebuild-graph",
        action="store_true",
        help="Rebuild graph from scratch",
    )
    parser.add_argument(
        "--skip-gnn",
        action="store_true",
        help="Skip GNN training (use existing or setup later)",
    )
    parser.add_argument(
        "--gnn-epochs",
        type=int,
        default=100,
        help="Number of GNN training epochs",
    )
    parser.add_argument(
        "--gnn-lr",
        type=float,
        default=0.01,
        help="GNN learning rate",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        help="Save checkpoint every N epochs (for long runs)",
    )
    parser.add_argument(
        "--resume-from",
        type=Path,
        help="Resume GNN training from checkpoint",
    )
    parser.add_argument(
        "--instruction-model",
        type=str,
        default="intfloat/e5-base-v2",
        help="Instruction-tuned model name",
    )
    parser.add_argument(
        "--use-temporal-split",
        action="store_true",
        default=True,
        help="Use temporal split to prevent data leakage (default: True)",
    )
    parser.add_argument(
        "--no-temporal-split",
        dest="use_temporal_split",
        action="store_false",
        help="Disable temporal split (WARNING: may cause data leakage)",
    )
    parser.add_argument(
        "--output-version",
        type=str,
        help="Version tag for output files (e.g., 'v2024-W52' or 'v2024-12-31'). If provided, outputs will be versioned (gnn_graphsage_v{version}.json). If not provided, uses default unversioned paths.",
    )
    parser.add_argument(
        "--progress-dir",
        type=Path,
        help="Directory to save training progress (metrics, checkpoints, summaries)",
    )

    args = parser.parse_args()

    # Apply versioning to output paths if --output-version provided
    if args.output_version:
        # Use centralized path resolution for versioning
        from ..utils.path_resolution import version_path

        args.gnn_output = version_path(args.gnn_output, args.output_version)
        logger.info(f"Versioning enabled: GNN output will be {args.gnn_output}")

    logger.info("=" * 70)
    logger.info("HYBRID EMBEDDING FULL TRAINING PIPELINE")
    logger.info("=" * 70)
    logger.info(f"Decks: {args.decks_path}")
    logger.info(f"Graph: {args.graph_path}")
    logger.info(f"GNN Output: {args.gnn_output}")
    logger.info(f"Test Set: {args.test_set}")
    logger.info("")

    try:
        # Step 1: Build graph
        if args.rebuild_graph and args.graph_path.exists():
            logger.info("Rebuilding graph from scratch...")
            args.graph_path.unlink()

        # Auto-detect SQLite from extension
        use_sqlite = args.use_sqlite
        if use_sqlite is None:
            use_sqlite = args.graph_path.suffix == ".db" if args.graph_path else False

        graph = build_incremental_graph(
            args.decks_path,
            args.graph_path,
            use_temporal_split=args.use_temporal_split,
            use_sqlite=use_sqlite,
            game=args.game,
        )

        # Step 2: Setup instruction embeddings (zero-shot)
        instruction_embedder = setup_instruction_embeddings(args.instruction_model)

        # Step 3: Train GNN
        gnn_embedder = None
        if not args.skip_gnn:
            if args.gnn_output.exists() and not args.rebuild_graph:
                logger.info(f"GNN model exists at {args.gnn_output}, loading...")
                gnn_embedder = CardGNNEmbedder(
                    model_path=args.gnn_output,
                    text_embedder=instruction_embedder,
                )
                logger.info("✓ GNN embeddings loaded")
            else:
                gnn_embedder = train_gnn_embeddings(
                    graph,
                    args.gnn_output,
                    model_type=args.model_type,
                    epochs=args.gnn_epochs,
                    lr=args.gnn_lr,
                    instruction_embedder=instruction_embedder,
                    checkpoint_interval=args.checkpoint_interval,
                    resume_from=args.resume_from,
                    use_contrastive=args.use_contrastive,
                    contrastive_temperature=args.contrastive_temperature,
                    contrastive_weight=args.contrastive_weight,
                    game=args.game,
                )
        else:
            logger.info("Skipping GNN training (--skip-gnn)")

        # Step 4: Quick evaluation
        eval_results = evaluate_components(
            graph,
            gnn_embedder,
            instruction_embedder,
            args.test_set,
        )

        # Summary
        logger.info("")
        logger.info("=" * 70)
        logger.info("TRAINING COMPLETE")
        logger.info("=" * 70)
        logger.info("✓ Incremental Graph: Ready")
        logger.info("✓ Instruction-Tuned Embeddings: Ready (zero-shot)")
        if gnn_embedder:
            logger.info("✓ GNN Embeddings: Trained")
        else:
            logger.info("⚠ GNN Embeddings: Skipped")
        logger.info("")
        logger.info("Next steps:")
        logger.info(" 1. Run full evaluation: just eval-hybrid-aws <instance-id>")
        logger.info(" 2. Integrate into API: Set INSTRUCTION_EMBEDDER_MODEL env var")
        logger.info(" 3. Use in production: API auto-loads on startup")

        # Register full hybrid training run (if available)
        try:
            try:
                from ml.utils.training_registry import register_training_run
            except ImportError:
                from ..utils.training_registry import register_training_run

            # Determine model path (GNN if trained, otherwise graph)
            model_path = args.gnn_output if gnn_embedder else args.graph_path

            # Extract version from output path if versioned
            version = None
            if args.output_version:
                version = args.output_version
            elif gnn_embedder and "_v" in args.gnn_output.stem:
                version = args.gnn_output.stem.split("_v")[-1]

            register_training_run(
                model_type="hybrid",
                model_path=str(model_path),
                output_path=str(args.gnn_output if gnn_embedder else args.graph_path),
                training_metadata={
                    "gnn_model_type": args.model_type if gnn_embedder else None,
                    "gnn_trained": gnn_embedder is not None,
                    "graph_path": str(args.graph_path),
                    "decks_path": str(args.decks_path),
                    "instruction_model": args.instruction_model,
                    "use_temporal_split": args.use_temporal_split,
                    "game": args.game,
                },
                version=version,
            )
            logger.info("✓ Hybrid training run registered")
        except Exception as e:
            logger.warning(f"Failed to register hybrid training run: {e}")

        return 0

    except Exception as e:
        log_exception(logger, "Training failed", e, include_context=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
