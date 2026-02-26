"""Tests for blended edgelist merge logic.

Tests the merge of two edgelists with overlapping and non-overlapping edges,
verifying edge counts and weight arithmetic. Tests the pattern used in
scripts/integrate_functional_tags_training.py::merge_functional_edges_into_pairs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _make_pairs_csv(pairs: list[tuple[str, str, int, int]], path: Path) -> None:
    """Write a pairs CSV with NAME_1, NAME_2, COUNT_SET, COUNT_MULTISET columns."""
    df = pd.DataFrame(pairs, columns=["NAME_1", "NAME_2", "COUNT_SET", "COUNT_MULTISET"])
    df.to_csv(path, index=False)


def _merge_edgelists(
    base_csv: Path,
    functional_edges: list[tuple[str, str, float]],
    output_csv: Path,
    functional_weight: float = 3.0,
) -> pd.DataFrame:
    """
    Merge functional similarity edges into a base pairs CSV.

    Mirrors the logic from integrate_functional_tags_training.merge_functional_edges_into_pairs.
    """
    pairs_df = pd.read_csv(base_csv)

    func_df = pd.DataFrame(functional_edges, columns=["NAME_1", "NAME_2", "FUNCTIONAL_SIMILARITY"])

    # Normalize card names (sorted pair key)
    func_df["PAIR_KEY"] = func_df.apply(
        lambda row: tuple(sorted([row["NAME_1"], row["NAME_2"]])), axis=1
    )
    pairs_df["PAIR_KEY"] = pairs_df.apply(
        lambda row: tuple(sorted([row["NAME_1"], row["NAME_2"]])), axis=1
    )

    # Merge
    merged = pairs_df.merge(
        func_df[["PAIR_KEY", "FUNCTIONAL_SIMILARITY"]],
        on="PAIR_KEY",
        how="left",
    )

    # Add new functional-only pairs
    existing_keys = set(merged["PAIR_KEY"])
    new_pairs = []
    for _, row in func_df.iterrows():
        if row["PAIR_KEY"] not in existing_keys:
            new_pairs.append({
                "NAME_1": row["NAME_1"],
                "NAME_2": row["NAME_2"],
                "COUNT_SET": 0,
                "COUNT_MULTISET": 0,
                "FUNCTIONAL_SIMILARITY": row["FUNCTIONAL_SIMILARITY"],
                "PAIR_KEY": row["PAIR_KEY"],
            })

    if new_pairs:
        new_df = pd.DataFrame(new_pairs)
        merged = pd.concat([merged, new_df], ignore_index=True)

    merged = merged.drop(columns=["PAIR_KEY"])
    merged.to_csv(output_csv, index=False)
    return merged


class TestBlendedEdgelistMerge:
    """Test blended edgelist merge logic."""

    def test_overlapping_edges_get_functional_similarity(self, tmp_path: Path):
        """Edges present in both sources should gain a FUNCTIONAL_SIMILARITY column."""
        base_pairs = [
            ("Lightning Bolt", "Rift Bolt", 10, 15),
            ("Brainstorm", "Ponder", 8, 12),
        ]
        base_csv = tmp_path / "pairs.csv"
        _make_pairs_csv(base_pairs, base_csv)

        functional_edges = [
            ("Lightning Bolt", "Rift Bolt", 0.85),
        ]

        output = tmp_path / "merged.csv"
        merged = _merge_edgelists(base_csv, functional_edges, output)

        # Same number of rows (one overlap, no new)
        assert len(merged) == 2

        # The overlapping pair should have functional similarity
        bolt_row = merged[
            (merged["NAME_1"] == "Lightning Bolt") & (merged["NAME_2"] == "Rift Bolt")
        ].iloc[0]
        assert bolt_row["FUNCTIONAL_SIMILARITY"] == pytest.approx(0.85)

        # The non-overlapping pair should have NaN
        brain_row = merged[
            (merged["NAME_1"] == "Brainstorm") & (merged["NAME_2"] == "Ponder")
        ].iloc[0]
        assert pd.isna(brain_row["FUNCTIONAL_SIMILARITY"])

    def test_non_overlapping_edges_added(self, tmp_path: Path):
        """Functional edges not in the base should be added as new rows."""
        base_pairs = [
            ("Lightning Bolt", "Rift Bolt", 10, 15),
        ]
        base_csv = tmp_path / "pairs.csv"
        _make_pairs_csv(base_pairs, base_csv)

        functional_edges = [
            ("Dark Ritual", "Cabal Ritual", 0.90),
        ]

        output = tmp_path / "merged.csv"
        merged = _merge_edgelists(base_csv, functional_edges, output)

        # 1 original + 1 new
        assert len(merged) == 2

        # New row should have COUNT_SET=0, COUNT_MULTISET=0
        new_row = merged[merged["NAME_1"] == "Dark Ritual"].iloc[0]
        assert new_row["COUNT_SET"] == 0
        assert new_row["COUNT_MULTISET"] == 0
        assert new_row["FUNCTIONAL_SIMILARITY"] == pytest.approx(0.90)

    def test_empty_functional_edges(self, tmp_path: Path):
        """Merging with no functional edges should return original pairs unchanged."""
        base_pairs = [
            ("Lightning Bolt", "Rift Bolt", 10, 15),
            ("Brainstorm", "Ponder", 8, 12),
        ]
        base_csv = tmp_path / "pairs.csv"
        _make_pairs_csv(base_pairs, base_csv)

        output = tmp_path / "merged.csv"
        merged = _merge_edgelists(base_csv, [], output)

        assert len(merged) == 2
        # All functional similarity should be NaN
        assert merged["FUNCTIONAL_SIMILARITY"].isna().all()

    def test_reversed_name_order_still_merges(self, tmp_path: Path):
        """Edge (A,B) in base and (B,A) in functional should still merge (PAIR_KEY is sorted)."""
        base_pairs = [
            ("Alpha", "Beta", 5, 7),
        ]
        base_csv = tmp_path / "pairs.csv"
        _make_pairs_csv(base_pairs, base_csv)

        # Reversed order
        functional_edges = [
            ("Beta", "Alpha", 0.75),
        ]

        output = tmp_path / "merged.csv"
        merged = _merge_edgelists(base_csv, functional_edges, output)

        # Should merge in-place, not add a new row
        assert len(merged) == 1
        assert merged.iloc[0]["FUNCTIONAL_SIMILARITY"] == pytest.approx(0.75)

    def test_multiple_overlapping_and_new(self, tmp_path: Path):
        """Mixed scenario: some overlap, some new from both sides."""
        base_pairs = [
            ("A", "B", 10, 20),
            ("C", "D", 5, 8),
            ("E", "F", 3, 4),
        ]
        base_csv = tmp_path / "pairs.csv"
        _make_pairs_csv(base_pairs, base_csv)

        functional_edges = [
            ("A", "B", 0.9),   # overlaps
            ("C", "D", 0.6),   # overlaps
            ("G", "H", 0.5),   # new
            ("I", "J", 0.4),   # new
        ]

        output = tmp_path / "merged.csv"
        merged = _merge_edgelists(base_csv, functional_edges, output)

        # 3 original + 2 new = 5
        assert len(merged) == 5
        assert merged["FUNCTIONAL_SIMILARITY"].notna().sum() == 4

    def test_output_csv_roundtrip(self, tmp_path: Path):
        """Merged output should be loadable as valid CSV."""
        base_pairs = [
            ("Card A", "Card B", 10, 15),
        ]
        base_csv = tmp_path / "pairs.csv"
        _make_pairs_csv(base_pairs, base_csv)

        functional_edges = [("Card C", "Card D", 0.7)]

        output = tmp_path / "merged.csv"
        _merge_edgelists(base_csv, functional_edges, output)

        # Read back
        reloaded = pd.read_csv(output)
        assert len(reloaded) == 2
        assert "FUNCTIONAL_SIMILARITY" in reloaded.columns
        assert "NAME_1" in reloaded.columns
        assert "NAME_2" in reloaded.columns
