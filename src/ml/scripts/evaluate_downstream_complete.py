#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Complete downstream task evaluation using trained assets.

Evaluates all downstream tasks:
1. Deck completion (greedy + beam search)
2. Deck refinement (add/remove/replace/move)
3. Card substitution
4. Contextual discovery (synergies, alternatives, upgrades, downgrades)
5. Deck quality assessment

Uses trained assets:
- Embeddings (Node2Vec)
- Fusion (embedding + Jaccard + functional tags)
- Functional taggers (game-specific)
- Archetype staples
- Price data

Critiques performance vs labeled data and identifies improvements.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import numpy as np
    from gensim.models import KeyedVectors
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

import sys
import os

# Set up project paths using shared utility (must be done before other ml imports)
# Import path_setup directly to avoid dependency issues
_path_setup_file = Path(__file__).parent.parent / "utils" / "path_setup.py"
if _path_setup_file.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location("path_setup", _path_setup_file)
    path_setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(path_setup)  # type: ignore
    project_root = path_setup.setup_project_paths()
else:
    # Fallback to manual setup if path_setup.py not found
    script_path = Path(__file__).resolve()
    script_dir = script_path.parent
    project_root = script_dir
    for _ in range(8):
        markers = ["pyproject.toml", "requirements.txt", "setup.py", "Cargo.toml", ".git", "runctl.toml", ".runctl.toml"]
        if any((project_root / marker).exists() for marker in markers):
            break
        parent = project_root.parent
        if parent == project_root:
            break
        project_root = parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    src_dir = project_root / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

from ml.deck_building.deck_completion import (
    greedy_complete,
    suggest_additions,
    suggest_removals,
    suggest_replacements,
    CompletionConfig,
)
from ml.deck_building.deck_quality import assess_deck_quality
from ml.deck_building.deck_refinement import DeckRefiner, RefinementConstraints
from ml.deck_building.contextual_discovery import ContextualCardDiscovery
from ml.similarity.fusion import WeightedLateFusion, FusionWeights
from ml.similarity.similarity_methods import load_graph, jaccard_similarity
from ml.data.card_resolver import CardResolver
from ml.utils.paths import PATHS
from ml.utils.logging_config import setup_script_logging

logger = setup_script_logging()


