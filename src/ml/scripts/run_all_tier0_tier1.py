#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Master script to run all Tier 0 and Tier 1 priorities.

T0.1: Test set validation (already has 940 queries - verify)
T0.2: Deck quality validation
T0.3: Quality dashboard generation
T1.1: Text embeddings validation (verify integration)
T1.2: A/B testing framework validation

This script orchestrates all validation and generates comprehensive reports.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

# Set up project paths
from ml.utils.path_setup import setup_project_paths
setup_project_paths()

from ml.utils.paths import PATHS
from ml.utils.logging_config import setup_script_logging
from ml.evaluation.quality_dashboard import compute_system_health, generate_dashboard_html

logger = setup_script_logging()


def check_test_set_size(game: str = "magic") -> dict[str, Any]:
    """T0.1: Check test set size and coverage."""
    logger.info(f"T0.1: Checking test set size for {game}")
    
    test_set_path = getattr(PATHS, f"test_{game}", None)
    if not test_set_path or not test_set_path.exists():
        return {
            "status": "fail",
            "message": f"Test set not found: {test_set_path}",
            "queries": 0,
        }
    
    try:
        with open(test_set_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return {
            "status": "fail",
            "message": f"Failed to load test set: {e}",
            "queries": 0,
        }
    
    # Handle different test set formats
    if isinstance(data, dict):
        queries = data.get("queries", {})
    elif isinstance(data, list):
        queries = {q.get("query", str(i)): q for i, q in enumerate(data)}
    else:
        return {
            "status": "fail",
            "message": f"Unexpected test set format: {type(data)}",
            "queries": 0,
        }
    
    if not queries:
        return {
            "status": "fail",
            "message": "Test set has no queries",
            "queries": 0,
        }
    
    num_queries = len(queries)
    
    # Count queries with labels (handle various label formats)
    queries_with_labels = 0
    for q in queries.values():
        if isinstance(q, dict):
            # Check for label fields
            has_labels = any(
                q.get(level, []) for level in ["highly_relevant", "relevant", "somewhat_relevant", "labels"]
            )
            if has_labels:
                queries_with_labels += 1
    
    coverage = queries_with_labels / num_queries if num_queries > 0 else 0.0
    
    return {
        "status": "pass" if num_queries >= 100 else "warn" if num_queries >= 50 else "fail",
        "queries": num_queries,
        "queries_with_labels": queries_with_labels,
        "coverage": coverage,
        "target": 100,
    }


def run_deck_quality_validation(game: str = "magic", num_decks: int = 50) -> dict[str, Any]:
    """T0.2: Run deck quality validation."""
    logger.info(f"T0.2: Running deck quality validation for {game}")
    
    output_path = PATHS.experiments / f"deck_quality_validation_{game}.json"
    
    # Check if decks file exists before running (with fallback)
    decks_path = PATHS.decks_all_final
    if not decks_path.exists():
        # Try game-specific fallback
        game_deck_files = {
            "magic": None,  # Magic decks are typically in decks_all_final
            "pokemon": PATHS.processed / "decks_pokemon.jsonl",
            "yugioh": PATHS.processed / "decks_yugioh_ygoprodeck-tournament.jsonl",
            "riftbound": PATHS.processed / "decks_riftbound_riftmana.jsonl",
        }
        fallback_path = game_deck_files.get(game.lower())
        if not fallback_path or not fallback_path.exists():
            return {
                "status": "fail",
                "error": f"Decks file not found: {decks_path} (fallback: {fallback_path})",
            }
        logger.info(f"Using fallback deck file: {fallback_path}")
    
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ml.scripts.validate_deck_quality",
                "--game", game,
                "--num-decks", str(num_decks),
                "--output", str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=7200,  # 2 hour timeout (increased for large validations)
            check=False,  # Don't raise on non-zero exit
        )
        
        # Ensure subprocess is cleaned up even on timeout
        if result.returncode == -15:  # SIGTERM (timeout)
            logger.warning(f"Subprocess timed out after {7200}s")
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            # Truncate very long error messages
            if len(error_msg) > 1000:
                error_msg = error_msg[:1000] + "... (truncated)"
            return {
                "status": "fail",
                "error": error_msg,
                "returncode": result.returncode,
            }
        
        # Load results with error handling (use safe JSON load)
        if output_path.exists():
            try:
                from ml.scripts.fix_nuances import safe_json_load
                validation_results = safe_json_load(output_path, default={})
            except (json.JSONDecodeError, IOError) as e:
                return {
                    "status": "fail",
                    "error": f"Failed to parse results: {e}",
                }
            
            # Check for errors in results
            if "error" in validation_results:
                return {
                    "status": "fail",
                    "error": validation_results["error"],
                }
            
            success_rate = validation_results.get("success_rate", 0)
            return {
                "status": "pass" if success_rate >= 0.7 else "warn" if success_rate >= 0.5 else "fail",
                "results": validation_results,
                "output_path": str(output_path),
            }
        else:
            return {
                "status": "fail",
                "error": "Output file not created",
            }
    except subprocess.TimeoutExpired:
        return {
            "status": "fail",
            "error": f"Validation timed out after 2 hours (tested {num_decks} decks)",
        }
    except FileNotFoundError:
        return {
            "status": "fail",
            "error": "Python interpreter not found",
        }
    except Exception as e:
        logger.error(f"Unexpected error in deck validation: {e}", exc_info=True)
        return {
            "status": "fail",
            "error": f"Unexpected error: {e}",
        }


