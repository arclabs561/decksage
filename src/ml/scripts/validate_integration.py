#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Integration validation for Tier 0 & Tier 1 components.

Validates that all components work together correctly:
1. Prerequisites → Validation → Dashboard
2. Test set → Evaluation → A/B Testing
3. Deck quality → Completion → Quality metrics
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Set up project paths
from ml.utils.path_setup import setup_project_paths
setup_project_paths()

from ml.utils.paths import PATHS
from ml.utils.logging_config import setup_script_logging
from ml.scripts.validate_prerequisites import validate_tier0_tier1_prerequisites
from ml.scripts.run_all_tier0_tier1 import (
    check_test_set_size,
    validate_text_embeddings_integration,
    validate_ab_testing_framework,
    generate_quality_dashboard,
)

logger = setup_script_logging()


def validate_end_to_end_workflow(game: str = "magic") -> dict[str, Any]:
    """Validate complete end-to-end workflow."""
    results = {
        "workflow": "end_to_end",
        "game": game,
        "steps": {},
        "overall": "pass",
    }
    
    # Step 1: Prerequisites
    logger.info("Step 1: Checking prerequisites...")
    prereq_results = validate_tier0_tier1_prerequisites()
    results["steps"]["prerequisites"] = prereq_results
    if prereq_results["overall"] == "fail":
        results["overall"] = "fail"
        return results
    
    # Step 2: Test set validation
    logger.info("Step 2: Validating test set...")
    test_set_results = check_test_set_size(game)
    results["steps"]["test_set"] = test_set_results
    if test_set_results["status"] == "fail":
        results["overall"] = "fail"
        return results
    
    # Step 3: Text embeddings
    logger.info("Step 3: Validating text embeddings...")
    text_embed_results = validate_text_embeddings_integration()
    results["steps"]["text_embeddings"] = text_embed_results
    if text_embed_results["status"] == "fail":
        results["overall"] = "warn"
    
    # Step 4: A/B testing framework
    logger.info("Step 4: Validating A/B testing framework...")
    ab_test_results = validate_ab_testing_framework()
    results["steps"]["ab_testing"] = ab_test_results
    if ab_test_results["status"] == "fail":
        results["overall"] = "warn"
    
    # Step 5: Quality dashboard
    logger.info("Step 5: Generating quality dashboard...")
    try:
        dashboard_results = generate_quality_dashboard()
        results["steps"]["dashboard"] = dashboard_results
    except Exception as e:
        logger.error(f"Dashboard generation failed: {e}")
        results["steps"]["dashboard"] = {"status": "fail", "error": str(e)}
        results["overall"] = "warn"
    
    return results


def validate_component_integration() -> dict[str, Any]:
    """Validate that components integrate correctly."""
    results = {
        "integration": "components",
        "checks": {},
        "overall": "pass",
    }
    
    # Check that paths are consistent
    logger.info("Checking path consistency...")
    try:
        test_set = getattr(PATHS, "test_magic", None)
        decks = PATHS.decks_all_final
        pairs = PATHS.pairs_large
        
        path_checks = {
            "test_set_exists": test_set.exists() if test_set else False,
            "decks_exists": decks.exists() if decks else False,
            "pairs_exists": pairs.exists() if pairs else False,
        }
        
        results["checks"]["paths"] = path_checks
        
        if not any(path_checks.values()):
            results["overall"] = "warn"
    except Exception as e:
        logger.error(f"Path check failed: {e}")
        results["checks"]["paths"] = {"error": str(e)}
        results["overall"] = "warn"
    
    # Check that validation scripts can import each other
    logger.info("Checking script imports...")
    import_checks = {}
    
    try:
        from ml.scripts.validate_deck_quality import validate_deck_quality_batch
        import_checks["validate_deck_quality"] = True
    except Exception as e:
        import_checks["validate_deck_quality"] = False
        import_checks["validate_deck_quality_error"] = str(e)
    
    try:
        from ml.scripts.run_all_tier0_tier1 import check_test_set_size
        import_checks["run_all_tier0_tier1"] = True
    except Exception as e:
        import_checks["run_all_tier0_tier1"] = False
        import_checks["run_all_tier0_tier1_error"] = str(e)
    
    results["checks"]["imports"] = import_checks
    
    if not all(v for k, v in import_checks.items() if k.endswith("_quality") or k.endswith("_tier1")):
        results["overall"] = "warn"
    
    return results


def main() -> int:
    """CLI for integration validation."""
    parser = argparse.ArgumentParser(description="Validate Tier 0 & Tier 1 integration")
    parser.add_argument(
        "--game",
        type=str,
        default="magic",
        choices=["magic", "pokemon", "yugioh"],
        help="Game to validate",
    )
    parser.add_argument(
        "--workflow",
        action="store_true",
        help="Run end-to-end workflow validation",
    )
    parser.add_argument(
        "--components",
        action="store_true",
        help="Run component integration validation",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file (optional)",
    )
    
    args = parser.parse_args()
    
    # Run requested validations
    all_results = {}
    
    if args.workflow or (not args.workflow and not args.components):
        logger.info("Running end-to-end workflow validation...")
        all_results["workflow"] = validate_end_to_end_workflow(args.game)
    
    if args.components or (not args.workflow and not args.components):
        logger.info("Running component integration validation...")
        all_results["components"] = validate_component_integration()
    
    # Save results (use safe JSON write)
    if args.output:
        from ml.scripts.fix_nuances import safe_json_dump
        safe_json_dump(all_results, args.output, indent=2)
        logger.info(f"Results saved to {args.output}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("Integration Validation Summary")
    print("=" * 70)
    
    for name, result in all_results.items():
        overall = result.get("overall", "unknown")
        status_icon = "✓" if overall == "pass" else "⚠" if overall == "warn" else "✗"
        print(f"{status_icon} {name}: {overall.upper()}")
    
    # Determine exit code
    if any(r.get("overall") == "fail" for r in all_results.values()):
        return 1
    elif any(r.get("overall") == "warn" for r in all_results.values()):
        return 0  # Warnings are acceptable
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())