def load_trained_assets(
    game: str,
    embeddings_path: Path | None = None,
    pairs_path: Path | None = None,
    functional_tagger_path: Path | None = None,
    fast_mode: bool = False,
    disable_functional: bool = False,
    disable_text_embed: bool = False,
) -> dict[str, Any]:
    """
    Load all trained assets for a game.
    
    Returns dict with:
    - embeddings: KeyedVectors
    - adj: adjacency dict for Jaccard
    - fusion: WeightedLateFusion instance
    - tagger: functional tagger
    - tag_set_fn: function to get tags for a card
    - price_fn: function to get price for a card (optional)
    """
    assets: dict[str, Any] = {}
    
    # Load embeddings
    # Priority: EBS volume (/mnt/data) > local paths > S3 download
    # EBS volumes are mounted at /mnt/data by runctl's user-data script
    ebs_data_dir = Path("/mnt/data")
    local_data_dir = PATHS.data
    
    if embeddings_path is None:
        # Try to find game-specific embedding
        # Check multiple locations
        possible_names = [
            f"{game}_128d_test_pecanpy",
            f"{game}_production",
            "multigame_128d",
            f"trained_{game}",
        ]
        
        embeddings_path = None
        for name in possible_names:
            try:
                candidate = PATHS.embedding(name)
                if candidate.exists():
                    embeddings_path = candidate
                    break
            except Exception:
                pass
        
        # Try trained directory - check EBS first, then local
        if embeddings_path is None or not embeddings_path.exists():
            # Check EBS volume first (faster, persistent)
            ebs_trained_dir = ebs_data_dir / "embeddings" / "trained"
            if ebs_trained_dir.exists():
                all_wv = list(ebs_trained_dir.glob("*.wv"))
                if all_wv:
                    game_matches = [p for p in all_wv if game.lower() in p.name.lower()]
                    if game_matches:
                        embeddings_path = game_matches[0]
                        logger.info(f"Found embeddings on EBS volume: {embeddings_path}")
                    else:
                        embeddings_path = all_wv[0]
                        logger.info(f"Found embeddings on EBS volume: {embeddings_path}")
            
            # Fallback to local trained directory
            if embeddings_path is None or not embeddings_path.exists():
                trained_dir = PATHS.embeddings / "trained"
                if trained_dir.exists():
                    # Find any .wv file (prefer game-specific)
                    all_wv = list(trained_dir.glob("*.wv"))
                    if all_wv:
                        game_matches = [p for p in all_wv if game.lower() in p.name.lower()]
                        if game_matches:
                            embeddings_path = game_matches[0]
                        else:
                            embeddings_path = all_wv[0]  # Use first available
    
    # Convert string paths to Path objects
    if embeddings_path and isinstance(embeddings_path, str):
        embeddings_path = Path(embeddings_path)
    
    # Try to load from S3 if local path doesn't exist
    # Only download if not on EBS (EBS should be pre-warmed)
    if embeddings_path and not embeddings_path.exists():
        # Check if it's an S3 path or try to download from S3
        if str(embeddings_path).startswith("s3://"):
            # Download to EBS if available, else /tmp
            download_dir = ebs_data_dir if ebs_data_dir.exists() else Path("/tmp")
            logger.info(f"Downloading embeddings from S3 to {download_dir}: {embeddings_path}")
            import boto3
            s3 = boto3.client("s3")
            # Extract bucket and key
            s3_path = str(embeddings_path).replace("s3://", "")
            bucket, key = s3_path.split("/", 1)
            local_path = download_dir / Path(key).name
            local_path.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(local_path))
            embeddings_path = local_path
    
    if embeddings_path and embeddings_path.exists():
        logger.info(f"Loading embeddings from {embeddings_path}")
        assets["embeddings"] = KeyedVectors.load(str(embeddings_path))
        logger.info(f"  Loaded {len(assets['embeddings'])} cards")
    else:
        logger.warning(f"Embeddings not found: {embeddings_path}")
        assets["embeddings"] = None
    
    # Load graph for Jaccard (OPTIMIZATION: prefer pairs CSV for faster loading, fallback to graph DB)
    from ml.utils.shared_operations import load_graph_for_jaccard
    
    game_code = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO"}.get(game)
    
    # OPTIMIZATION: Try pairs CSV first (faster for large graphs, ~4-5x faster than SQLite)
    # Priority: pairs CSV > graph DB (reversed from before for performance)
    pairs_path = None
    if pairs_path is None:
        # Check EBS first
        ebs_pairs = Path("/mnt/data/processed/pairs_large.csv")
        if ebs_pairs.exists() and ebs_pairs.stat().st_size > 1000:
            pairs_path = ebs_pairs
            logger.info(f"Using pairs from EBS volume: {pairs_path}")
        else:
            pairs_path = PATHS.pairs_large
            if not pairs_path.exists() or (pairs_path.exists() and pairs_path.stat().st_size < 1000):
                pairs_path = PATHS.backend / "pairs.csv"
            if not pairs_path.exists():
                pairs_path = Path("src/backend/pairs.csv")
    
    if pairs_path and pairs_path.exists() and pairs_path.stat().st_size > 1000:
        logger.info(f"Loading graph from CSV (faster): {pairs_path}")
        try:
            adj = load_graph_for_jaccard(pairs_csv=pairs_path, game=game_code)
            weights = {tuple(sorted([c1, c2])): 1.0 for c1 in adj for c2 in adj[c1]}
            assets["adj"] = adj
            assets["weights"] = weights
            logger.info(f"  Loaded graph: {len(adj)} cards, {len(weights)} edges")
        except Exception as e:
            logger.warning(f"Failed to load from CSV: {e}, trying graph database...")
            pairs_path = None
    
    # Fallback to graph database if CSV failed
    if not assets.get("adj"):
        graph_db = PATHS.incremental_graph_db
        if graph_db.exists():
            logger.info(f"Loading graph from database: {graph_db}")
            try:
                adj = load_graph_for_jaccard(graph_db=graph_db, game=game_code)
                weights = {tuple(sorted([c1, c2])): 1.0 for c1 in adj for c2 in adj[c1]}
                assets["adj"] = adj
                assets["weights"] = weights
                logger.info(f"  Loaded graph: {len(adj)} cards, {len(weights)} edges")
            except Exception as e:
                logger.warning(f"Failed to load from graph database: {e}")
                assets["adj"] = {}
                assets["weights"] = {}
    
    # Fallback to pairs CSV
    # Priority: EBS volume > local paths > S3 download
    if not assets.get("adj"):
        if pairs_path is None:
            # Check EBS first
            ebs_pairs = ebs_data_dir / "processed" / "pairs_large.csv"
            if ebs_pairs.exists() and ebs_pairs.stat().st_size > 1000:
                pairs_path = ebs_pairs
                logger.info(f"Using pairs from EBS volume: {pairs_path}")
            else:
                pairs_path = PATHS.pairs_large
                if not pairs_path.exists() or (pairs_path.exists() and pairs_path.stat().st_size < 1000):
                    pairs_path = PATHS.backend / "pairs.csv"
                if not pairs_path.exists():
                    pairs_path = Path("src/backend/pairs.csv")
        
        # Convert string to Path and handle S3
        if pairs_path and isinstance(pairs_path, str):
            pairs_path = Path(pairs_path)
        
        # Try S3 if local doesn't exist (download to EBS if available)
        if pairs_path and not pairs_path.exists():
            if str(pairs_path).startswith("s3://"):
                download_dir = ebs_data_dir if ebs_data_dir.exists() else Path("/tmp")
                logger.info(f"Downloading pairs from S3 to {download_dir}: {pairs_path}")
                import boto3
                s3 = boto3.client("s3")
                s3_path = str(pairs_path).replace("s3://", "")
                bucket, key = s3_path.split("/", 1)
                local_path = download_dir / Path(key).name
                local_path.parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(bucket, key, str(local_path))
                pairs_path = local_path
        
        if pairs_path and pairs_path.exists() and pairs_path.stat().st_size > 1000:
            logger.info(f"Loading graph from CSV: {pairs_path}")
            try:
                adj = load_graph_for_jaccard(pairs_csv=pairs_path, game=game_code)
                weights = {tuple(sorted([c1, c2])): 1.0 for c1 in adj for c2 in adj[c1]}
                assets["adj"] = adj
                assets["weights"] = weights
                logger.info(f"  Loaded graph: {len(adj)} cards, {len(weights)} edges")
            except Exception as e:
                logger.warning(f"Failed to load graph: {e}")
                assets["adj"] = {}
                assets["weights"] = {}
        else:
            logger.warning(f"Graph source not found: {pairs_path}")
            assets["adj"] = {}
            assets["weights"] = {}
    
    # Load functional tagger
    try:
        if game == "magic":
            # MTG functional tagger - try to find it
            tagger = None
            try:
                # Check if there's a card_functional_tagger module (might be in scripts)
                from ml.scripts.card_functional_tagger import FunctionalTagger
                tagger = FunctionalTagger()
            except ImportError:
                try:
                    # Try unified tagger (doesn't support MTG yet but has structure)
                    from ml.enrichment.card_functional_tagger_unified import UnifiedFunctionalTagger
                    # Create a stub tagger for MTG
                    class MTGTaggerStub:
                        def tag_card(self, card_name: str):
                            # Return empty tags object for now
                            return type('Tags', (), {})()
                    tagger = MTGTaggerStub()
                except ImportError:
                    tagger = None
        elif game == "pokemon":
            from ml.enrichment.pokemon_functional_tagger import PokemonFunctionalTagger
            tagger = PokemonFunctionalTagger()
        elif game == "yugioh":
            from ml.enrichment.yugioh_functional_tagger import YugiohFunctionalTagger
            tagger = YugiohFunctionalTagger()
        else:
            tagger = None
        
        if tagger:
            def tag_set_fn(card: str) -> set[str]:
                try:
                    # Try tag_card with card name (some taggers take name, some take data dict)
                    if hasattr(tagger, 'tag_card'):
                        tags_obj = tagger.tag_card(card)
                        # Extract boolean tags
                        tags = set()
                        if hasattr(tags_obj, '__dict__'):
                            for key, value in tags_obj.__dict__.items():
                                if isinstance(value, bool) and value:
                                    tags.add(key)
                        return tags
                    return set()
                except Exception:
                    return set()
            
            assets["tagger"] = tagger
            assets["tag_set_fn"] = tag_set_fn
            logger.info(f"  Loaded functional tagger for {game}")
        else:
            assets["tagger"] = None
            assets["tag_set_fn"] = None
            logger.warning(f"  No functional tagger available for {game}")
    except ImportError as e:
        logger.warning(f"Functional tagger not available: {e}")
        assets["tagger"] = None
        assets["tag_set_fn"] = None
    
    # Load fusion weights (try optimized first, then grid search)
    fusion_weights = None
    for weights_path in [
        PATHS.experiments / "optimized_fusion_weights_latest.json",
        PATHS.experiments / "fusion_grid_search_latest.json",
    ]:
        if weights_path.exists():
            try:
                with open(weights_path) as f:
                    data = json.load(f)
                if "recommendation" in data:
                    rec = data["recommendation"]
                    fusion_weights = FusionWeights(
                        embed=float(rec.get("embed", 0.25)),
                        jaccard=float(rec.get("jaccard", 0.75)),
                        functional=float(rec.get("functional", 0.0)),
                    ).normalized()
                else:
                    # Legacy format - include all weight fields for hybrid system compatibility
                    bw = data.get("best_weights", {})
                    fusion_weights = FusionWeights(
                        embed=float(bw.get("embed", 0.25)),
                        jaccard=float(bw.get("jaccard", 0.75)),
                        functional=float(bw.get("functional", 0.0)),
                        text_embed=float(bw.get("text_embed", 0.0)),
                        sideboard=float(bw.get("sideboard", 0.0)),
                        temporal=float(bw.get("temporal", 0.0)),
                        gnn=float(bw.get("gnn", 0.0)),
                        archetype=float(bw.get("archetype", 0.0)),
                        format=float(bw.get("format", 0.0)),
                    ).normalized()
                logger.info(f"  Loaded fusion weights: embed={fusion_weights.embed:.2f}, jaccard={fusion_weights.jaccard:.2f}, functional={fusion_weights.functional:.2f}")
                break
            except Exception as e:
                logger.debug(f"Failed to load weights from {weights_path}: {e}")
    
    if fusion_weights is None:
        # Use better weights for substitution: more functional, less jaccard
        # For substitution, functional tags are critical
        # OPTIMIZATION: Disable functional tags in fast mode
        if fast_mode or disable_functional:
            fusion_weights = FusionWeights(embed=0.5, jaccard=0.5, functional=0.0).normalized()
            logger.info(f"  Using fast mode weights (functional tags disabled)")
        else:
            fusion_weights = FusionWeights(embed=0.4, jaccard=0.4, functional=0.2).normalized()
            logger.info(f"  Using default fusion weights (optimized for substitution)")
    
    # Create fusion instance
    if assets["embeddings"] and assets["adj"]:
        # OPTIMIZATION: Disable tagger in fast mode (functional tags are expensive)
        tagger_to_use = None if (fast_mode or disable_functional) else assets["tagger"]
        fusion = WeightedLateFusion(
            embeddings=assets["embeddings"],
            adj=assets["adj"],
            tagger=tagger_to_use,
            weights=fusion_weights,
            text_embedder=None,  # Always disable text embeddings for evaluation (too slow)
        )
        assets["fusion"] = fusion
    else:
        assets["fusion"] = None
        logger.warning("Cannot create fusion (missing embeddings or graph)")
    
    # Price function - load from card database
    def price_fn(card: str) -> float | None:
        try:
            from ml.data.card_database import get_card_database
            card_db = get_card_database()
            card_data = card_db.get_card_data(card, game=game)
            if card_data and "price" in card_data:
                price = card_data["price"]
                if isinstance(price, (int, float)):
                    return float(price)
                elif isinstance(price, str):
                    # Try to parse price string
                    try:
                        return float(price.replace("$", "").replace(",", ""))
                    except ValueError:
                        return None
            return None
        except Exception as e:
            logger.debug(f"Could not get price for {card}: {e}")
            return None
    
    assets["price_fn"] = price_fn
    
    return assets


