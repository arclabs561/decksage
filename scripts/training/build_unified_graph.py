#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.24.0", "sentence-transformers>=2.2.0"]
# ///
"""
Build the unified SQLite graph from all edge sources.

Converges the 56-file edgelist sprawl into a single IncrementalCardGraph SQLite
database with source_type-tagged edges. Replaces the manual multi-file merge step
in train_all_embeddings.py.

Sources ingested:
  1. Co-occurrence pairs (from Go scraper CSV/edgelist)  -> source_type='co_occurrence'
  2. PPMI-reweighted edges (computed in-process)          -> source_type='ppmi'
  3. Oracle text similarity (computed in-process)         -> source_type='oracle_text'
  4. LLM annotation edges (from annotation JSON)          -> source_type='annotation'
  5. Propagated pseudo-labels (computed in-process)        -> source_type='propagated'
  6. Card attributes CSV -> node enrichment (oracle_text, image_url)

Usage:
    # Build for one game
    PYTHONPATH=src python scripts/training/build_unified_graph.py --game magic

    # Build for all games
    PYTHONPATH=src python scripts/training/build_unified_graph.py

    # Dry run
    PYTHONPATH=src python scripts/training/build_unified_graph.py --game pokemon --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.data.incremental_graph import IncrementalCardGraph
from ml.utils.data_loading import load_edgelist


# Game name -> internal game code mapping
GAME_CODE = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO", "digimon": "DGM", "riftbound": "RFB"}

# ── Game configurations ──
# Mirrors GAME_CONFIGS from train_all_embeddings.py but adds all source paths.

GAME_CONFIGS = {
    "magic": {
        "base_edgelist": "data/graphs/pairs_large.edg",
        "deck_jsonl": [
            "data/decks/decks_magic_goldfish.jsonl",
            "data/decks/decks_magic_commander_combined.jsonl",
            "data/decks/decks_magic_commander_extended.jsonl",
            "data/decks/decks_magic_commander_seq.jsonl",
            "data/decks/decks_magic_mtgtop8.jsonl",
        ],
        "annotations": [
            "data/annotations/magic_500_v3.json",
            "data/annotations/magic_500_hub_v3.json",
        ],
        "enriched_edgelist": "data/graphs/pairs_enriched_magic_v3b.edg",
        "card_attributes": "data/processed/card_attributes_enriched.csv",
        "image_urls": "data/processed/card_attributes_enriched_image_urls.json",
    },
    "pokemon": {
        "base_edgelist": "data/graphs/pokemon_blended.edg",
        "deck_jsonl": [
            "data/decks/decks_pokemon.jsonl",
            "data/decks/decks_pokemon_limitless.jsonl",
            "data/decks/decks_pokemon_limitless_expanded.jsonl",
            "data/decks/decks_pokemon_limitless-web.jsonl",
            "data/decks/decks_pokemon_limitless-web-expanded.jsonl",
        ],
        "annotations": [
            "data/annotations/pokemon_500_v3.json",
        ],
        "enriched_edgelist": "data/graphs/pairs_enriched_pokemon_v3b.edg",
        "card_attributes": "data/processed/card_attributes_pokemon_enriched.csv",
        "image_urls": "data/processed/pokemon_image_urls.json",
    },
    "yugioh": {
        "base_edgelist": "data/graphs/yugioh_blended.edg",
        "deck_jsonl": [
            "data/decks/decks_yugioh_resolved.jsonl",
            "data/decks/decks_yugioh_ygoprodeck-tournament.jsonl",
            "data/decks/decks_yugioh_masterduelmeta.jsonl",
        ],
        "annotations": [
            "data/annotations/yugioh_500_v3.json",
        ],
        "enriched_edgelist": "data/graphs/pairs_enriched_yugioh_v4.edg",
        "card_attributes": "data/processed/card_attributes_yugioh_enriched.csv",
        "image_urls": "data/processed/yugioh_image_urls.json",
    },
    "digimon": {
        "base_edgelist": None,
        "deck_jsonl": [
            "data/decks/decks_digimon.jsonl",
            "data/decks/decks_digimon_limitless.jsonl",
        ],
        "annotations": [],
        "enriched_edgelist": None,
        "card_attributes": "data/processed/card_attributes_digimon.csv",
        "image_urls": None,
    },
    "riftbound": {
        "base_edgelist": None,
        "deck_jsonl": [
            "data/decks/decks_riftbound.jsonl",
        ],
        "annotations": [],
        "enriched_edgelist": None,
        "card_attributes": "data/processed/card_attributes_riftbound.csv",
        "image_urls": None,
    },
}


# ── Edge loading helpers ──


## load_edgelist imported from ml.utils.data_loading (consolidated)


# ── Metadata-aware deck loading ──


def load_decks_with_metadata(
    jsonl_paths: list[Path],
) -> list[dict]:
    """Load deck records from JSONL files, keeping metadata."""
    decks = []
    for path in jsonl_paths:
        if not path.exists():
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    decks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return decks


def collect_card_metadata(
    decks: list[dict],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Collect per-card format and archetype tags from deck records.

    Returns:
        (card_formats, card_archetypes)
    """
    card_formats: dict[str, set[str]] = defaultdict(set)
    card_archetypes: dict[str, set[str]] = defaultdict(set)

    for deck in decks:
        fmt = (deck.get("format") or "").strip()
        arch = (deck.get("archetype") or "").strip()
        if not fmt and not arch:
            continue

        # Extract unique card names from deck
        unique_cards: set[str] = set()
        for card in deck.get("cards", []):
            name = (card.get("name", "") if isinstance(card, dict) else str(card)).strip()
            if name:
                unique_cards.add(name)
        for partition in deck.get("partitions", []):
            for card in partition.get("cards", []):
                name = (card.get("name", "") if isinstance(card, dict) else str(card)).strip()
                if name:
                    unique_cards.add(name)

        for card in unique_cards:
            if fmt:
                card_formats[card].add(fmt)
            if arch:
                card_archetypes[card].add(arch)

    return dict(card_formats), dict(card_archetypes)


