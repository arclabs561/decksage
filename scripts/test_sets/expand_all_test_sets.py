#!/usr/bin/env python3
"""
Expand test sets for Pokemon, Yugioh, and Riftbound to reach 100+ queries each.

Uses the hybrid LLM + human annotation approach:
1. LLM generates candidate queries
2. Human reviews and selects best queries
3. Human annotates relevance labels
4. Merges into unified test sets
"""

import sys
from pathlib import Path


# Add src to path
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import argparse
import json
import logging
import shutil
import time
from typing import Any


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def check_dependencies() -> tuple[bool, list[str]]:
    """Check if all required dependencies are available."""
    missing = []

    # Check for pydantic-ai
    try:
        import pydantic_ai  # noqa: F401
    except ImportError:
        missing.append("pydantic-ai (install: pip install pydantic-ai or uv add pydantic-ai)")

    # Check for required modules
    required_modules = [
        ("ml.scripts.expand_test_set_with_llm", "expand_test_set_with_llm.py"),
        ("ml.scripts.generate_labels_multi_judge", "generate_labels_multi_judge.py"),
    ]

    for module_name, file_name in required_modules:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(f"{file_name} (module not found: {module_name})")

    return len(missing) == 0, missing


def get_current_test_set_size(test_set_path: Path) -> int:
    """Get current number of queries in test set."""
    if not test_set_path.exists():
        return 0

    try:
        with open(test_set_path) as f:
            data = json.load(f)
            queries = data.get("queries", data)
            return len(queries) if isinstance(queries, dict) else 0
    except Exception as e:
        logger.warning(f"Error reading {test_set_path}: {e}")
        return 0


def validate_expanded_test_set(test_set_path: Path, game: str) -> dict[str, Any]:
    """Validate expanded test set quality."""
    if not test_set_path.exists():
        return {
            "valid": False,
            "error": "Test set file does not exist",
        }

    try:
        with open(test_set_path) as f:
            data = json.load(f)

        queries = data.get("queries", data) if isinstance(data, dict) else data
        if not isinstance(queries, dict):
            return {
                "valid": False,
                "error": "Invalid test set format: queries must be a dict",
            }

        # Check basic structure
        if len(queries) == 0:
            return {
                "valid": False,
                "error": "Test set is empty",
            }

        # Check quality metrics
        total_labels = 0
        queries_with_labels = 0
        iaa_scores = []

        for query_name, labels in queries.items():
            if not isinstance(labels, dict):
                continue

            # Count labels
            query_labels = sum(
                len(labels.get(level, []))
                for level in [
                    "highly_relevant",
                    "relevant",
                    "somewhat_relevant",
                    "marginally_relevant",
                ]
            )

            if query_labels > 0:
                queries_with_labels += 1
                total_labels += query_labels

            # Check IAA if available
            if "iaa" in labels and isinstance(labels["iaa"], dict):
                agreement = labels["iaa"].get("agreement_rate")
                if agreement is not None:
                    iaa_scores.append(agreement)

        avg_labels = total_labels / len(queries) if queries else 0
        avg_iaa = sum(iaa_scores) / len(iaa_scores) if iaa_scores else None

        warnings = []
        if avg_labels < 5:
            warnings.append(f"Low average labels per query: {avg_labels:.1f} (target: 5+)")
        if avg_iaa is not None and avg_iaa < 0.7:
            warnings.append(f"Low average IAA: {avg_iaa:.2f} (target: 0.7+)")
        if queries_with_labels < len(queries) * 0.9:
            warnings.append(f"Only {queries_with_labels}/{len(queries)} queries have labels")

        return {
            "valid": True,
            "num_queries": len(queries),
            "queries_with_labels": queries_with_labels,
            "avg_labels_per_query": avg_labels,
            "avg_iaa": avg_iaa,
            "warnings": warnings,
        }
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "error": f"Invalid JSON: {e}",
        }
    except Exception as e:
        return {
            "valid": False,
            "error": f"Validation error: {e}",
        }