def evaluate_deck_completion_task(
    assets: dict[str, Any],
    test_decks: list[dict],
    game: str = "magic",
) -> dict[str, Any]:
    """Evaluate deck completion on test decks."""
    logger.info(f"Evaluating deck completion on {len(test_decks)} decks...")
    
    if not assets["fusion"]:
        return {"error": "Fusion not available"}
    
    def candidate_fn(card: str, k: int) -> list[tuple[str, float]]:
        if not assets["fusion"]:
            return []
        try:
            # Use task-specific instruction for deck completion
            # Use larger k to ensure we get good candidates
            candidates = assets["fusion"].similar(card, k=min(k * 2, 50), task_type="completion")
            return candidates[:k]  # Return top k
        except Exception as e:
            logger.debug(f"Failed to get candidates for {card}: {e}")
            return []
    
    results = {
        "total_decks": len(test_decks),
        "completed": 0,
        "failed": 0,
        "avg_steps": 0.0,
        "avg_quality_before": 0.0,
        "avg_quality_after": 0.0,
        "quality_improvements": [],
        "errors": [],
    }
    
    quality_before_sum = 0.0
    quality_after_sum = 0.0
    total_steps = 0
    
    def cmc_fn(card: str) -> int | None:
        # Placeholder - would load from card database
        return None
    
    for i, deck in enumerate(test_decks):
        try:
            # Create partial deck (remove some cards)
            partial_deck = json.loads(json.dumps(deck))  # Deep copy
            main_partition = "Main" if game == "magic" else "Main Deck"
            
            # Remove 10-20 cards to create partial deck
            for p in partial_deck.get("partitions", []) or []:
                if p.get("name") == main_partition:
                    cards = p.get("cards", []) or []
                    if len(cards) > 20:
                        # Remove last 15 cards
                        p["cards"] = cards[:-15]
                    break
            
            # Assess quality before
            quality_before = assess_deck_quality(
                deck=partial_deck,
                game=game,
                tag_set_fn=assets["tag_set_fn"] or (lambda x: set()),
                cmc_fn=cmc_fn,
            )
            quality_before_sum += quality_before.overall_score
            
            # Complete deck
            config = CompletionConfig(
                game=game,
                target_main_size=60 if game == "magic" else 40,
                method="fusion",
            )
            
            completed_deck, steps, quality_metrics = greedy_complete(
                game=game,
                deck=partial_deck,
                candidate_fn=candidate_fn,
                cfg=config,
                tag_set_fn=assets["tag_set_fn"],
                assess_quality=True,
            )
            
            # Assess quality after
            quality_after = assess_deck_quality(
                deck=completed_deck,
                game=game,
                tag_set_fn=assets["tag_set_fn"] or (lambda x: set()),
                cmc_fn=cmc_fn,
            )
            quality_after_sum += quality_after.overall_score
            
            improvement = quality_after.overall_score - quality_before.overall_score
            results["quality_improvements"].append(improvement)
            
            results["completed"] += 1
            total_steps += len(steps)
            
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Deck {i}: {str(e)}")
            logger.warning(f"Failed to complete deck {i}: {e}")
    
    if results["completed"] > 0:
        results["avg_steps"] = total_steps / results["completed"]
        results["avg_quality_before"] = quality_before_sum / results["completed"]
        results["avg_quality_after"] = quality_after_sum / results["completed"]
    
    return results