# ── Temporal decay for co-occurrence ──

# Default halflife per format family (days). Rotating formats decay faster.
FORMAT_HALFLIFE: dict[str, float] = {
    "Standard": 90,
    "Pioneer": 180,
    "Modern": 365,
    "Legacy": 730,
    "Vintage": 730,
    "Commander": 365,
    "Pauper": 365,
}


def compute_temporally_weighted_cooccurrence(
    decks: list[dict],
    halflife_days: float,
    reference_date: datetime | None = None,
) -> list[tuple[str, str, float]]:
    """Compute co-occurrence edges with exponential temporal decay.

    Each deck's co-occurrence contribution is weighted by
    exp(-ln(2) / halflife * age_days), so edges from older decks
    contribute less. Decks without timestamps get weight 1.0 (no penalty).

    Args:
        decks: Deck records with optional 'created_at' and 'format' fields.
        halflife_days: Base halflife in days. Per-format overrides are applied
            when the deck has a recognized format.
        reference_date: "Now" for age computation (default: actual now).

    Returns:
        List of (card1, card2, weight) tuples.
    """
    if reference_date is None:
        reference_date = datetime.now()

    ln2 = math.log(2)
    edge_weights: dict[tuple[str, str], float] = defaultdict(float)

    for deck in decks:
        # Determine decay weight
        decay_w = 1.0
        ts_str = (deck.get("created_at") or "").strip()
        if ts_str:
            try:
                # Accept both ISO datetime and date-only
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts = ts.replace(tzinfo=None)  # naive comparison
                age_days = max(0.0, (reference_date - ts).total_seconds() / 86400)
                # Use format-specific halflife if available
                fmt = (deck.get("format") or "").strip()
                hl = FORMAT_HALFLIFE.get(fmt, halflife_days)
                if hl > 0:
                    decay_w = math.exp(-ln2 / hl * age_days)
            except (ValueError, TypeError):
                pass  # unparseable timestamp -> weight 1.0

        # Extract card names
        cards: list[str] = []
        for card in deck.get("cards", []):
            name = (card.get("name", "") if isinstance(card, dict) else str(card)).strip()
            if name:
                cards.append(name)
        for partition in deck.get("partitions", []):
            for card in partition.get("cards", []):
                name = (card.get("name", "") if isinstance(card, dict) else str(card)).strip()
                if name:
                    cards.append(name)

        # Pairwise co-occurrence (deduplicated names within deck)
        unique = sorted(set(cards))
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                key = (unique[i], unique[j])  # already sorted
                edge_weights[key] += decay_w

    return [(c1, c2, w) for (c1, c2), w in edge_weights.items() if w > 0]