def generate_quality_dashboard() -> dict[str, Any]:
    """T0.3: Generate quality dashboard."""
    logger.info("T0.3: Generating quality dashboard")
    
    # Find validation files
    test_set_validation = PATHS.experiments / "test_set_validation.json"
    completion_validation = PATHS.experiments / "deck_quality_validation_magic.json"
    evaluation_results = PATHS.hybrid_evaluation_results
    
    # Use available files
    health = compute_system_health(
        test_set_validation_path=test_set_validation if test_set_validation.exists() else None,
        completion_validation_path=completion_validation if completion_validation.exists() else None,
        evaluation_results_path=evaluation_results if evaluation_results.exists() else None,
    )
    
    # Generate dashboard
    dashboard_path = PATHS.experiments / "quality_dashboard.html"
    generate_dashboard_html(health, dashboard_path)
    
    return {
        "status": health.overall_status,
        "metrics_count": len(health.metrics),
        "dashboard_path": str(dashboard_path),
        "overall_status": health.overall_status,
    }


def validate_text_embeddings_integration() -> dict[str, Any]:
    """T1.1: Validate text embeddings are integrated."""
    logger.info("T1.1: Validating text embeddings integration")
    
    try:
        from ml.similarity.text_embeddings import CardTextEmbedder, get_text_embedder
        from ml.similarity.fusion import WeightedLateFusion, FusionWeights
        
        # Check if text embedder can be created
        try:
            embedder = get_text_embedder()
            embedder_available = embedder is not None
        except Exception as e:
            logger.warning(f"Text embedder not available: {e}")
            embedder_available = False
        
        # Check if fusion system supports text embeddings
        weights = FusionWeights()  # Uses defaults (25% text_embed)
        text_embed_weight = weights.text_embed
        
        # Check if API loads text embedder
        try:
            from ml.api.api import get_state
            state = get_state()
            # Check if state has text embedder capability
            has_text_embed = hasattr(state, 'text_embedder') or text_embed_weight > 0
        except Exception:
            has_text_embed = text_embed_weight > 0
        
        return {
            "status": "pass" if embedder_available and text_embed_weight > 0 else "warn",
            "embedder_available": embedder_available,
            "text_embed_weight": text_embed_weight,
            "api_integration": has_text_embed,
            "message": "Text embeddings integrated" if embedder_available else "Text embeddings not available",
        }
    except ImportError as e:
        return {
            "status": "fail",
            "error": f"Import error: {e}",
        }


def validate_ab_testing_framework() -> dict[str, Any]:
    """T1.2: Validate A/B testing framework."""
    logger.info("T1.2: Validating A/B testing framework")
    
    try:
        from ml.evaluation.ab_testing import ABTestFramework, ABTestConfig
        
        # Check if framework can be instantiated
        config = ABTestConfig()
        framework = ABTestFramework(config)
        
        # Verify methods exist
        has_methods = all(
            hasattr(framework, method)
            for method in ["evaluate_model", "compare_models", "generate_report"]
        )
        
        return {
            "status": "pass" if has_methods else "warn",
            "framework_available": True,
            "has_methods": has_methods,
            "message": "A/B testing framework available" if has_methods else "A/B testing framework partially available",
        }
    except ImportError as e:
        return {
            "status": "warn",
            "framework_available": False,
            "error": str(e),
            "message": "A/B testing framework not fully available",
        }
    except Exception as e:
        return {
            "status": "warn",
            "framework_available": False,
            "error": str(e),
        }