def evaluate_deck_refinement_task(
    assets: dict[str, Any],
    test_decks: list[dict],
    game: str = "magic",
) -> dict[str, Any]:
    """Evaluate deck refinement on test decks."""
    logger.info(f"Evaluating deck refinement on {len(test_decks)} decks...")
    
    if not assets["fusion"]:
        return {"error": "Fusion not available"}
    
    refiner = DeckRefiner(
        fusion=assets["fusion"],  # Will use task_type="completion" for adds, "substitution" for replaces
        price_fn=assets["price_fn"],
        tag_set_fn=assets["tag_set_fn"],
    )
    
    results = {
        "total_decks": len(test_decks),
        "refined": 0,
        "failed": 0,
        "add_suggestions": [],
        "remove_suggestions": [],
        "replace_suggestions": [],
        "move_suggestions": [],
        "errors": [],
    }
    
    for i, deck in enumerate(test_decks):
        try:
            constraints = RefinementConstraints(
                max_suggestions=10,
                preserve_roles=True,
            )
            
            # Test add suggestions
            add_suggestions = refiner.suggest_additions(game, deck, constraints)
            logger.debug(f"Deck {i}: Generated {len(add_suggestions)} add suggestions")
            if len(add_suggestions) == 0:
                # Debug: check if deck has cards
                main_partition = "Main" if game == "magic" else "Main Deck"
                main_cards = []
                for p in deck.get("partitions", []) or []:
                    if p.get("name") == main_partition:
                        main_cards = p.get("cards", []) or []
                        break
                logger.debug(f"Deck {i}: Has {len(main_cards)} cards in main partition")
            results["add_suggestions"].append(len(add_suggestions))
            
            # Test remove suggestions
            remove_suggestions = refiner.suggest_removals(game, deck, constraints)
            results["remove_suggestions"].append(len(remove_suggestions))
            
            # Test move suggestions
            move_suggestions = refiner.suggest_moves(game, deck, constraints)
            results["move_suggestions"].append(len(move_suggestions))
            
            results["refined"] += 1
            
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Deck {i}: {str(e)}")
            from ml.utils.logging_config import log_exception
            log_exception(logger, f"Failed to refine deck {i}", e, level="warning", include_context=True)
    
    if results["refined"] > 0:
        results["avg_add_suggestions"] = sum(results["add_suggestions"]) / results["refined"]
        results["avg_remove_suggestions"] = sum(results["remove_suggestions"]) / results["refined"]
        results["avg_move_suggestions"] = sum(results["move_suggestions"]) / results["refined"]
    
    return results