# ── PPMI computation (from ppmi_sparsify.py logic) ──


def compute_ppmi(
    edges: list[tuple[str, str, float]],
    threshold: float = 0.5,
    top_k: int = 50,
) -> list[tuple[str, str, float]]:
    """Compute PPMI-reweighted edges from raw co-occurrence."""
    node_degree: dict[str, float] = defaultdict(float)
    total_weight = 0.0
    for n1, n2, w in edges:
        node_degree[n1] += w
        node_degree[n2] += w
        total_weight += w

    if total_weight == 0:
        return []

    ppmi_edges: list[tuple[str, str, float, float]] = []
    for n1, n2, w in edges:
        p_ij = w / total_weight
        p_i = node_degree[n1] / (2 * total_weight)
        p_j = node_degree[n2] / (2 * total_weight)
        if p_i == 0 or p_j == 0:
            continue
        pmi = math.log2(p_ij / (p_i * p_j))
        ppmi = max(0.0, pmi)
        if ppmi >= threshold:
            ppmi_edges.append((n1, n2, ppmi, w))

    # Top-K filtering per node
    if top_k > 0:
        node_neighbors: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for n1, n2, ppmi, w in ppmi_edges:
            node_neighbors[n1].append((n2, ppmi))
            node_neighbors[n2].append((n1, ppmi))

        kept_pairs: set[tuple[str, str]] = set()
        for node, neighbors in node_neighbors.items():
            neighbors.sort(key=lambda x: -x[1])
            for nb, _ in neighbors[:top_k]:
                kept_pairs.add(tuple(sorted([node, nb])))

        ppmi_edges = [
            (n1, n2, ppmi, w)
            for n1, n2, ppmi, w in ppmi_edges
            if tuple(sorted([n1, n2])) in kept_pairs
        ]

    # Return with ppmi_scaled weight (ppmi * original)
    return [(n1, n2, ppmi * w) for n1, n2, ppmi, w in ppmi_edges]


# ── Annotation loading (from annotations_to_edgelist.py logic) ──


def load_annotation_edges(
    paths: list[Path],
    min_score: float = 0.20,
    weight_scale: float = 10.0,
) -> list[tuple[str, str, float]]:
    """Load annotation pairs as weighted edges."""
    edges: dict[tuple[str, str], float] = {}
    for path in paths:
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        for label in data.get("labels", []):
            consensus = label.get("consensus")
            if not consensus:
                continue
            score = consensus.get("similarity_score", 0.0)
            if score < min_score:
                continue
            c1, c2 = label["card1"], label["card2"]
            key = tuple(sorted([c1, c2]))
            weight = score * weight_scale
            edges[key] = max(edges.get(key, 0.0), weight)
    return [(c1, c2, w) for (c1, c2), w in edges.items()]


# ── Label propagation (from propagate_labels.py logic) ──