def estimate_cost(num_queries: int, num_judges: int, game: str) -> dict[str, Any]:
    """Estimate API costs for expansion."""
    # Rough estimates based on typical usage
    # These are conservative estimates - actual costs may vary
    queries_per_dollar = 100  # Approximate cost for query generation
    judges_per_dollar = 50  # Approximate cost for labeling (per judge)

    query_cost = num_queries / queries_per_dollar
    judge_cost = (num_queries * num_judges) / judges_per_dollar
    total_cost = query_cost + judge_cost

    warnings = []
    if total_cost > 10.0:
        warnings.append("High cost - consider reducing batch size or number of judges")
    elif total_cost > 5.0:
        warnings.append("Moderate cost - expansion may take 30-60 minutes")

    return {
        "estimated_cost_usd": total_cost,
        "query_generation_cost": query_cost,
        "labeling_cost": judge_cost,
        "warnings": warnings,
        "estimated_time_minutes": num_queries * 2,  # Rough estimate: 2 min per query
    }


def expand_test_set_for_game(
    game: str,
    test_set_path: Path,
    target_size: int = 100,
    num_judges: int = 3,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Expand test set for a specific game using LLM generation."""
    current_size = get_current_test_set_size(test_set_path)
    needed = max(0, target_size - current_size)

    if needed == 0:
        logger.info(f"{game}: Already has {current_size} queries (target: {target_size})")
        return {
            "game": game,
            "current_size": current_size,
            "target_size": target_size,
            "needed": 0,
            "status": "complete",
        }

    logger.info(f"{game}: Current: {current_size}, Target: {target_size}, Need: {needed}")

    # Estimate cost
    cost_estimate = estimate_cost(needed + 10, num_judges, game)  # +10 for filtering overhead
    logger.info(f"{game}: Estimated cost: ${cost_estimate['estimated_cost_usd']:.2f}")
    logger.info(f"{game}: Estimated time: {cost_estimate['estimated_time_minutes']:.0f} minutes")
    if cost_estimate["warnings"]:
        for warning in cost_estimate["warnings"]:
            logger.warning(f"{game}: {warning}")

    if dry_run:
        return {
            "game": game,
            "current_size": current_size,
            "target_size": target_size,
            "needed": needed,
            "status": "dry_run",
            "cost_estimate": cost_estimate,
        }

    # Create backup before modification
    backup_path = None
    if test_set_path.exists():
        backup_path = test_set_path.with_suffix(f".backup_{int(time.time())}.json")
        try:
            shutil.copy2(test_set_path, backup_path)
            logger.info(f"{game}: Created backup: {backup_path}")
        except Exception as e:
            logger.error(f"{game}: Failed to create backup: {e}")
            return {
                "game": game,
                "current_size": current_size,
                "target_size": target_size,
                "needed": needed,
                "status": "error",
                "error": f"Backup failed: {e}",
            }

    # Use temporary file for expansion
    temp_path = test_set_path.with_suffix(".tmp.json")

    try:
        from ml.scripts.expand_test_set_with_llm import expand_test_set

        result = expand_test_set(
            existing_test_set_path=test_set_path,
            output_path=temp_path,  # Write to temp first
            num_new_queries=needed + 10,  # Generate extra to account for filtering
            num_judges=num_judges,
            batch_size=10,
            parallel_judges=True,
            game=game,
        )

        # Validate before replacing
        validation = validate_expanded_test_set(temp_path, game)
        if not validation["valid"]:
            error_msg = validation.get("error", "Unknown validation error")
            logger.error(f"{game}: Validation failed: {error_msg}")
            # Restore from backup if available
            if backup_path and backup_path.exists():
                logger.info(f"{game}: Restoring from backup...")
                shutil.copy2(backup_path, test_set_path)
            return {
                "game": game,
                "current_size": current_size,
                "target_size": target_size,
                "needed": needed,
                "status": "error",
                "error": f"Validation failed: {error_msg}",
                "validation": validation,
            }

        # Log validation warnings
        if validation.get("warnings"):
            for warning in validation["warnings"]:
                logger.warning(f"{game}: {warning}")

        # Atomic replace
        temp_path.replace(test_set_path)
        logger.info(f"{game}: Successfully updated test set")

        new_size = get_current_test_set_size(test_set_path)
        logger.info(f"{game}: Expanded to {new_size} queries")

        return {
            "game": game,
            "current_size": current_size,
            "target_size": target_size,
            "needed": needed,
            "new_queries": result.get("new_queries", 0),
            "successfully_labeled": result.get("successfully_labeled", 0),
            "final_size": new_size,
            "status": "success" if new_size >= target_size else "partial",
            "validation": validation,
            "cost_estimate": cost_estimate,
        }
    except ImportError as e:
        error_msg = str(e)
        logger.error(f"{game}: Missing dependencies")
        logger.error("  Required: pydantic-ai")
        logger.error("  Install: pip install pydantic-ai or uv add pydantic-ai")
        logger.error("  Check: src/ml/scripts/expand_test_set_with_llm.py exists")

        # Restore from backup if available
        if backup_path and backup_path.exists():
            logger.info(f"{game}: Restoring from backup...")
            shutil.copy2(backup_path, test_set_path)

        return {
            "game": game,
            "current_size": current_size,
            "target_size": target_size,
            "needed": needed,
            "status": "error",
            "error": "missing_dependencies",
            "error_details": error_msg,
            "fix": "install_dependencies",
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"{game}: Expansion failed: {e}")
        logger.error("  Check logs above for details")
        logger.error(f"  Try: --num-judges {max(1, num_judges - 1)} to reduce load")
        logger.error(f"  Try: --target-size {current_size + (needed // 2)} to reduce batch size")

        # Restore from backup if available
        if backup_path and backup_path.exists():
            logger.info(f"{game}: Restoring from backup...")
            shutil.copy2(backup_path, test_set_path)

        return {
            "game": game,
            "current_size": current_size,
            "target_size": target_size,
            "needed": needed,
            "status": "error",
            "error": error_msg,
            "suggestion": "reduce_batch_size_or_judges",
        }
    finally:
        # Clean up temp file if it still exists
        if temp_path.exists():
            temp_path.unlink()


def main() -> int:
    """Expand all test sets to 100+ queries."""
    parser = argparse.ArgumentParser(
        description="Expand test sets for Pokemon, Yugioh, and Riftbound"
    )
    parser.add_argument(
        "--games",
        nargs="+",
        choices=["pokemon", "yugioh", "riftbound", "all"],
        default=["all"],
        help="Games to expand (default: all)",
    )
    parser.add_argument(
        "--target-size",
        type=int,
        default=100,
        help="Target number of queries per game (default: 100)",
    )
    parser.add_argument(
        "--num-judges",
        type=int,
        default=3,
        help="Number of judges per query for IAA (default: 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually expanding",
    )

    args = parser.parse_args()

    # Check dependencies first
    logger.info("Checking dependencies...")
    deps_ok, missing_deps = check_dependencies()
    if not deps_ok and not args.dry_run:
        logger.error("Missing required dependencies:")
        for dep in missing_deps:
            logger.error(f"  - {dep}")
        logger.error("")
        logger.error("Install dependencies:")
        logger.error("  pip install pydantic-ai")
        logger.error("  or")
        logger.error("  uv add pydantic-ai")
        logger.error("")
        logger.error("Or run with --dry-run to see what would be done without dependencies")
        return 1
    elif not deps_ok and args.dry_run:
        logger.warning("Missing dependencies (dry-run mode, continuing):")
        for dep in missing_deps:
            logger.warning(f"  - {dep}")
    else:
        logger.info("✓ All dependencies available")

    # Try to import PATHS, but don't fail if dependencies are missing
    try:
        from ml.utils.paths import PATHS
    except (ImportError, ModuleNotFoundError) as e:
        logger.warning(f"Could not import PATHS utility: {e}")
        logger.warning("Using fallback paths")

        # Create a simple PATHS-like object for fallback
        class FallbackPaths:
            test_pokemon = Path("experiments/test_set_unified_pokemon.json")
            test_yugioh = Path("experiments/test_set_unified_yugioh.json")

        PATHS = FallbackPaths()

    # Map games to test set paths
    game_map = {
        "pokemon": PATHS.test_pokemon
        if hasattr(PATHS, "test_pokemon")
        else Path("experiments/test_set_unified_pokemon.json"),
        "yugioh": PATHS.test_yugioh
        if hasattr(PATHS, "test_yugioh")
        else Path("experiments/test_set_unified_yugioh.json"),
        "riftbound": Path("experiments/test_set_unified_riftbound.json"),
    }

    if "all" in args.games:
        games_to_expand = ["pokemon", "yugioh", "riftbound"]
    else:
        games_to_expand = args.games

    logger.info("=" * 60)
    logger.info("Test Set Expansion")
    logger.info("=" * 60)
    logger.info(f"Target size: {args.target_size} queries per game")
    logger.info(f"Games: {', '.join(games_to_expand)}")
    logger.info("")

    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        logger.info("")

    results = {}

    for game in games_to_expand:
        test_set_path = game_map.get(game)
        if not test_set_path:
            logger.warning(f"{game}: Test set path not found, skipping")
            continue

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Expanding {game.upper()} test set")
        logger.info(f"{'=' * 60}")

        result = expand_test_set_for_game(
            game=game,
            test_set_path=test_set_path,
            target_size=args.target_size,
            num_judges=args.num_judges,
            dry_run=args.dry_run,
        )
        results[game] = result

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Expansion Summary")
    logger.info("=" * 60)

    for game, result in results.items():
        status = result.get("status", "unknown")
        current = result.get("current_size", 0)
        target = result.get("target_size", 100)
        final = result.get("final_size", current)

        if status == "complete":
            logger.info(f"✓ {game}: {final}/{target} queries (complete)")
        elif status == "success":
            logger.info(f"✓ {game}: {current} → {final}/{target} queries (success)")
            # Show validation results if available
            validation = result.get("validation", {})
            if validation.get("valid"):
                logger.info(
                    f"  Validation: {validation.get('avg_labels_per_query', 0):.1f} avg labels/query"
                )
                if validation.get("avg_iaa") is not None:
                    logger.info(f"  IAA: {validation.get('avg_iaa', 0):.2f}")
        elif status == "partial":
            logger.info(f"⚠ {game}: {current} → {final}/{target} queries (partial)")
            # Show validation warnings
            validation = result.get("validation", {})
            if validation.get("warnings"):
                for warning in validation["warnings"]:
                    logger.warning(f"  {warning}")
        elif status == "error":
            error = result.get("error", "unknown error")
            logger.error(f"✗ {game}: Failed - {error}")
            if result.get("fix"):
                logger.info(f"  Fix: {result.get('fix')}")
            if result.get("suggestion"):
                logger.info(f"  Suggestion: {result.get('suggestion')}")
        elif status == "dry_run":
            needed = result.get("needed", 0)
            cost = result.get("cost_estimate", {})
            logger.info(f"  {game}: {current}/{target} queries (would generate {needed})")
            if cost:
                logger.info(f"    Estimated cost: ${cost.get('estimated_cost_usd', 0):.2f}")
                logger.info(
                    f"    Estimated time: {cost.get('estimated_time_minutes', 0):.0f} minutes"
                )

    # Check if all targets met
    all_complete = all(
        r.get("status") in ["complete", "success"]
        and r.get("final_size", r.get("current_size", 0)) >= args.target_size
        for r in results.values()
    )

    if all_complete:
        logger.info("")
        logger.info("✓ All test sets expanded to target size!")
        return 0
    else:
        logger.info("")
        logger.info("⚠ Some test sets need more expansion")
        return 1


if __name__ == "__main__":
    sys.exit(main())