def evaluate_substitution_task(
    assets: dict[str, Any],
    test_pairs: list[tuple[str, str]],  # (original, target)
    game: str = "magic",
) -> dict[str, Any]:
    """Evaluate card substitution on test pairs."""
    logger.info(f"Evaluating substitution on {len(test_pairs)} pairs...")
    
    if not assets["fusion"]:
        return {"error": "Fusion not available"}
    
    def candidate_fn(card: str, k: int) -> list[tuple[str, float]]:
        if not assets["fusion"]:
            return []
        try:
            # Use task-specific instruction for substitution
            # Use larger k to ensure we get good candidates
            candidates = assets["fusion"].similar(card, k=min(k * 2, 50), task_type="substitution")
            return candidates[:k]  # Return top k
        except Exception as e:
            logger.debug(f"Failed to get candidates for {card}: {e}")
            return []
    
    results = {
        "total_pairs": len(test_pairs),
        "found_in_top_1": 0,
        "found_in_top_5": 0,
        "found_in_top_10": 0,
        "not_found": 0,
        "avg_rank": 0.0,
        "ranks": [],
    }
    
    rank_sum = 0.0
    
    for idx, (original, target) in enumerate(test_pairs):
        if (idx + 1) % 100 == 0:
            logger.info(f"  Progress: {idx + 1}/{len(test_pairs)} pairs evaluated...")
        try:
            candidates = candidate_fn(original, k=20)
            candidate_names = [card for card, _ in candidates]
            
            if target in candidate_names:
                rank = candidate_names.index(target) + 1
                results["ranks"].append(rank)
                rank_sum += rank
                
                if rank <= 1:
                    results["found_in_top_1"] += 1
                if rank <= 5:
                    results["found_in_top_5"] += 1
                if rank <= 10:
                    results["found_in_top_10"] += 1
            else:
                results["not_found"] += 1
                results["ranks"].append(999)  # Not found
                rank_sum += 999
                
        except Exception as e:
            logger.warning(f"Failed to evaluate pair ({original}, {target}): {e}")
            results["not_found"] += 1
    
    if results["ranks"]:
        results["avg_rank"] = rank_sum / len(results["ranks"])
        results["p_at_1"] = results["found_in_top_1"] / len(test_pairs)
        results["p_at_5"] = results["found_in_top_5"] / len(test_pairs)
        results["p_at_10"] = results["found_in_top_10"] / len(test_pairs)
    
    return results


def evaluate_contextual_discovery_task(
    assets: dict[str, Any],
    test_queries: list[dict],  # {card, format?, archetype?, expected_synergies?}
    game: str = "magic",
) -> dict[str, Any]:
    """Evaluate contextual discovery on test queries."""
    logger.info(f"Evaluating contextual discovery on {len(test_queries)} queries...")
    
    if not assets["fusion"]:
        return {"error": "Fusion not available"}
    
    discovery = ContextualCardDiscovery(
        fusion=assets["fusion"],
        price_fn=assets["price_fn"],
        tag_set_fn=assets["tag_set_fn"],
    )
    
    results = {
        "total_queries": len(test_queries),
        "synergies_found": 0,
        "alternatives_found": 0,
        "upgrades_found": 0,
        "downgrades_found": 0,
        "avg_synergies_per_query": 0.0,
        "avg_alternatives_per_query": 0.0,
    }
    
    total_synergies = 0
    total_alternatives = 0
    
    for query in test_queries:
        card = query.get("card", "")
        if not card:
            continue
        
        try:
            # Find synergies
            synergies = discovery.find_synergies(
                card=card,
                format=query.get("format"),
                archetype=query.get("archetype"),
                top_k=10,
            )
            total_synergies += len(synergies)
            if synergies:
                results["synergies_found"] += 1
            
            # Find alternatives
            alternatives = discovery.find_alternatives(card, top_k=10)
            total_alternatives += len(alternatives)
            if alternatives:
                results["alternatives_found"] += 1
            
            # Find upgrades (if price available)
            upgrades = discovery.find_upgrades(card, top_k=5)
            if upgrades:
                results["upgrades_found"] += 1
            
            # Find downgrades (if price available)
            downgrades = discovery.find_downgrades(card, top_k=5)
            if downgrades:
                results["downgrades_found"] += 1
                
        except Exception as e:
            logger.warning(f"Failed to evaluate query {card}: {e}")
    
    if results["total_queries"] > 0:
        results["avg_synergies_per_query"] = total_synergies / results["total_queries"]
        results["avg_alternatives_per_query"] = total_alternatives / results["total_queries"]
    
    return results


