"""Utilities for working with enriched annotations.

Provides helpers to extract and use graph features, card comparisons,
and contextual analysis from enriched annotations.
"""

from __future__ import annotations

from typing import Any


def extract_graph_features_from_annotation(
    annotation: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract graph features from an enriched annotation."""
    return annotation.get("graph_features")


def extract_card_comparison_from_annotation(
    annotation: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract card comparison from an enriched annotation."""
    return annotation.get("card_comparison")


def extract_contextual_analysis_from_annotation(
    annotation: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract contextual analysis from an enriched annotation."""
    return annotation.get("contextual_analysis")


def get_jaccard_similarity(annotation: dict[str, Any]) -> float:
    """Get Jaccard similarity from enriched annotation."""
    graph_features = extract_graph_features_from_annotation(annotation)
    if graph_features:
        return graph_features.get("jaccard_similarity", 0.0)
    return 0.0


def get_cooccurrence_count(annotation: dict[str, Any]) -> int:
    """Get co-occurrence count from enriched annotation."""
    graph_features = extract_graph_features_from_annotation(annotation)
    if graph_features:
        return graph_features.get("cooccurrence_count", 0)
    return 0


def get_archetypes_together(annotation: dict[str, Any]) -> list[str]:
    """Get archetypes where both cards appear from enriched annotation."""
    contextual = extract_contextual_analysis_from_annotation(annotation)
    if contextual:
        return contextual.get("archetypes_together", [])
    return []


def get_formats_together(annotation: dict[str, Any]) -> list[str]:
    """Get formats where both cards appear from enriched annotation."""
    contextual = extract_contextual_analysis_from_annotation(annotation)
    if contextual:
        return contextual.get("formats_together", [])
    return []


def validate_annotation_against_graph(annotation: dict[str, Any]) -> dict[str, Any]:
    """Validate LLM annotation against graph data.
    
    Returns validation results including:
    - Graph consistency (does graph support the similarity score?)
    - Attribute consistency (do attributes match the similarity type?)
    - Contextual consistency (does context match archetype/format?)
    """
    validation = {
        "is_valid": True,
        "warnings": [],
        "graph_consistency": None,
        "attribute_consistency": None,
        "contextual_consistency": None,
    }

    similarity_score = annotation.get("similarity_score", 0.0)
    graph_features = extract_graph_features_from_annotation(annotation)
    card_comparison = extract_card_comparison_from_annotation(annotation)
    contextual = extract_contextual_analysis_from_annotation(annotation)

    # Graph consistency check
    if graph_features:
        jaccard = graph_features.get("jaccard_similarity", 0.0)
        cooccurrence = graph_features.get("cooccurrence_count", 0)
        
        # High similarity score but low Jaccard might indicate inconsistency
        if similarity_score > 0.7 and jaccard < 0.3:
            validation["warnings"].append(
                f"High similarity score ({similarity_score:.2f}) but low Jaccard ({jaccard:.2f})"
            )
        
        # Low similarity score but high Jaccard might indicate inconsistency
        if similarity_score < 0.3 and jaccard > 0.7:
            validation["warnings"].append(
                f"Low similarity score ({similarity_score:.2f}) but high Jaccard ({jaccard:.2f})"
            )
        
        validation["graph_consistency"] = {
            "jaccard": jaccard,
            "cooccurrence": cooccurrence,
            "score_alignment": abs(similarity_score - jaccard) < 0.3,
        }

    # Attribute consistency check
    if card_comparison:
        similarity_type = annotation.get("similarity_type", "")
        attribute_sim = card_comparison.get("attribute_similarity", {})
        
        # Functional similarity should have high type/function similarity
        if similarity_type == "functional":
            type_sim = attribute_sim.get("type", 0.0)
            if type_sim < 0.5:
                validation["warnings"].append(
                    f"Functional similarity but low type similarity ({type_sim:.2f})"
                )
        
        # Manabase similarity should have high mana cost similarity
        if similarity_type == "manabase":
            mana_sim = attribute_sim.get("mana_cost", 0.0)
            if mana_sim < 0.5:
                validation["warnings"].append(
                    f"Manabase similarity but low mana cost similarity ({mana_sim:.2f})"
                )
        
        validation["attribute_consistency"] = {
            "attribute_similarities": attribute_sim,
            "type_consistency": True,  # Simplified
        }

    # Contextual consistency check
    if contextual:
        archetypes = contextual.get("archetypes_together", [])
        formats = contextual.get("formats_together", [])
        
        # If context_dependent is True, should have specific archetypes/formats
        if annotation.get("context_dependent", False):
            if not archetypes and not formats:
                validation["warnings"].append(
                    "Context-dependent but no archetype/format context found"
                )
        
        validation["contextual_consistency"] = {
            "archetypes": archetypes,
            "formats": formats,
            "has_context": len(archetypes) > 0 or len(formats) > 0,
        }

    if validation["warnings"]:
        validation["is_valid"] = False

    return validation


def format_enriched_annotation_for_display(
    annotation: dict[str, Any],
) -> str:
    """Format enriched annotation for human-readable display."""
    card1 = annotation.get("card1", "?")
    card2 = annotation.get("card2", "?")
    score = annotation.get("similarity_score", 0.0)
    sim_type = annotation.get("similarity_type", "unknown")
    is_sub = annotation.get("is_substitute", False)
    
    lines = [
        f"Similarity: {card1} ↔ {card2}",
        f"  Score: {score:.2f} ({sim_type})",
        f"  Substitutable: {is_sub}",
    ]
    
    # Add graph features
    graph_features = extract_graph_features_from_annotation(annotation)
    if graph_features:
        jaccard = graph_features.get("jaccard_similarity", 0.0)
        cooccur = graph_features.get("cooccurrence_count", 0)
        lines.append(f"  Graph: Jaccard={jaccard:.3f}, Co-occurrence={cooccur}")
    
    # Add contextual info
    contextual = extract_contextual_analysis_from_annotation(annotation)
    if contextual:
        archetypes = contextual.get("archetypes_together", [])
        if archetypes:
            lines.append(f"  Archetypes: {', '.join(archetypes[:3])}")
    
    return "\n".join(lines)


def filter_annotations_by_graph_quality(
    annotations: list[dict[str, Any]],
    min_jaccard: float = 0.0,
    min_cooccurrence: int = 0,
) -> list[dict[str, Any]]:
    """Filter annotations by graph quality metrics."""
    filtered = []
    for ann in annotations:
        graph_features = extract_graph_features_from_annotation(ann)
        if not graph_features:
            continue
        
        jaccard = graph_features.get("jaccard_similarity", 0.0)
        cooccur = graph_features.get("cooccurrence_count", 0)
        
        if jaccard >= min_jaccard and cooccur >= min_cooccurrence:
            filtered.append(ann)
    
    return filtered


def get_enrichment_summary(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Get summary statistics about annotation enrichment."""
    total = len(annotations)
    with_graph = 0
    with_attributes = 0
    with_context = 0
    
    jaccard_scores = []
    cooccurrence_counts = []
    
    for ann in annotations:
        if extract_graph_features_from_annotation(ann):
            with_graph += 1
            graph_features = extract_graph_features_from_annotation(ann)
            if graph_features:
                jaccard = graph_features.get("jaccard_similarity", 0.0)
                cooccur = graph_features.get("cooccurrence_count", 0)
                if jaccard > 0:
                    jaccard_scores.append(jaccard)
                if cooccur > 0:
                    cooccurrence_counts.append(cooccur)
        
        if extract_card_comparison_from_annotation(ann):
            with_attributes += 1
        
        if extract_contextual_analysis_from_annotation(ann):
            with_context += 1
    
    summary = {
        "total": total,
        "with_graph_features": with_graph,
        "with_card_attributes": with_attributes,
        "with_contextual_analysis": with_context,
        "enrichment_rate": {
            "graph": with_graph / total if total > 0 else 0.0,
            "attributes": with_attributes / total if total > 0 else 0.0,
            "context": with_context / total if total > 0 else 0.0,
        },
    }
    
    if jaccard_scores:
        summary["jaccard_stats"] = {
            "mean": sum(jaccard_scores) / len(jaccard_scores),
            "min": min(jaccard_scores),
            "max": max(jaccard_scores),
        }
    
    if cooccurrence_counts:
        summary["cooccurrence_stats"] = {
            "mean": sum(cooccurrence_counts) / len(cooccurrence_counts),
            "min": min(cooccurrence_counts),
            "max": max(cooccurrence_counts),
        }
    
    return summary


