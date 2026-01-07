"""Annotation validation utilities inspired by graph validator agent.

Provides systematic validation similar to agentic_qa_agent for annotations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Lazy import to avoid pandas dependency
try:
    from ml.utils.enriched_annotation_utils import validate_annotation_against_graph
    HAS_ENRICHED_UTILS = True
except ImportError:
    HAS_ENRICHED_UTILS = False


@dataclass
class AnnotationValidationResult:
    """Result of annotation validation."""
    
    is_valid: bool
    warnings: list[str]
    errors: list[str]
    graph_consistency: dict[str, Any] | None = None
    score_calibration: dict[str, Any] | None = None
    reasoning_consistency: dict[str, Any] | None = None


def validate_annotation_comprehensive(
    annotation: dict[str, Any],
    previous_annotations: list[dict[str, Any]] | None = None,
) -> AnnotationValidationResult:
    """Comprehensive annotation validation (similar to graph quality agent).
    
    Checks:
    1. Graph consistency (score vs Jaccard alignment)
    2. Score calibration (appropriate range usage)
    3. Reasoning consistency (score matches explanation)
    4. Distribution check (not clustering with previous annotations)
    """
    warnings = []
    errors = []
    
    # 1. Graph consistency (from enriched_annotation_utils)
    graph_consistency = None
    if HAS_ENRICHED_UTILS:
        try:
            graph_validation = validate_annotation_against_graph(annotation)
            graph_consistency = graph_validation.get("graph_consistency")
            
            if graph_validation.get("warnings"):
                warnings.extend(graph_validation["warnings"])
        except Exception:
            # If graph validation fails, continue without it
            pass
    else:
        # Fallback: basic graph consistency check
        graph_features = annotation.get("graph_features", {})
        if isinstance(graph_features, dict):
            jaccard = graph_features.get("jaccard_similarity")
            similarity_score = annotation.get("similarity_score")
            if jaccard is not None and similarity_score is not None:
                # Basic consistency check
                if similarity_score > 0.7 and jaccard < 0.3:
                    warnings.append(
                        f"High similarity ({similarity_score:.2f}) but low Jaccard ({jaccard:.2f})"
                    )
                elif similarity_score < 0.3 and jaccard > 0.7:
                    warnings.append(
                        f"Low similarity ({similarity_score:.2f}) but high Jaccard ({jaccard:.2f})"
                    )
                graph_consistency = {
                    "jaccard": jaccard,
                    "score_alignment": abs(similarity_score - jaccard) < 0.3,
                }
    
    # 2. Score calibration check
    similarity_score = annotation.get("similarity_score")
    score_calibration = None
    
    if similarity_score is not None:
        # Check if score is in appropriate range
        if similarity_score < 0.0 or similarity_score > 1.0:
            errors.append(f"Invalid similarity_score: {similarity_score} (must be 0.0-1.0)")
        
        # Check for clustering indicators
        if similarity_score < 0.1:
            warnings.append(f"Very low score ({similarity_score:.2f}) - verify this is truly unrelated")
        elif 0.1 <= similarity_score < 0.2:
            warnings.append(f"Low score ({similarity_score:.2f}) - ensure not defaulting to low range")
        
        score_calibration = {
            "score": similarity_score,
            "range": _get_score_range(similarity_score),
            "is_extreme": similarity_score < 0.1 or similarity_score > 0.9,
        }
    
    # 3. Reasoning consistency check
    reasoning = annotation.get("reasoning", "")
    reasoning_consistency = None
    
    if reasoning and similarity_score is not None:
        # Check for contradictions
        contradictions = []
        
        # Check if reasoning mentions high similarity but score is low
        high_sim_keywords = ["same function", "same role", "similar effect", "substitute", "interchangeable"]
        if any(kw in reasoning.lower() for kw in high_sim_keywords) and similarity_score < 0.5:
            contradictions.append(
                f"Reasoning mentions high similarity but score is low ({similarity_score:.2f})"
            )
        
        # Check if reasoning mentions archetype but score is very low
        archetype_keywords = ["same archetype", "same deck", "same strategy", "thematic"]
        if any(kw in reasoning.lower() for kw in archetype_keywords) and similarity_score < 0.3:
            contradictions.append(
                f"Reasoning mentions shared archetype but score is very low ({similarity_score:.2f})"
            )
        
        # Check if reasoning mentions unrelated but score is moderate
        unrelated_keywords = ["unrelated", "different", "no connection", "distinct"]
        if any(kw in reasoning.lower() for kw in unrelated_keywords) and similarity_score > 0.3:
            contradictions.append(
                f"Reasoning mentions unrelated but score is moderate ({similarity_score:.2f})"
            )
        
        if contradictions:
            warnings.extend(contradictions)
        
        reasoning_consistency = {
            "has_contradictions": len(contradictions) > 0,
            "reasoning_length": len(reasoning),
            "mentions_archetype": any(kw in reasoning.lower() for kw in archetype_keywords),
            "mentions_function": any(kw in reasoning.lower() for kw in high_sim_keywords),
        }
    
    # 4. Distribution check (compare with previous annotations)
    distribution_warning = None
    if previous_annotations and similarity_score is not None:
        recent_scores = [
            a.get("similarity_score")
            for a in previous_annotations[-10:]  # Last 10
            if a.get("similarity_score") is not None
        ]
        
        if recent_scores:
            # Check if clustering in low range
            low_range_count = sum(1 for s in recent_scores if s < 0.2)
            if low_range_count >= 8:  # 80% in low range
                distribution_warning = (
                    f"Score clustering detected: {low_range_count}/{len(recent_scores)} "
                    f"recent scores in 0.0-0.2 range"
                )
                warnings.append(distribution_warning)
    
    is_valid = len(errors) == 0
    
    return AnnotationValidationResult(
        is_valid=is_valid,
        warnings=warnings,
        errors=errors,
        graph_consistency=graph_consistency,
        score_calibration=score_calibration,
        reasoning_consistency=reasoning_consistency,
    )


def _get_score_range(score: float) -> str:
    """Get score range label."""
    if score >= 0.8:
        return "high"
    elif score >= 0.6:
        return "strong"
    elif score >= 0.4:
        return "moderate"
    elif score >= 0.2:
        return "weak"
    else:
        return "very_low"