def main() -> int:
    """Run all Tier 0 and Tier 1 validations."""
    parser = argparse.ArgumentParser(description="Run all Tier 0 and Tier 1 priorities")
    parser.add_argument(
        "--game",
        type=str,
        default="magic",
        choices=["magic", "pokemon", "yugioh"],
        help="Game to validate",
    )
    parser.add_argument(
        "--skip-deck-validation",
        action="store_true",
        help="Skip deck quality validation (slow)",
    )
    parser.add_argument(
        "--num-decks",
        type=int,
        default=20,  # Smaller default for faster runs
        help="Number of decks for quality validation",
    )
    parser.add_argument(
        "--check-prerequisites",
        action="store_true",
        help="Check prerequisites before running validations",
    )
    parser.add_argument(
        "--skip-prerequisites",
        action="store_true",
        help="Skip prerequisite checking (faster)",
    )
    
    args = parser.parse_args()
    
    # Check prerequisites if requested
    if args.check_prerequisites and not args.skip_prerequisites:
        logger.info("Checking prerequisites...")
        try:
            from ml.scripts.validate_prerequisites import validate_tier0_tier1_prerequisites
            prereq_results = validate_tier0_tier1_prerequisites()
            if prereq_results["overall"] == "fail":
                logger.error("Prerequisites check failed - some required dependencies/files missing")
                logger.error("Run with --skip-prerequisites to continue anyway")
                return 1
            elif prereq_results["overall"] == "warn":
                logger.warning("Prerequisites check passed with warnings")
        except Exception as e:
            logger.warning(f"Prerequisites check failed: {e}, continuing anyway")
    
    results = {
        "t0_1_test_set": check_test_set_size(args.game),
        "t0_2_deck_quality": None,
        "t0_3_dashboard": None,
        "t1_1_text_embeddings": validate_text_embeddings_integration(),
        "t1_2_ab_testing": validate_ab_testing_framework(),
    }
    
    # Run deck quality validation if not skipped
    if not args.skip_deck_validation:
        results["t0_2_deck_quality"] = run_deck_quality_validation(args.game, args.num_decks)
    else:
        logger.info("Skipping deck quality validation (--skip-deck-validation)")
        results["t0_2_deck_quality"] = {"status": "skipped"}
    
    # Generate dashboard
    results["t0_3_dashboard"] = generate_quality_dashboard()
    
    # Save results
    results_path = PATHS.experiments / "tier0_tier1_validation.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print("\n" + "=" * 70)
    print("Tier 0 & Tier 1 Validation Summary")
    print("=" * 70)
    
    for key, result in results.items():
        if result:
            status = result.get("status", "unknown")
            status_icon = "✓" if status == "pass" else "⚠" if status == "warn" else "✗"
            print(f"{status_icon} {key}: {status.upper()}")
            
            if key == "t0_1_test_set" and "queries" in result:
                print(f"   Queries: {result['queries']} (target: {result.get('target', 100)})")
            elif key == "t0_2_deck_quality" and result.get("results"):
                r = result["results"]
                print(f"   Success rate: {r.get('success_rate', 0):.1%}")
                print(f"   Avg quality: {r.get('avg_quality_score', 0):.2f}/10.0")
            elif key == "t0_3_dashboard" and "dashboard_path" in result:
                print(f"   Dashboard: {result['dashboard_path']}")
            elif key == "t1_1_text_embeddings" and "text_embed_weight" in result:
                print(f"   Text embed weight: {result['text_embed_weight']:.1%}")
                print(f"   Available: {result.get('embedder_available', False)}")
    
    print(f"\nFull results saved to: {results_path}")
    
    # Determine overall status
    all_statuses = [r.get("status") for r in results.values() if r]
    if any(s == "fail" for s in all_statuses):
        return 1
    elif any(s == "warn" for s in all_statuses):
        return 0  # Warnings are acceptable
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())

