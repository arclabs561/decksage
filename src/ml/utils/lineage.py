"""
Data lineage validation utilities.

Provides functions to validate data lineage dependencies and enforce rules.
"""

from pathlib import Path


# Order 0 locations (immutable)
ORDER_0_LOCATIONS = [
    "src/backend/data-full/games/",
    "s3://games-collections/games/",
]

# Order definitions
DATA_ORDERS = {
    0: {
        "name": "Primary Source Data",
        "immutable": True,
        "locations": ORDER_0_LOCATIONS,
    },
    1: {
        "name": "Exported Decks",
        "depends_on": [0],
        "locations": ["data/processed/decks_*.jsonl"],
    },
    2: {
        "name": "Co-occurrence Pairs",
        "depends_on": [1],
        "locations": ["data/processed/pairs_*.csv"],
    },
    3: {
        "name": "Incremental Graph",
        "depends_on": [1, 2],
        "locations": ["data/graphs/incremental_graph.db", "data/graphs/incremental_graph.json"],
    },
    4: {
        "name": "Embeddings",
        "depends_on": [2, 3],
        "locations": ["data/embeddings/"],
    },
    5: {
        "name": "Test Sets",
        "depends_on": [1, 4],
        "locations": ["experiments/test_set_unified_*.json"],
    },
    6: {
        "name": "Annotations",
        "depends_on": [1, 4],
        "locations": ["annotations/*.jsonl"],
    },
}


def is_order_0_location(path: str | Path) -> bool:
    """Check if a path is an Order 0 (immutable) location."""
    path_str = str(path)
    return any(
        path_str.startswith(loc.rstrip("/")) or loc.rstrip("/") in path_str
        for loc in ORDER_0_LOCATIONS
    )


def validate_write_path(path: str | Path, order: int) -> tuple[bool, str | None]:
    """
    Validate that a write path is appropriate for the given order.

    Returns:
        (is_valid, error_message)
    """
    path_str = str(path)

    # Order 0 is immutable - never allow writes
    if order == 0:
        return False, f"Cannot write to Order 0 (immutable primary data): {path_str}"

    # Check if trying to write to Order 0 location
    if is_order_0_location(path_str):
        return False, f"Cannot write to Order 0 location (immutable): {path_str}"

    # Check if path matches expected location for order
    order_info = DATA_ORDERS.get(order, {})
    expected_locations = order_info.get("locations", [])

    # For now, just check it's not Order 0
    # Could add stricter validation later
    return True, None


def get_order_for_path(path: str | Path) -> int | None:
    """Infer the order for a given path."""
    path_str = str(path)

    for order, info in DATA_ORDERS.items():
        for location in info.get("locations", []):
            # Simple pattern matching
            if location.replace("*", "") in path_str:
                return order

    return None


def check_dependencies(order: int) -> tuple[bool, list[str]]:
    """
    Check if dependencies for an order are satisfied.

    Returns:
        (all_satisfied, missing_dependencies)
    """
    order_info = DATA_ORDERS.get(order, {})
    depends_on = order_info.get("depends_on", [])

    missing = []
    for dep_order in depends_on:
        dep_info = DATA_ORDERS.get(dep_order, {})
        dep_locations = dep_info.get("locations", [])

        # Check if any dependency location exists
        found = False
        for loc in dep_locations:
            # Remove wildcards for checking
            check_path = Path(loc.replace("*", "").replace("s3://", ""))
            if check_path.exists() or check_path.is_dir():
                found = True
                break

        if not found:
            missing.append(f"Order {dep_order}: {dep_info.get('name', 'Unknown')}")

    return len(missing) == 0, missing


def validate_before_processing(order: int, input_paths: list[Path]) -> tuple[bool, list[str]]:
    """
    Validate that dependencies exist before processing data of a given order.

    Args:
        order: The order being processed
        input_paths: Paths to input files being used

    Returns:
        (is_valid, missing_dependencies)
    """
    # Check dependencies
    all_satisfied, missing = check_dependencies(order)

    # Check that input paths exist
    missing_paths = []
    for path in input_paths:
        if not path.exists() and not str(path).startswith("s3://"):
            missing_paths.append(str(path))

    if missing_paths:
        return False, [f"Missing input files: {missing_paths}"] + missing

    return all_satisfied, missing


def get_lineage_info(order: int) -> dict:
    """Get lineage information for a given order."""
    return DATA_ORDERS.get(order, {})
