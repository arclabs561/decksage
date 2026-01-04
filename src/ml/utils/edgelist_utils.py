"""Utilities for converting pairs CSV to edgelist format."""

from __future__ import annotations

from pathlib import Path

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def prepare_edgelist(
    csv_file: Path | str,
    output_edg: Path | str,
    min_cooccurrence: int = 2,
) -> tuple[int, int]:
    """
    Convert pairs CSV to edgelist format.
    
    Args:
        csv_file: Path to pairs CSV file
        output_edg: Path to output edgelist file
        min_cooccurrence: Minimum co-occurrence count to include edge
    
    Returns:
        Tuple of (num_nodes, num_edges)
    """
    if not HAS_PANDAS:
        raise ImportError("pandas required: pip install pandas")
    
    csv_file = Path(csv_file)
    output_edg = Path(output_edg)
    
    df = pd.read_csv(csv_file)
    
    # Filter by min_cooccurrence
    if "COUNT_SET" in df.columns:
        df = df[df["COUNT_SET"] >= min_cooccurrence]
    elif "COUNT_MULTISET" in df.columns:
        df = df[df["COUNT_MULTISET"] >= min_cooccurrence]
    else:
        # No count column, include all
        pass
    
    # Write edgelist format: node1\tnode2\tweight
    output_edg.parent.mkdir(parents=True, exist_ok=True)
    with open(output_edg, "w") as f:
        for _, row in df.iterrows():
            card1 = row["NAME_1"]
            card2 = row["NAME_2"]
            weight = row.get("COUNT_MULTISET", row.get("COUNT_SET", 1))
            f.write(f"{card1}\t{card2}\t{weight}\n")
    
    # Count nodes and edges
    num_nodes = len(set(df["NAME_1"]) | set(df["NAME_2"]))
    num_edges = len(df)
    
    return num_nodes, num_edges

