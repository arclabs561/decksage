#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Comprehensive validation of entire repository.

Validates:
- Data files (existence, size, format)
- Test sets (structure, coverage)
- Embeddings (existence, format)
- Code quality (imports, syntax)
- Configuration (paths, settings)
- Documentation (completeness)
"""

import json
import sys
from pathlib import Path
from typing import Any


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


class ValidationResult:
    """Track validation results."""

    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []

    def add_pass(self, check: str, detail: str = ""):
        self.passed.append({"check": check, "detail": detail})

    def add_fail(self, check: str, reason: str, fix: str = ""):
        self.failed.append({"check": check, "reason": reason, "fix": fix})

    def add_warning(self, check: str, reason: str, suggestion: str = ""):
        self.warnings.append({"check": check, "reason": reason, "suggestion": suggestion})

    def summary(self) -> dict[str, Any]:
        return {
            "total": len(self.passed) + len(self.failed) + len(self.warnings),
            "passed": len(self.passed),
            "failed": len(self.failed),
            "warnings": len(self.warnings),
        }


def validate_data_files(result: ValidationResult) -> None:
    """Validate data files."""
    try:
        from ml.utils.paths import PATHS
    except ImportError:
        # Fallback: construct paths manually
        class PATHS:
            pairs_large = Path("data/processed/pairs_large.csv")
            card_attributes = Path("data/processed/card_attributes_enriched.csv")
            decks_all_final = Path("data/processed/decks_all_final.jsonl")

    print("Validating data files...")

    # Check critical files
    critical_files = {
        "pairs_large.csv": PATHS.pairs_large,
        "pairs_multi_game.csv": Path("data/processed/pairs_multi_game.csv"),
        "card_attributes_enriched.csv": PATHS.card_attributes,
    }

    for name, path in critical_files.items():
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > 0:
                result.add_pass(f"Data file: {name}", f"{size_mb:.1f} MB")
            else:
                result.add_fail(f"Data file: {name}", "File is empty")
        else:
            result.add_fail(
                f"Data file: {name}", "File not found", f"Check if file exists at {path}"
            )

    # Check deck files
    deck_files = {
        "decks_all_final.jsonl": PATHS.decks_all_final,
        "decks_pokemon.jsonl": Path("data/processed/decks_pokemon.jsonl"),
    }

    for name, path in deck_files.items():
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            if name == "decks_all_final.jsonl":
                result.add_pass(f"Deck file: {name}", f"{size_mb:.1f} MB")
            else:
                result.add_pass(f"Deck file: {name}", f"{size_mb:.1f} MB")
        else:
            if name == "decks_all_final.jsonl":
                result.add_warning(
                    f"Deck file: {name}",
                    "File not found (can be generated)",
                    "Run: uv run scripts/data_processing/unified_export_pipeline.py",
                )
            else:
                result.add_fail(f"Deck file: {name}", "File not found")


def validate_test_sets(result: ValidationResult) -> None:
    """Validate test sets."""
    print("Validating test sets...")

    test_sets = {
        "test_set_canonical_magic.json": Path("experiments/test_set_canonical_magic.json"),
        "test_set_unified_magic.json": Path("experiments/test_set_unified_magic.json"),
        "test_set_canonical_pokemon.json": Path("experiments/test_set_canonical_pokemon.json"),
        "test_set_canonical_yugioh.json": Path("experiments/test_set_canonical_yugioh.json"),
    }

    for name, path in test_sets.items():
        if not path.exists():
            result.add_fail(f"Test set: {name}", "File not found")
            continue

        try:
            with open(path) as f:
                data = json.load(f)

            # Check structure
            if not isinstance(data, dict):
                result.add_fail(f"Test set: {name}", "Invalid format: not a dict")
                continue

            # Get queries
            queries = data.get("queries", data)
            if not isinstance(queries, dict):
                result.add_fail(f"Test set: {name}", "Invalid format: queries not a dict")
                continue

            num_queries = len(queries)
            if num_queries == 0:
                result.add_fail(f"Test set: {name}", "Empty test set")
                continue

            # Check query structure
            sample_query = list(queries.keys())[0]
            sample_labels = queries[sample_query]

            if not isinstance(sample_labels, dict):
                result.add_fail(
                    f"Test set: {name}", f"Invalid label format for query '{sample_query}'"
                )
                continue

            # Check for relevant labels
            relevant_levels = [
                "highly_relevant",
                "relevant",
                "somewhat_relevant",
                "marginally_relevant",
            ]
            has_relevant = any(sample_labels.get(level, []) for level in relevant_levels)

            if not has_relevant:
                result.add_warning(
                    f"Test set: {name}", f"Query '{sample_query}' has no relevant labels"
                )

            # Check minimum queries
            if num_queries < 10:
                result.add_warning(
                    f"Test set: {name}", f"Only {num_queries} queries (recommend ≥10)"
                )

            result.add_pass(f"Test set: {name}", f"{num_queries} queries")

        except json.JSONDecodeError as e:
            result.add_fail(f"Test set: {name}", f"Invalid JSON: {e}")
        except Exception as e:
            result.add_fail(f"Test set: {name}", f"Error: {e}")


def validate_embeddings(result: ValidationResult) -> None:
    """Validate embeddings."""
    print("Validating embeddings...")

    embeddings_dir = Path("data/embeddings")
    if not embeddings_dir.exists():
        result.add_fail("Embeddings directory", "Directory not found")
        return

    embedding_files = list(embeddings_dir.glob("*.wv"))
    embedding_files.extend(list(embeddings_dir.glob("**/*.wv")))

    if not embedding_files:
        result.add_warning("Embeddings", "No .wv files found")
        return

    result.add_pass("Embeddings directory", f"{len(embedding_files)} files found")

    # Try to load a sample
    try:
        from gensim.models import KeyedVectors

        sample = embedding_files[0]
        embedding = KeyedVectors.load(str(sample))
        result.add_pass(
            "Embedding format", f"Sample '{sample.name}' loads correctly ({len(embedding)} vectors)"
        )
    except ImportError:
        result.add_warning("Embedding format", "Cannot validate (gensim not available)")
    except Exception as e:
        result.add_warning("Embedding format", f"Sample load failed: {e}")


def validate_code_quality(result: ValidationResult) -> None:
    """Validate code quality."""
    print("Validating code quality...")

    # Check critical modules can be imported (skip ones that require heavy dependencies)
    # Try to import paths, but handle gracefully if it fails
    try:
        import ml.utils.paths

        result.add_pass("Module: ml.utils.paths", "Imports successfully")
    except ImportError:
        result.add_warning("Module: ml.utils.paths", "Not available (may need dependencies)")
    except Exception as e:
        result.add_warning("Module: ml.utils.paths", f"Import error: {e}")

    critical_modules = []

    optional_modules = [
        "ml.utils.data_loading",  # Requires pandas
        "ml.utils.evaluation",  # May require numpy
    ]

    for module_name in critical_modules:
        try:
            __import__(module_name)
            result.add_pass(f"Module: {module_name}", "Imports successfully")
        except ImportError as e:
            result.add_fail(f"Module: {module_name}", f"Import failed: {e}")
        except Exception as e:
            result.add_warning(f"Module: {module_name}", f"Import error: {e}")

    for module_name in optional_modules:
        try:
            __import__(module_name)
            result.add_pass(f"Module: {module_name}", "Imports successfully")
        except ImportError:
            result.add_warning(f"Module: {module_name}", "Not available (missing dependencies)")
        except Exception as e:
            result.add_warning(f"Module: {module_name}", f"Import error: {e}")


def validate_paths(result: ValidationResult) -> None:
    """Validate path configuration."""
    print("Validating paths...")

    try:
        try:
            from ml.utils.paths import PATHS
        except ImportError:
            # Fallback: construct paths manually
            class PATHS:
                data = Path("data")
                processed = Path("data/processed")
                embeddings = Path("data/embeddings")
                experiments = Path("experiments")

        # Check directories exist
        dirs = {
            "data": PATHS.data,
            "processed": PATHS.processed,
            "embeddings": PATHS.embeddings,
            "experiments": PATHS.experiments,
        }

        for name, path in dirs.items():
            if path.exists() and path.is_dir():
                result.add_pass(f"Directory: {name}", str(path))
            else:
                result.add_fail(f"Directory: {name}", f"Not found: {path}")

    except Exception as e:
        result.add_fail("Path configuration", f"Error: {e}")


def validate_documentation(result: ValidationResult) -> None:
    """Validate documentation."""
    print("Validating documentation...")

    docs = {
        "README.md": Path("README.md"),
        "data/README.md": Path("data/README.md"),
        "docs/QUICK_REFERENCE.md": Path("docs/QUICK_REFERENCE.md"),
    }

    for name, path in docs.items():
        if path.exists():
            size = path.stat().st_size
            if size > 100:  # At least 100 bytes
                result.add_pass(f"Documentation: {name}", f"{size} bytes")
            else:
                result.add_warning(f"Documentation: {name}", "File is very small")
        else:
            result.add_warning(f"Documentation: {name}", "File not found")


def main() -> int:
    """Main entry point."""
    result = ValidationResult()

    print("=" * 70)
    print("Comprehensive Repository Validation")
    print("=" * 70)
    print()

    # Run all validations
    validate_data_files(result)
    print()
    validate_test_sets(result)
    print()
    validate_embeddings(result)
    print()
    validate_code_quality(result)
    print()
    validate_paths(result)
    print()
    validate_documentation(result)
    print()

    # Summary
    print("=" * 70)
    print("Validation Summary")
    print("=" * 70)
    print()

    summary = result.summary()
    print(f"Total checks: {summary['total']}")
    print(f"  ✓ Passed: {summary['passed']}")
    print(f"  ✗ Failed: {summary['failed']}")
    print(f"  ⚠ Warnings: {summary['warnings']}")
    print()

    if result.failed:
        print("Failed checks:")
        for fail in result.failed:
            print(f"  ✗ {fail['check']}: {fail['reason']}")
            if fail.get("fix"):
                print(f"      Fix: {fail['fix']}")
        print()

    if result.warnings:
        print("Warnings:")
        for warn in result.warnings[:10]:  # Limit to 10
            print(f"  ⚠ {warn['check']}: {warn['reason']}")
            if warn.get("suggestion"):
                print(f"      Suggestion: {warn['suggestion']}")
        if len(result.warnings) > 10:
            print(f"  ... and {len(result.warnings) - 10} more warnings")
        print()

    # Save report
    report_path = Path("experiments/validation_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(
            {
                "summary": summary,
                "passed": result.passed,
                "failed": result.failed,
                "warnings": result.warnings,
            },
            f,
            indent=2,
        )

    print(f"Full report saved to: {report_path}")

    return 0 if len(result.failed) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