def propagate_labels(
    labeled_pairs: list[tuple[str, str, float]],
    adj: dict[str, dict[str, float]],
    decay: float = 0.7,
    jaccard_threshold: float = 0.10,
    max_per_pair: int = 30,
    weight_scale: float = 10.0,
) -> list[tuple[str, str, float]]:
    """Propagate annotation labels to nearby nodes via graph structure."""
    original_keys = {tuple(sorted([a, b])) for a, b, _ in labeled_pairs}
    propagated: dict[tuple[str, str], float] = {}

    for a, b, score in labeled_pairs:
        neighbors_a = set(adj.get(a, {}).keys())
        neighbors_b = set(adj.get(b, {}).keys())

        # Propagate from A's perspective: find C near B, check if A ~ C
        for c in neighbors_b - {a, b}:
            neighbors_c = set(adj.get(c, {}).keys())
            inter = len(neighbors_a & neighbors_c)
            union = len(neighbors_a | neighbors_c)
            j = inter / union if union > 0 else 0.0
            if j >= jaccard_threshold:
                key = tuple(sorted([a, c]))
                if key not in original_keys:
                    propagated[key] = max(propagated.get(key, 0.0), score * decay * j)

        # Propagate from B's perspective: find C near A, check if B ~ C
        for c in neighbors_a - {a, b}:
            neighbors_c = set(adj.get(c, {}).keys())
            inter = len(neighbors_b & neighbors_c)
            union = len(neighbors_b | neighbors_c)
            j = inter / union if union > 0 else 0.0
            if j >= jaccard_threshold:
                key = tuple(sorted([b, c]))
                if key not in original_keys:
                    propagated[key] = max(propagated.get(key, 0.0), score * decay * j)

    # Include original labeled pairs + propagated
    merged: dict[tuple[str, str], float] = {}
    for a, b, score in labeled_pairs:
        key = tuple(sorted([a, b]))
        merged[key] = max(merged.get(key, 0.0), score * weight_scale)
    for key, score in propagated.items():
        merged[key] = max(merged.get(key, 0.0), score * weight_scale)

    return [(c1, c2, w) for (c1, c2), w in merged.items()]


# ── Oracle text similarity (from oracle_text_edges.py logic) ──


