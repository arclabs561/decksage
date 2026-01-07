"""Graph-based enrichment for annotations.

Extracts graph features, card attributes, and contextual analysis
to enrich similarity annotations with graph DB data.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

try:
    from ..data.incremental_graph import IncrementalCardGraph
    from ..utils.shared_operations import jaccard_similarity
    from .enriched_annotation import (
        CardAttributes,
        CardComparison,
        ContextualAnalysis,
        GraphFeatures,
        TournamentContext,
    )

    HAS_GRAPH = True
except ImportError:
    HAS_GRAPH = False
    IncrementalCardGraph = None  # type: ignore
    jaccard_similarity = None  # type: ignore


def compute_jaccard_from_graph(
    graph: IncrementalCardGraph, card1: str, card2: str, game: str | None = None
) -> float:
    """Compute Jaccard similarity from graph neighbors."""
    if not HAS_GRAPH or graph is None:
        return 0.0

    neighbors1 = set(graph.get_neighbors(card1, min_weight=1, game=game))
    neighbors2 = set(graph.get_neighbors(card2, min_weight=1, game=game))

    if not neighbors1 or not neighbors2:
        return 0.0

    intersection = len(neighbors1 & neighbors2)
    union = len(neighbors1 | neighbors2)

    return intersection / union if union > 0 else 0.0


def extract_graph_features(
    graph: IncrementalCardGraph | None,
    card1: str,
    card2: str,
    game: str | None = None,
) -> GraphFeatures | None:
    """Extract graph-derived features for a card pair."""
    if not HAS_GRAPH or graph is None:
        return None

    # Get neighbors for both cards
    neighbors1 = set(graph.get_neighbors(card1, min_weight=1, game=game))
    neighbors2 = set(graph.get_neighbors(card2, min_weight=1, game=game))

    # Compute Jaccard similarity
    jaccard = compute_jaccard_from_graph(graph, card1, card2, game)

    # Find direct edge
    edge_key1 = tuple(sorted([card1, card2]))
    edge_key2 = (card1, card2) if card1 < card2 else (card2, card1)
    edge = graph.edges.get(edge_key1) or graph.edges.get(edge_key2)

    # Compute common neighbors
    common_neighbors = len(neighbors1 & neighbors2)

    # Compute graph distance (shortest path)
    graph_distance = None
    if edge:
        graph_distance = 1  # Direct edge
    else:
        # BFS to find shortest path
        from collections import deque

        queue = deque([(card1, 0)])
        visited = {card1}

        while queue:
            current, dist = queue.popleft()
            if current == card2:
                graph_distance = dist
                break

            for neighbor in graph.get_neighbors(current, min_weight=1, game=game):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, dist + 1))

        # If not found, they're disconnected
        if graph_distance is None:
            graph_distance = None  # Disconnected

    # Compute co-occurrence count and frequency
    cooccurrence_count = edge.weight if edge else 0
    total_decks_card1 = graph.nodes.get(card1, type("obj", (), {"total_decks": 0})()).total_decks
    total_decks_card2 = graph.nodes.get(card2, type("obj", (), {"total_decks": 0})()).total_decks
    cooccurrence_frequency = (
        cooccurrence_count / max(total_decks_card1, total_decks_card2, 1)
        if max(total_decks_card1, total_decks_card2) > 0
        else 0.0
    )

    return GraphFeatures(
        cooccurrence_count=cooccurrence_count,
        cooccurrence_frequency=cooccurrence_frequency,
        jaccard_similarity=jaccard,
        graph_distance=graph_distance,
        common_neighbors=common_neighbors,
        total_neighbors_card1=len(neighbors1),
        total_neighbors_card2=len(neighbors2),
        edge_weight=edge.weight if edge else None,
    )


def load_card_attributes(
    card_name: str, card_attributes: dict[str, dict[str, Any]] | None = None
) -> CardAttributes:
    """Load card attributes from card_attributes dict with case-insensitive matching."""
    if not card_attributes:
        return CardAttributes()
    
    # Try exact match first
    attrs = card_attributes.get(card_name, {})
    
    # If not found, try case-insensitive match
    if not attrs:
        card_name_lower = card_name.strip().lower()
        for key, value in card_attributes.items():
            if key.strip().lower() == card_name_lower:
                attrs = value
                break

    # Parse color_identity if it's a string
    color_identity = attrs.get("color_identity", [])
    if isinstance(color_identity, str):
        color_identity = [c.strip() for c in color_identity.split(",") if c.strip()]

    # Parse subtypes if it's a string
    subtypes = attrs.get("subtypes", [])
    if isinstance(subtypes, str):
        subtypes = [s.strip() for s in subtypes.split(",") if s.strip()]

    # Parse keywords if it's a string
    keywords = attrs.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]

    # Handle NaN values from pandas
    def clean_value(val):
        if val is None:
            return None
        if isinstance(val, float):
            import math
            if math.isnan(val):
                return None
        if isinstance(val, str) and val.lower() in ("nan", "none", ""):
            return None
        return val
    
    return CardAttributes(
        mana_cost=clean_value(attrs.get("mana_cost")),
        cmc=clean_value(attrs.get("cmc")),
        color_identity=color_identity if isinstance(color_identity, list) else [],
        type=clean_value(attrs.get("type") or attrs.get("type_line")),
        subtypes=subtypes if isinstance(subtypes, list) else [],
        power=clean_value(attrs.get("power")),
        toughness=clean_value(attrs.get("toughness")),
        oracle_text=clean_value(attrs.get("oracle_text")),
        keywords=keywords if isinstance(keywords, list) else [],
        rarity=clean_value(attrs.get("rarity")),
    )


def compare_card_attributes(
    card1: str,
    card2: str,
    card_attributes: dict[str, dict[str, Any]] | None = None,
) -> CardComparison | None:
    """Compare card attributes and compute similarities.
    
    Returns CardComparison even if card_attributes is None or cards not found,
    but with empty CardAttributes. This ensures card_comparison field exists
    even for non-Magic games (allowing meta-judge to detect missing data).
    """
    # Always create CardComparison, even if attributes are missing
    # This allows downstream code to detect missing data vs missing field
    attrs1 = load_card_attributes(card1, card_attributes) if card_attributes else CardAttributes()
    attrs2 = load_card_attributes(card2, card_attributes) if card_attributes else CardAttributes()
    
    # If we have no attributes at all, still return CardComparison but with empty attrs
    # This is better than returning None, as it allows detection of missing data

    # Compute attribute-level similarities
    attribute_similarity = {}

    # Mana cost similarity (exact match = 1.0, partial = 0.5, different = 0.0)
    if attrs1.mana_cost and attrs2.mana_cost:
        attribute_similarity["mana_cost"] = (
            1.0 if attrs1.mana_cost == attrs2.mana_cost else 0.0
        )
    elif attrs1.mana_cost or attrs2.mana_cost:
        attribute_similarity["mana_cost"] = 0.0

    # CMC similarity (closer = higher)
    if attrs1.cmc is not None and attrs2.cmc is not None:
        cmc_diff = abs(attrs1.cmc - attrs2.cmc)
        attribute_similarity["cmc"] = max(0.0, 1.0 - (cmc_diff / 10.0))  # Normalize to 0-1
    elif attrs1.cmc is not None or attrs2.cmc is not None:
        attribute_similarity["cmc"] = 0.0

    # Type similarity (exact match = 1.0, same base type = 0.7, different = 0.0)
    if attrs1.type and attrs2.type:
        if attrs1.type == attrs2.type:
            attribute_similarity["type"] = 1.0
        elif attrs1.type.split()[0] == attrs2.type.split()[0]:  # Same base type
            attribute_similarity["type"] = 0.7
        else:
            attribute_similarity["type"] = 0.0

    # Color identity similarity (Jaccard on color sets)
    if attrs1.color_identity and attrs2.color_identity:
        set1 = set(attrs1.color_identity)
        set2 = set(attrs2.color_identity)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        attribute_similarity["color_identity"] = intersection / union if union > 0 else 0.0

    # Subtype similarity (Jaccard on subtype sets)
    if attrs1.subtypes and attrs2.subtypes:
        set1 = set(attrs1.subtypes)
        set2 = set(attrs2.subtypes)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        attribute_similarity["subtypes"] = intersection / union if union > 0 else 0.0

    # Keywords similarity (Jaccard on keyword sets)
    if attrs1.keywords and attrs2.keywords:
        set1 = set(attrs1.keywords)
        set2 = set(attrs2.keywords)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        attribute_similarity["keywords"] = intersection / union if union > 0 else 0.0

    # Functional overlap (shared keywords)
    functional_overlap = list(set(attrs1.keywords) & set(attrs2.keywords))

    # Differences
    differences = []
    if attrs1.type != attrs2.type:
        differences.append(f"{card1} is {attrs1.type}, {card2} is {attrs2.type}")
    if attrs1.mana_cost != attrs2.mana_cost:
        differences.append(f"{card1} costs {attrs1.mana_cost}, {card2} costs {attrs2.mana_cost}")
    if attrs1.cmc != attrs2.cmc:
        differences.append(f"{card1} CMC {attrs1.cmc}, {card2} CMC {attrs2.cmc}")

    return CardComparison(
        card1_attrs=attrs1,
        card2_attrs=attrs2,
        attribute_similarity=attribute_similarity,
        functional_overlap=functional_overlap,
        differences=differences,
    )


def extract_contextual_analysis(
    graph: IncrementalCardGraph | None,
    card1: str,
    card2: str,
    game: str | None = None,
) -> ContextualAnalysis | None:
    """Extract contextual analysis (archetype, format, temporal patterns)."""
    if not HAS_GRAPH or graph is None:
        return None

    # Find edge
    edge_key1 = tuple(sorted([card1, card2]))
    edge_key2 = (card1, card2) if card1 < card2 else (card2, card1)
    edge = graph.edges.get(edge_key1) or graph.edges.get(edge_key2)

    if not edge:
        return ContextualAnalysis()

    metadata = edge.metadata or {}

    # Extract archetypes
    archetypes_together = []
    archetype_counts = defaultdict(int)

    # Check edge metadata
    if "archetype" in metadata:
        archetypes_together.append(str(metadata["archetype"]))

    # Check deck sources for archetype patterns
    # (This would require loading deck metadata, simplified here)

    # Extract formats
    formats_together = []
    format_counts = defaultdict(int)

    if "format" in metadata:
        formats_together.append(str(metadata["format"]))

    # Compute specificity (how concentrated the relationship is)
    # Simplified: if they appear in few archetypes/formats, higher specificity
    archetype_specificity = 1.0 / max(len(archetypes_together), 1) if archetypes_together else 0.0
    format_specificity = 1.0 / max(len(formats_together), 1) if formats_together else 0.0

    # Temporal analysis
    temporal_trend = "unknown"
    peak_periods = []

    if edge.monthly_counts:
        counts = list(edge.monthly_counts.values())
        if len(counts) >= 3:
            # Simple trend detection
            recent = sum(counts[-3:])
            earlier = sum(counts[:-3]) if len(counts) > 3 else 0
            if recent > earlier * 1.2:
                temporal_trend = "increasing"
            elif recent < earlier * 0.8:
                temporal_trend = "decreasing"
            else:
                temporal_trend = "stable"

            # Find peak periods
            sorted_periods = sorted(
                edge.monthly_counts.items(), key=lambda x: x[1], reverse=True
            )
            peak_periods = [period for period, _ in sorted_periods[:3]]

    # Tournament context (if available in metadata)
    tournament_context = None
    if "placement" in metadata or "event_date" in metadata:
        tournament_context = TournamentContext(
            top8_appearances=metadata.get("top8_count", 0),
            win_rate_together=metadata.get("win_rate"),
            placement_distribution=metadata.get("placement_distribution", {}),
        )

    return ContextualAnalysis(
        archetypes_together=archetypes_together,
        archetype_specificity=min(archetype_specificity, 1.0),
        formats_together=formats_together,
        format_specificity=min(format_specificity, 1.0),
        temporal_trend=temporal_trend,
        peak_periods=peak_periods,
        tournament_context=tournament_context,
    )


def enrich_annotation_with_graph(
    annotation: dict[str, Any],
    graph: IncrementalCardGraph | None = None,
    card_attributes: dict[str, dict[str, Any]] | None = None,
    game: str | None = None,
) -> dict[str, Any]:
    """Enrich an annotation with graph features, card attributes, and contextual analysis.
    
    Preserves all original annotation fields including 'source' which is required for validation.
    """
    card1 = annotation.get("card1")
    card2 = annotation.get("card2")

    if not card1 or not card2:
        return annotation

    # Preserve source field if missing (required for UnifiedAnnotation validation)
    if "source" not in annotation:
        # Infer source from other fields
        if annotation.get("model_name"):
            annotation["source"] = "llm"
        elif annotation.get("relevance") is not None:
            annotation["source"] = "hand"
        elif annotation.get("annotator_id"):
            annotation["source"] = "multi_judge"
        else:
            annotation["source"] = "unknown"

    # Extract graph features
    graph_features = extract_graph_features(graph, card1, card2, game)
    if graph_features:
        annotation["graph_features"] = graph_features.model_dump() if hasattr(graph_features, "model_dump") else graph_features.__dict__

    # Compare card attributes
    card_comparison = compare_card_attributes(card1, card2, card_attributes)
    if card_comparison:
        annotation["card_comparison"] = card_comparison.model_dump() if hasattr(card_comparison, "model_dump") else card_comparison.__dict__

    # Extract contextual analysis
    contextual_analysis = extract_contextual_analysis(graph, card1, card2, game)
    if contextual_analysis:
        annotation["contextual_analysis"] = contextual_analysis.model_dump() if hasattr(contextual_analysis, "model_dump") else contextual_analysis.__dict__

    return annotation

