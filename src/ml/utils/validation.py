"""Pre-flight validation utilities for automation scripts."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from .paths import PATHS


try:
    from .logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


def check_file_exists(path: Path | str, description: str = "File") -> bool:
    """Check if a file exists, raise ValidationError if not."""
    path = Path(path)
    if not path.exists():
        raise ValidationError(f"{description} not found: {path}")
    if not path.is_file():
        raise ValidationError(f"{description} is not a file: {path}")
    return True


def check_directory_exists(path: Path | str, description: str = "Directory") -> bool:
    """Check if a directory exists, raise ValidationError if not."""
    path = Path(path)
    if not path.exists():
        raise ValidationError(f"{description} not found: {path}")
    if not path.is_dir():
        raise ValidationError(f"{description} is not a directory: {path}")
    return True


def check_s3_path(path: str) -> bool:
    """Check if S3 path is accessible."""
    if not path.startswith("s3://"):
        return False

    try:
        result = subprocess.run(
            ["s5cmd", "ls", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_instance_status(instance_id: str, runctl_bin: Path | str | None = None) -> dict[str, Any]:
    """Check AWS instance status using runctl."""
    runctl_bin = (
        Path(runctl_bin)
        if runctl_bin
        else PATHS.project_root.parent / "runctl" / "target" / "release" / "runctl"
    )

    if not runctl_bin.exists():
        raise ValidationError(f"runctl not found at {runctl_bin}")

    try:
        result = subprocess.run(
            [str(runctl_bin), "aws", "instances", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise ValidationError(f"Failed to check instance status: {result.stderr}")

        instances = json.loads(result.stdout)
        for inst in instances:
            if inst.get("id") == instance_id:
                return {
                    "exists": True,
                    "state": inst.get("state", "unknown"),
                    "type": inst.get("type", "unknown"),
                    "ready": inst.get("state") == "running",
                }

        return {"exists": False, "state": "not_found", "ready": False}
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        raise ValidationError(f"Error checking instance status: {e}")


def validate_training_prerequisites(
    decks_path: Path | str | None = None,
    pairs_path: Path | str | None = None,
    graph_path: Path | str | None = None,
    instance_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Validate prerequisites for training.

    Returns:
    dict with validation results
    """
    results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "checks": {},
    }

    # Check data files
    if decks_path:
        try:
            check_file_exists(decks_path, "Decks file")
            results["checks"]["decks"] = "✓"
        except ValidationError as e:
            results["errors"].append(str(e))
            results["checks"]["decks"] = "✗"
            results["valid"] = False

    if pairs_path:
        try:
            check_file_exists(pairs_path, "Pairs file")
            results["checks"]["pairs"] = "✓"
        except ValidationError as e:
            results["errors"].append(str(e))
            results["checks"]["pairs"] = "✗"
            results["valid"] = False

    # Check graph (optional, will be created if missing)
    if graph_path:
        graph_path_obj = Path(graph_path)
        if graph_path_obj.exists():
            results["checks"]["graph"] = "✓ (exists)"
        else:
            results["warnings"].append(f"Graph will be created: {graph_path}")
            results["checks"]["graph"] = "⚠ (will create)"

    # Check instance if provided
    if instance_id and not dry_run:
        try:
            status = check_instance_status(instance_id)
            results["checks"]["instance"] = status
            if not status["exists"]:
                results["errors"].append(f"Instance not found: {instance_id}")
                results["valid"] = False
            elif not status["ready"]:
                results["warnings"].append(f"Instance not ready (state: {status['state']})")
        except ValidationError as e:
            results["errors"].append(str(e))
            results["checks"]["instance"] = "✗"
            results["valid"] = False

    return results


def validate_evaluation_prerequisites(
    test_set_path: Path | str,
    gnn_model_path: Path | str | None = None,
    cooccurrence_path: Path | str | None = None,
    graph_path: Path | str | None = None,
    instance_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Validate prerequisites for evaluation.

    Returns:
    dict with validation results
    """
    results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "checks": {},
    }

    # Test set is required
    try:
        check_file_exists(test_set_path, "Test set")
        results["checks"]["test_set"] = "✓"
    except ValidationError as e:
        results["errors"].append(str(e))
        results["checks"]["test_set"] = "✗"
        results["valid"] = False

    # GNN model (optional, will use default if missing)
    if gnn_model_path:
        try:
            check_file_exists(gnn_model_path, "GNN model")
            results["checks"]["gnn_model"] = "✓"
        except ValidationError as e:
            results["warnings"].append(f"{e} (will use default)")
            results["checks"]["gnn_model"] = "⚠"

    # Co-occurrence embeddings (optional)
    if cooccurrence_path:
        try:
            check_file_exists(cooccurrence_path, "Co-occurrence embeddings")
            results["checks"]["cooccurrence"] = "✓"
        except ValidationError as e:
            results["warnings"].append(f"{e} (will use default)")
            results["checks"]["cooccurrence"] = "⚠"

    # Graph (optional, for Jaccard similarity)
    if graph_path:
        graph_path_obj = Path(graph_path)
        if graph_path_obj.exists():
            results["checks"]["graph"] = "✓"
        else:
            results["warnings"].append(
                f"Graph not found: {graph_path} (Jaccard similarity disabled)"
            )
            results["checks"]["graph"] = "⚠"

    # Instance check
    if instance_id and not dry_run:
        try:
            status = check_instance_status(instance_id)
            results["checks"]["instance"] = status
            if not status["exists"]:
                results["errors"].append(f"Instance not found: {instance_id}")
                results["valid"] = False
            elif not status["ready"]:
                results["warnings"].append(f"Instance not ready (state: {status['state']})")
        except ValidationError as e:
            results["errors"].append(str(e))
            results["checks"]["instance"] = "✗"
            results["valid"] = False

    return results


def print_validation_results(results: dict[str, Any], dry_run: bool = False) -> None:
    """Print validation results in a readable format."""
    prefix = "[DRY-RUN] " if dry_run else ""

    print(f"\n{prefix}Validation Results:")
    print("=" * 60)

    for check, status in results["checks"].items():
        if isinstance(status, dict):
            state = status.get("state", "unknown")
            print(f" {check}: {state}")
        else:
            print(f" {check}: {status}")

    if results["warnings"]:
        print("\nWarning: Warnings:")
        for warning in results["warnings"]:
            print(f" • {warning}")

    if results["errors"]:
        print("\nError: Errors:")
        for error in results["errors"]:
            print(f" • {error}")

    if results["valid"]:
        print(f"\n✓ {prefix}Validation passed")
    else:
        print(f"\n✗ {prefix}Validation failed")

    print("=" * 60)