def critique_performance(
    results: dict[str, dict[str, Any]],
    game: str,
) -> dict[str, Any]:
    """Critique performance and suggest improvements."""
    critique = {
        "game": game,
        "overall_assessment": "",
        "strengths": [],
        "weaknesses": [],
        "recommendations": [],
    }
    
    # Analyze completion task
    if "completion" in results:
        comp = results["completion"]
        if comp.get("completed", 0) > 0:
            avg_improvement = sum(comp.get("quality_improvements", [])) / comp["completed"]
            if avg_improvement > 1.0:
                critique["strengths"].append(f"Deck completion improves quality by {avg_improvement:.2f} points on average")
            elif avg_improvement < 0:
                critique["weaknesses"].append(f"Deck completion degrades quality (avg improvement: {avg_improvement:.2f})")
                critique["recommendations"].append("Review completion algorithm - may be adding wrong cards")
    
    # Analyze substitution task
    if "substitution" in results:
        sub = results["substitution"]
        p_at_10 = sub.get("p_at_10", 0.0)
        if p_at_10 > 0.5:
            critique["strengths"].append(f"Substitution P@10 = {p_at_10:.2f} (good)")
        elif p_at_10 < 0.2:
            critique["weaknesses"].append(f"Substitution P@10 = {p_at_10:.2f} (poor)")
            critique["recommendations"].append("Improve substitution by using functional tags more heavily")
    
    # Analyze refinement task
    if "refinement" in results:
        ref = results["refinement"]
        if ref.get("refined", 0) > 0:
            avg_add = ref.get("avg_add_suggestions", 0.0)
            if avg_add > 5:
                critique["strengths"].append(f"Refinement generates {avg_add:.1f} add suggestions on average")
            elif avg_add < 2:
                critique["weaknesses"].append(f"Refinement generates few suggestions ({avg_add:.1f})")
                critique["recommendations"].append("Review refinement role gap detection")
    
    # Overall assessment
    if len(critique["strengths"]) > len(critique["weaknesses"]):
        critique["overall_assessment"] = "Generally performing well, with room for improvement"
    elif len(critique["weaknesses"]) > len(critique["strengths"]):
        critique["overall_assessment"] = "Multiple issues identified - needs significant improvement"
    else:
        critique["overall_assessment"] = "Mixed performance - some tasks work well, others need work"
    
    return critique