def compute_oracle_text_edges(
    csv_path: Path,
    threshold: float = 0.85,
    top_k: int = 15,
    weight_scale: float = 3.0,
    name_col: str = "name",
    text_col: str = "oracle_text",
    type_col: str = "type",
) -> list[tuple[str, str, float]]:
    """Compute oracle text similarity edges using sentence-transformers."""
    from sentence_transformers import SentenceTransformer

    # Load cards
    cards = []
    seen = set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get(name_col, "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            parts = [name]
            if type_col and row.get(type_col):
                parts.append(row[type_col].strip())
            text = row.get(text_col, "").strip()
            if text and text != "nan":
                parts.append(text)
            full_text = ". ".join(parts)
            if len(full_text) > len(name) + 5:
                cards.append((name, full_text))

    if len(cards) < 2:
        print(f"  Only {len(cards)} cards with text, skipping oracle text edges")
        return []

    names = [c[0] for c in cards]
    texts = [c[1] for c in cards]

    print(f"  Embedding {len(texts)} cards for oracle text similarity...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(
        texts,
        batch_size=256,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    # Chunked pairwise similarity
    n = len(names)
    pairs = []
    chunk_size = 1000
    for i in range(0, n, chunk_size):
        chunk_end = min(i + chunk_size, n)
        sims = embeddings[i:chunk_end] @ embeddings.T
        for local_idx in range(chunk_end - i):
            global_idx = i + local_idx
            row = sims[local_idx]
            row[: global_idx + 1] = -1
            if top_k < n:
                top_indices = np.argpartition(row, -top_k)[-top_k:]
                top_indices = top_indices[row[top_indices] >= threshold]
            else:
                top_indices = np.where(row >= threshold)[0]
            for j in top_indices:
                score = float(row[j])
                if score >= threshold:
                    pairs.append((names[global_idx], names[int(j)], score * weight_scale))

    print(f"  Found {len(pairs):,} oracle text edges (threshold={threshold})")
    return pairs


# ── Node enrichment ──


def enrich_nodes(
    graph: IncrementalCardGraph,
    csv_path: Path,
    image_urls_path: Path | None,
    game_code: str,
) -> None:
    """Enrich graph nodes with oracle_text and image_url from CSV and JSON."""
    # Load oracle text from card attributes CSV
    if csv_path and csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name", "").strip()
                if not name:
                    continue
                oracle_text = row.get("oracle_text", "").strip()
                if oracle_text and oracle_text != "nan":
                    if name in graph.nodes:
                        graph.nodes[name].oracle_text = oracle_text
                    else:

                        from ml.data.incremental_graph import CardNode

                        graph.nodes[name] = CardNode(
                            name=name,
                            game=game_code,
                            oracle_text=oracle_text,
                        )

    # Load image URLs from JSON
    if image_urls_path and image_urls_path.exists():
        with open(image_urls_path) as f:
            image_urls = json.load(f)
        for name, url in image_urls.items():
            if name in graph.nodes:
                graph.nodes[name].image_url = url


# ── Main build logic ──


def build_game(
    game: str,
    config: dict,
    output_db: Path,
    dry_run: bool = False,
    halflife_days: float = 0,
) -> None:
    """Build the unified SQLite graph for one game."""
    game_code = GAME_CODE[game]
    base_edgelist = PROJECT_ROOT / config["base_edgelist"] if config["base_edgelist"] else None
    csv_path = PROJECT_ROOT / config["card_attributes"] if config["card_attributes"] else None
    annotation_paths = [PROJECT_ROOT / p for p in config["annotations"]]
    image_urls_path = (
        PROJECT_ROOT / config["image_urls"] if config.get("image_urls") else None
    )

    print(f"\n{'='*60}")
    print(f"  Building unified graph: {game.upper()}")
    print(f"  Output: {output_db}")
    print(f"{'='*60}")

    deck_jsonl_paths = [PROJECT_ROOT / p for p in config.get("deck_jsonl", [])]

    if dry_run:
        print("\n[DRY RUN] Would build from:")
        print(f"  Base edgelist: {base_edgelist}")
        print(f"  Deck JSONL: {[str(p) for p in deck_jsonl_paths]}")
        print(f"  Annotations: {[str(p) for p in annotation_paths]}")
        print(f"  Card attributes: {csv_path}")
        print(f"  Image URLs: {image_urls_path}")
        if halflife_days > 0:
            print(f"  Temporal decay: halflife={halflife_days} days")
        return

    # Initialize graph
    graph = IncrementalCardGraph(graph_path=output_db, use_sqlite=True)

    # 1. Co-occurrence edges from base edgelist
    raw_edges: list[tuple[str, str, float]] = []
    if base_edgelist and base_edgelist.exists():
        print(f"\n[1/8] Loading co-occurrence edges from {base_edgelist.name}...")
        raw_edges = load_edgelist(base_edgelist)
        print(f"  {len(raw_edges):,} co-occurrence edges")
        for c1, c2, w in raw_edges:
            graph.add_edge(c1, c2, w, source_type="co_occurrence", game=game_code)
    else:
        print("\n[1/8] No base edgelist, will build co-occurrence from deck JSONL")

    # 1b. Load deck JSONL for node metadata (format/archetype tags)
    # Placement-weighted edge merging was tested but caused nDCG regression
    # (dilutes curated co-occurrence signal). Metadata is node-only.
    existing_jsonl = [p for p in deck_jsonl_paths if p.exists()]
    card_formats: dict[str, set[str]] = {}
    card_archetypes: dict[str, set[str]] = {}
    if existing_jsonl:
        decks = load_decks_with_metadata(existing_jsonl)
        card_formats, card_archetypes = collect_card_metadata(decks)

        # Build co-occurrence from deck JSONL when no base edgelist exists
        if not base_edgelist or not base_edgelist.exists():
            deck_cooccurrence = compute_temporally_weighted_cooccurrence(
                decks, halflife_days=999999,  # effectively no decay
            )
            raw_edges = deck_cooccurrence
            print(f"  {len(raw_edges):,} co-occurrence edges from deck JSONL")
            for c1, c2, w in raw_edges:
                graph.add_edge(c1, c2, w, source_type="co_occurrence", game=game_code)
        has_placement = sum(1 for d in decks if d.get("placement"))
        has_format = sum(1 for d in decks if d.get("format"))
        has_archetype = sum(1 for d in decks if d.get("archetype"))
        print(f"  {len(decks):,} decks from JSONL ({has_placement:,} with placement, "
              f"{has_format:,} with format, {has_archetype:,} with archetype)")
        print(f"  {len(card_formats):,} cards with format tags, "
              f"{len(card_archetypes):,} with archetype tags")

        # Temporal decay: recompute co-occurrence with exponential decay
        if halflife_days > 0:
            has_timestamps = sum(1 for d in decks if d.get("created_at"))
            print(f"\n  [temporal decay] halflife={halflife_days} days, "
                  f"{has_timestamps:,}/{len(decks):,} decks with timestamps")
            if has_timestamps > 0:
                temporal_edges = compute_temporally_weighted_cooccurrence(
                    decks, halflife_days=halflife_days,
                )
                print(f"  [temporal decay] {len(temporal_edges):,} temporally-weighted edges "
                      f"(replacing base co-occurrence)")
                # Replace base edges with temporally-weighted ones
                raw_edges = temporal_edges
                # Re-add to graph (clear old co_occurrence edges first)
                graph_edges_to_remove = [
                    k for k, e in graph.edges.items()
                    if e.source_type == "co_occurrence"
                ]
                for k in graph_edges_to_remove:
                    del graph.edges[k]
                for c1, c2, w in raw_edges:
                    graph.add_edge(c1, c2, w, source_type="co_occurrence", game=game_code)
            else:
                print("  [temporal decay] No timestamped decks, keeping base co-occurrence")

        del decks

    # 2. PPMI edges
    print("\n[2/8] Computing PPMI edges...")
    ppmi_edges = compute_ppmi(raw_edges, threshold=0.5, top_k=50)
    print(f"  {len(ppmi_edges):,} PPMI edges")
    for c1, c2, w in ppmi_edges:
        graph.add_edge(c1, c2, w, source_type="ppmi", game=game_code)

    # 3. Oracle text edges
    print("\n[3/8] Computing oracle text similarity edges...")
    if csv_path and csv_path.exists():
        oracle_edges = compute_oracle_text_edges(
            csv_path, threshold=0.85, top_k=15, weight_scale=3.0
        )
        print(f"  {len(oracle_edges):,} oracle text edges")
        for c1, c2, w in oracle_edges:
            graph.add_edge(c1, c2, w, source_type="oracle_text", game=game_code)
    else:
        print(f"  SKIPPED (no card attributes CSV at {csv_path})")

    # 4. Enriched edgelist (pre-combined annotations + card sets)
    enriched_path = (
        PROJECT_ROOT / config["enriched_edgelist"] if config.get("enriched_edgelist") else None
    )
    print("\n[4/8] Loading enriched edgelist...")
    if enriched_path and enriched_path.exists():
        enriched_edges = load_edgelist(enriched_path)
        print(f"  {len(enriched_edges):,} enriched edges from {enriched_path.name}")
        for c1, c2, w in enriched_edges:
            graph.add_edge(c1, c2, w, source_type="enriched", game=game_code)
    else:
        print("  SKIPPED (no enriched edgelist)")

    # 5. Annotation edges (raw from JSON, separate from enriched for traceability)
    print("\n[5/8] Loading annotation edges...")
    existing_annotations = [p for p in annotation_paths if p.exists()]
    if existing_annotations:
        ann_edges = load_annotation_edges(existing_annotations, min_score=0.20, weight_scale=10.0)
        print(f"  {len(ann_edges):,} annotation edges from {len(existing_annotations)} file(s)")
        for c1, c2, w in ann_edges:
            graph.add_edge(c1, c2, w, source_type="annotation", game=game_code)
    else:
        print("  SKIPPED (no annotation files found)")

    # 6. Propagated edges (requires PPMI adjacency + annotations)
    print("\n[6/8] Propagating labels via graph structure...")
    if existing_annotations and ppmi_edges:
        ppmi_adj: dict[str, dict[str, float]] = defaultdict(dict)
        for c1, c2, w in ppmi_edges:
            ppmi_adj[c1][c2] = max(ppmi_adj[c1].get(c2, 0.0), w)
            ppmi_adj[c2][c1] = max(ppmi_adj[c2].get(c1, 0.0), w)

        raw_annotations = load_annotation_edges(
            existing_annotations, min_score=0.25, weight_scale=1.0
        )
        prop_edges = propagate_labels(
            raw_annotations,
            dict(ppmi_adj),
            decay=0.7,
            jaccard_threshold=0.10,
            max_per_pair=30,
            weight_scale=10.0,
        )
        print(f"  {len(prop_edges):,} propagated edges (original + pseudo-labeled)")
        for c1, c2, w in prop_edges:
            graph.add_edge(c1, c2, w, source_type="propagated", game=game_code)
    else:
        print("  SKIPPED (need both annotations and PPMI edges)")

    # 7. Node enrichment (oracle text, image URLs)
    print("\n[7/8] Enriching nodes with oracle text and image URLs...")
    enrich_nodes(graph, csv_path, image_urls_path, game_code)
    nodes_with_text = sum(1 for n in graph.nodes.values() if n.oracle_text)
    nodes_with_img = sum(1 for n in graph.nodes.values() if n.image_url)
    print(f"  {nodes_with_text:,} nodes with oracle text, {nodes_with_img:,} with image URLs")

    # 8. Node metadata from deck JSONL (format, archetype tags)
    print("\n[8/8] Enriching nodes with format/archetype metadata...")
    n_enriched = 0
    all_tagged_cards = set(card_formats.keys()) | set(card_archetypes.keys())
    for card_name in all_tagged_cards:
        if card_name not in graph.nodes:
            continue
        node = graph.nodes[card_name]
        attrs = node.attributes or {}
        if card_name in card_formats:
            attrs["formats"] = sorted(card_formats[card_name])
        if card_name in card_archetypes:
            attrs["archetypes"] = sorted(card_archetypes[card_name])
        node.attributes = attrs
        n_enriched += 1
    print(f"  {n_enriched:,} nodes enriched with format/archetype tags")

    # Save
    print(f"\nSaving to {output_db}...")
    graph.save_sqlite()

    # Summary
    edge_types: dict[str, int] = defaultdict(int)
    for edge in graph.edges.values():
        edge_types[edge.source_type] += 1
    print("\n  Graph summary:")
    print(f"    Nodes: {len(graph.nodes):,}")
    print(f"    Edges: {len(graph.edges):,}")
    for st, count in sorted(edge_types.items()):
        print(f"      {st}: {count:,}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build unified SQLite graph from all edge sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--game",
        choices=list(GAME_CONFIGS.keys()),
        help="Build for specific game (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "graphs",
        help="Directory for output .db files (default: data/graphs/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )
    parser.add_argument(
        "--halflife-days",
        type=float,
        default=0,
        help="Enable temporal decay on co-occurrence edges. Weight decays by "
             "half every N days. 0 = disabled (default). Suggested: 180 for "
             "mixed formats, 90 for Standard-heavy data.",
    )
    args = parser.parse_args()

    games = [args.game] if args.game else list(GAME_CONFIGS.keys())

    for game in games:
        config = GAME_CONFIGS[game]
        output_db = args.output_dir / f"{game}_unified.db"
        build_game(game, config, output_db, args.dry_run, args.halflife_days)

    print(f"\n{'='*60}")
    print("  Unified graph build complete.")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
