"""
Shared edge file registry for all training scripts.

Single source of truth for which edge types exist and which are safe for training.
Import this instead of duplicating the edge file map.
"""

from __future__ import annotations

from pathlib import Path


# Edge types safe for training (self-supervised, no eval leakage)
TRAINING_EDGE_FILES = {
    "deck": "{game}_merged_all.edg",
    "enriched": "{game}_merged_enriched.edg",
    "set": "{game}_set_cooccurrence.edg",
    "precon": "{game}_precon_cooccurrence.edg",
    "keyword": "{game}_keyword_sharing.edg",
    "archetype": "{game}_archetype_cooccurrence.edg",
    "commander": "{game}_archidekt_commander.edg",
    "oracle_text": "{game}_oracle_text_similarity.edg",
}

# Attribute-based edge files (available but NOT in default training set).
# These create massive cliques (all 4-mana creatures connected) that dilute
# co-occurrence signal. Use as GNN node features, not Cleora/MetaPath2Vec edges.
# Available via --edge-types same_cmc,same_type etc. if experimenting.
ATTRIBUTE_EDGE_FILES = {
    "same_cmc": "{game}_same_cmc.edg",
    "same_type": "{game}_same_type.edg",
    "same_creature_type": "{game}_same_creature_type.edg",
    "same_archetype": "{game}_same_archetype.edg",
}

# Edge types reserved for evaluation only -- NEVER use for training
# Using these creates data leakage (annotation pairs are the eval test set)
EVAL_ONLY_EDGE_FILES = {
    "annotation": "{game}_annotation_edges.edg",
    "diverse_annotation": "{game}_diverse_annotation_edges.edg",
}

# Source types in the unified SQLite graph that are eval-only.
# Training scripts reading from IncrementalCardGraph must filter these out.
# Use TRAINING_SAFE_SOURCE_TYPES with export_edgelist_filtered(source_types=...).
EVAL_ONLY_SOURCE_TYPES = {"annotation", "diverse_annotation"}
TRAINING_SAFE_SOURCE_TYPES = [
    "co_occurrence",
    "ppmi",
    "oracle_text",
    "propagated",
    "set",
    "precon",
    "keyword",
    "archetype",
    "commander",
]

# Quality check pairs per game (for quick sanity checks after training)
QUALITY_PAIRS = {
    "magic": [
        ("Lightning Bolt", "Lava Spike"),
        ("Sol Ring", "Arcane Signet"),
        ("Counterspell", "Mana Leak"),
    ],
    "pokemon": [("Ultra Ball", "Nest Ball")],
    "yugioh": [("Ash Blossom & Joyous Spring", 'Maxx "C"')],
}

# All supported games (auto-discoverable from data/graphs/ but listed for validation)
ALL_GAMES = ["magic", "pokemon", "yugioh", "digimon", "onepiece"]


def get_edge_files(
    game: str, graph_dir: Path, include_types: list[str] | None = None
) -> dict[str, Path]:
    """Return {edge_type: path} for training-safe edge files that exist on disk.

    Args:
        game: Game name (magic, pokemon, yugioh, etc.)
        graph_dir: Path to data/graphs/
        include_types: If provided, only include these edge types. Blocked types
                       are still rejected even if explicitly requested.
    """
    result = {}
    for etype, pattern in TRAINING_EDGE_FILES.items():
        if include_types and etype not in include_types:
            continue
        path = graph_dir / pattern.format(game=game)
        if path.exists():
            result[etype] = path

    # Guard: reject annotation edges even if explicitly requested
    if include_types:
        for blocked_type in EVAL_ONLY_EDGE_FILES:
            if blocked_type in include_types:
                print(
                    f"  WARNING: '{blocked_type}' edges are reserved for evaluation only "
                    f"(train/eval separation). Skipping."
                )

    return result


def load_edges_from_files(
    edge_files: dict[str, Path],
) -> dict[str, list[tuple[str, str, float]]]:
    """Load edges from a {type: path} dict. Returns {type: [(src, dst, weight)]}."""
    edge_types = {}
    for etype, path in edge_files.items():
        edges = []
        with open(path) as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    try:
                        edges.append((parts[0], parts[1], float(parts[2])))
                    except ValueError:
                        continue
        if edges:
            edge_types[etype] = edges
            print(f"  {etype}: {len(edges):,} edges")
    return edge_types


# Per-format edge files (from build_format_edges.py)
FORMAT_EDGE_FILES = {
    "standard": "{game}_standard_cooccurrence.edg",
    "modern": "{game}_modern_cooccurrence.edg",
    "commander": "{game}_archidekt_commander.edg",
}