def main() -> int:
    """Run complete downstream evaluation."""
    parser = argparse.ArgumentParser(description="Evaluate all downstream tasks")
    parser.add_argument("--game", type=str, default="magic", choices=["magic", "pokemon", "yugioh"],
                       help="Game to evaluate")
    parser.add_argument("--embeddings", type=str, help="Embedding file (.wv)")
    parser.add_argument("--pairs", type=str, help="Pairs CSV file")
    parser.add_argument("--test-decks", type=str, help="Test decks JSONL")
    parser.add_argument("--test-substitutions", type=str, help="Test substitution pairs JSON")
    parser.add_argument("--test-contextual", type=str, help="Test contextual queries JSON")
    parser.add_argument("--output", type=str, required=True, help="Output JSON")
    parser.add_argument("--fast", action="store_true", help="Fast mode: disable expensive operations (functional tags, text embeddings)")
    parser.add_argument("--disable-functional", action="store_true", help="Disable functional tag similarity")
    parser.add_argument("--disable-text-embed", action="store_true", help="Disable text embedding similarity")
    parser.add_argument("--use-runctl", action="store_true", help="Auto-detect if running on AWS and use runctl optimizations")
    parser.add_argument("--min-pairs-for-runctl", type=int, default=1000, help="Minimum pairs to trigger runctl recommendation")
    parser.add_argument("--validate-deck-quality", action="store_true", help="Run deck quality validation after evaluation")
    parser.add_argument("--generate-dashboard", action="store_true", help="Generate quality dashboard after evaluation")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        logger.error("Missing dependencies")
        return 1
    
    # Load trained assets
    logger.info(f"Loading trained assets for {args.game}...")
    assets = load_trained_assets(
        game=args.game,
        embeddings_path=Path(args.embeddings) if args.embeddings else None,
        pairs_path=Path(args.pairs) if args.pairs else None,
        fast_mode=args.fast,
        disable_functional=args.disable_functional,
        disable_text_embed=args.disable_text_embed,
    )
    
    if not assets["fusion"]:
        logger.error("Cannot evaluate without fusion (need embeddings and graph)")
        return 1
    
    # OPTIMIZATION: Auto-detect AWS/runctl environment
    is_aws = args.use_runctl or Path("/mnt/data").exists() or os.getenv("AWS_EXECUTION_ENV") is not None
    if is_aws:
        logger.info("Detected AWS/runctl environment - using optimized paths")
        # Prefer EBS volume paths
        if args.pairs and not str(args.pairs).startswith("/mnt/data"):
            from ml.utils.paths import PATHS
            ebs_pairs = Path("/mnt/data") / PATHS.pairs_large.relative_to(PATHS.data)
            if ebs_pairs.exists():
                logger.info(f"Using EBS volume pairs: {ebs_pairs}")
                args.pairs = str(ebs_pairs)
    
    # Load test data - handle S3 paths
    def load_from_path(file_path: str | Path) -> Path:
        """Load file from local path or S3, return local Path."""
        path = Path(file_path) if isinstance(file_path, str) else file_path
        
        # If S3 path, download first
        if str(path).startswith("s3://"):
            logger.info(f"Downloading from S3: {path}")
            import boto3
            s3 = boto3.client("s3")
            s3_path = str(path).replace("s3://", "")
            bucket, key = s3_path.split("/", 1)
            local_path = Path("/tmp") / Path(key).name
            s3.download_file(bucket, key, str(local_path))
            return local_path
        return path
    
    test_decks: list[dict] = []
    if args.test_decks:
        test_decks_path = load_from_path(args.test_decks)
        if test_decks_path.exists():
            with open(test_decks_path) as f:
                for line in f:
                    if line.strip():
                        test_decks.append(json.loads(line))
            logger.info(f"Loaded {len(test_decks)} test decks")
    
    test_substitutions: list[tuple[str, str]] = []
    if args.test_substitutions:
        sub_path = load_from_path(args.test_substitutions)
        if sub_path.exists():
            with open(sub_path) as f:
                data = json.load(f)
                
                # Handle unified test set format: {"queries": {"card_name": {"highly_relevant": [...], ...}}}
                if isinstance(data, dict) and "queries" in data:
                    queries = data["queries"]
                    for query_card, labels in queries.items():
                        if isinstance(labels, dict):
                            # Extract highly_relevant and relevant cards as substitution targets
                            highly_relevant = labels.get("highly_relevant", [])
                            relevant = labels.get("relevant", [])
                            # Create pairs: (query, target) where target should be substitutable
                            for target in (highly_relevant + relevant)[:3]:  # Up to 3 pairs per query
                                if target and query_card:
                                    test_substitutions.append((query_card, target))
                
                # Handle list format: [[card1, card2], ...] or [{"original": "...", "target": "..."}, ...]
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, list) and len(item) >= 2:
                            test_substitutions.append((item[0], item[1]))
                        elif isinstance(item, dict):
                            orig = item.get("original", item.get("query", ""))
                            targ = item.get("target", item.get("substitute", ""))
                            if orig and targ:
                                test_substitutions.append((orig, targ))
                
                # Handle dict format without "queries" key: {"card_name": {"target": "...", ...}}
                elif isinstance(data, dict):
                    for query_card, labels in data.items():
                        if isinstance(labels, dict):
                            orig = labels.get("original", query_card)
                            targ = labels.get("target", labels.get("substitute", ""))
                            if orig and targ:
                                test_substitutions.append((orig, targ))
            
            logger.info(f"Loaded {len(test_substitutions)} test substitution pairs")
    
    # OPTIMIZATION: Auto-detect if we should recommend runctl for large evaluations
    test_pairs_count = len(test_substitutions) if test_substitutions else 0
    is_aws = args.use_runctl or Path("/mnt/data").exists() or os.getenv("AWS_EXECUTION_ENV") is not None
    
    if test_pairs_count > args.min_pairs_for_runctl:
        logger.warning(f"Large evaluation detected ({test_pairs_count} pairs)")
        logger.warning(f"   Consider using runctl on AWS for faster execution:")
        logger.warning(f"   ./scripts/evaluation/validate_e2e_runctl.sh --game {args.game}")
        if not args.use_runctl and not is_aws:
            logger.warning(f"   Or add --use-runctl flag to enable AWS optimizations")
    
    test_contextual: list[dict] = []
    if args.test_contextual:
        ctx_path = load_from_path(args.test_contextual)
        if ctx_path.exists():
            with open(ctx_path) as f:
                data = json.load(f)
                if isinstance(data, list):
                    test_contextual = data
            logger.info(f"Loaded {len(test_contextual)} test contextual queries")
    
    # Run evaluations
    results: dict[str, Any] = {
        "game": args.game,
        "tasks": {},
    }
    
    # Deck completion
    if test_decks:
        logger.info("\n" + "="*70)
        logger.info("TASK 1: DECK COMPLETION")
        logger.info("="*70)
        comp_results = evaluate_deck_completion_task(assets, test_decks, game=args.game)
        results["tasks"]["completion"] = comp_results
    
    # Deck refinement
    if test_decks:
        logger.info("\n" + "="*70)
        logger.info("TASK 2: DECK REFINEMENT")
        logger.info("="*70)
        ref_results = evaluate_deck_refinement_task(assets, test_decks, game=args.game)
        results["tasks"]["refinement"] = ref_results
    
    # Substitution
    if test_substitutions:
        logger.info("\n" + "="*70)
        logger.info("TASK 3: CARD SUBSTITUTION")
        logger.info("="*70)
        sub_results = evaluate_substitution_task(assets, test_substitutions, game=args.game)
        results["tasks"]["substitution"] = sub_results
    
    # Contextual discovery
    if test_contextual:
        logger.info("\n" + "="*70)
        logger.info("TASK 4: CONTEXTUAL DISCOVERY")
        logger.info("="*70)
        ctx_results = evaluate_contextual_discovery_task(assets, test_contextual, game=args.game)
        results["tasks"]["contextual_discovery"] = ctx_results
    
    # Critique
    logger.info("\n" + "="*70)
    logger.info("PERFORMANCE CRITIQUE")
    logger.info("="*70)
    critique = critique_performance(results["tasks"], args.game)
    results["critique"] = critique
    
    # Print summary
    logger.info("\n" + "="*70)
    logger.info("SUMMARY")
    logger.info("="*70)
    logger.info(f"Overall: {critique['overall_assessment']}")
    if critique["strengths"]:
        logger.info("\nStrengths:")
        for s in critique["strengths"]:
            logger.info(f"  + {s}")
    if critique["weaknesses"]:
        logger.info("\nWeaknesses:")
        for w in critique["weaknesses"]:
            logger.info(f"  - {w}")
    if critique["recommendations"]:
        logger.info("\nRecommendations:")
        for r in critique["recommendations"]:
            logger.info(f"  → {r}")
    
    # Save results - handle S3 output
    output_path = Path(args.output)
    local_output_path = output_path
    
    # If S3 path, save locally first then upload
    if str(output_path).startswith("s3://"):
        import boto3
        s3 = boto3.client("s3")
        local_output_path = Path("/tmp") / Path(output_path.name)
        local_output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_output_path, "w") as f:
            json.dump(results, f, indent=2)
        
        # Upload to S3
        s3_path = str(output_path).replace("s3://", "")
        bucket, key = s3_path.split("/", 1)
        s3.upload_file(str(local_output_path), bucket, key)
        logger.info(f"\nResults saved to S3: {output_path}")
        logger.info(f"  Local copy: {local_output_path}")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"\nResults saved to {output_path}")
    
    # Run deck quality validation if requested
    if args.validate_deck_quality:
        try:
            from ml.evaluation.deck_quality_validation import validate_deck_completion
            from ml.evaluation.similarity_helper import create_similarity_function_from_env
            
            logger.info("\n" + "="*70)
            logger.info("DECK QUALITY VALIDATION")
            logger.info("="*70)
            
            # Create similarity function from assets
            similarity_fn = None
            if assets.get("fusion"):
                # Use fusion for similarity
                fusion = assets["fusion"]
                def sim_fn(query: str, k: int) -> list[tuple[str, float]]:
                    try:
                        results = fusion.similar(query, k, task_type="substitution")
                        return [(card, float(score)) for card, score in results]
                    except Exception as e:
                        logger.warning(f"Similarity lookup failed for {query}: {e}")
                        return []
                similarity_fn = sim_fn
            
            if similarity_fn:
                quality_results = validate_deck_completion(
                    game=args.game,
                    num_test_cases=10,
                    similarity_fn=similarity_fn,
                )
                results["deck_quality_validation"] = quality_results
                logger.info(f"Deck quality validation: {quality_results['success_rate']*100:.1f}% success rate")
            else:
                logger.warning("Cannot run deck quality validation: similarity function not available")
        except Exception as e:
            logger.warning(f"Deck quality validation failed: {e}")
    
    # Generate quality dashboard if requested
    if args.generate_dashboard:
        try:
            from ml.evaluation.quality_dashboard import compute_system_health, generate_dashboard_html
            
            logger.info("\n" + "="*70)
            logger.info("GENERATING QUALITY DASHBOARD")
            logger.info("="*70)
            
            # Create dashboard from evaluation results
            dashboard_path = local_output_path.parent / f"{local_output_path.stem}_dashboard.html"
            health = compute_system_health(
                completion_validation_path=local_output_path if args.validate_deck_quality else None,
                evaluation_results_path=local_output_path,
            )
            generate_dashboard_html(health, dashboard_path)
            logger.info(f"Quality dashboard: {dashboard_path}")
        except Exception as e:
            logger.warning(f"Quality dashboard generation failed: {e}")
    
    # Register evaluation in registry (if available)
    try:
        try:
            from ml.utils.evaluation_registry import EvaluationRegistry
        except ImportError:
            from ..utils.evaluation_registry import EvaluationRegistry
        
        # Extract version from output path or use timestamp
        version = None
        if "_v" in local_output_path.stem:
            version = local_output_path.stem.split("_v")[-1]
        else:
            version = datetime.now().strftime("%Y-W%V")
        
        # Determine model path from embedding argument
        model_path = None
        if args.embedding:
            model_path = str(args.embedding)
        elif args.gnn_model:
            model_path = str(args.gnn_model)
        elif args.cooccurrence_embeddings:
            model_path = str(args.cooccurrence_embeddings)
        else:
            model_path = "downstream_evaluation"
        
        registry = EvaluationRegistry()
        registry.record_evaluation(
            model_type="downstream",
            model_version=version,
            model_path=model_path,
            evaluation_results=results,
            test_set_path=str(args.test_set) if args.test_set else None,
            metadata={
                "game": args.game,
                "test_decks": str(args.test_decks) if args.test_decks else None,
                "test_substitutions": str(args.test_substitutions) if args.test_substitutions else None,
                "test_contextual": str(args.test_contextual) if args.test_contextual else None,
            },
        )
        logger.info(f"✓ Evaluation registered in model registry (version: {version})")
    except Exception as e:
        # Don't fail evaluation if registry fails
        logger.warning(f"Failed to register evaluation in registry: {e}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


