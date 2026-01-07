"""Enriched annotation models with graph DB context.

Extends basic annotations with:
- Graph-derived features (Jaccard, co-occurrence, graph distance)
- Card attribute comparison
- Contextual analysis (archetype, format, temporal)
- Rich text explanations
- Multi-faceted similarity breakdown
"""

from __future__ import annotations

from typing import Any

try:
    from pydantic import BaseModel, Field

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    BaseModel = object  # type: ignore
    Field = lambda **kwargs: lambda x: x  # type: ignore


class GraphFeatures(BaseModel):
    """Graph-derived similarity features."""

    cooccurrence_count: int = Field(
        default=0, description="Number of decks they appear together"
    )
    cooccurrence_frequency: float = Field(
        default=0.0, description="Frequency (0-1) of co-occurrence"
    )
    jaccard_similarity: float = Field(
        default=0.0, description="Jaccard similarity of neighbor sets"
    )
    graph_distance: int | None = Field(
        None, description="Shortest path in graph (None if disconnected)"
    )
    common_neighbors: int = Field(default=0, description="Number of shared neighbors")
    total_neighbors_card1: int = Field(default=0, description="Degree of card1")
    total_neighbors_card2: int = Field(default=0, description="Degree of card2")
    clustering_coefficient: float | None = Field(
        None, description="Local clustering coefficient"
    )
    edge_weight: int | None = Field(None, description="Direct edge weight if exists")


class CardAttributes(BaseModel):
    """Card attribute data."""

    mana_cost: str | None = None
    cmc: float | None = None
    color_identity: list[str] = Field(default_factory=list)
    type: str | None = None
    subtypes: list[str] = Field(default_factory=list)
    power: str | None = None
    toughness: str | None = None
    oracle_text: str | None = None
    keywords: list[str] = Field(default_factory=list)
    rarity: str | None = None


class CardComparison(BaseModel):
    """Side-by-side card attribute comparison."""

    card1_attrs: CardAttributes
    card2_attrs: CardAttributes
    attribute_similarity: dict[str, float] = Field(
        default_factory=dict, description="Similarity per attribute (mana_cost, type, etc.)"
    )
    functional_overlap: list[str] = Field(
        default_factory=list, description="Shared functional tags/keywords"
    )
    differences: list[str] = Field(
        default_factory=list, description="Key differences (e.g., 'card1 is instant, card2 is sorcery')"
    )


class TournamentContext(BaseModel):
    """Tournament-specific co-occurrence patterns."""

    top8_appearances: int = Field(
        default=0, description="Number of top 8 finishes together"
    )
    win_rate_together: float | None = Field(
        None, description="Win rate when both present"
    )
    placement_distribution: dict[str, int] = Field(
        default_factory=dict, description="Placement distribution (1st, 2nd, etc.)"
    )


class ContextualAnalysis(BaseModel):
    """Context-specific similarity analysis."""

    archetypes_together: list[str] = Field(
        default_factory=list, description="Archetypes where both cards appear"
    )
    archetype_specificity: float = Field(
        default=0.0, description="How archetype-specific this relationship is (0-1)"
    )
    formats_together: list[str] = Field(
        default_factory=list, description="Formats where both cards appear together"
    )
    format_specificity: float = Field(
        default=0.0, description="How format-specific this relationship is (0-1)"
    )
    temporal_trend: str = Field(
        default="unknown",
        description="Temporal pattern: 'increasing', 'decreasing', 'stable', 'seasonal'",
    )
    peak_periods: list[str] = Field(
        default_factory=list, description="Time periods when co-occurrence was highest"
    )
    tournament_context: TournamentContext | None = Field(
        None, description="Tournament-specific patterns"
    )


class MultiFacetedAnalysis(BaseModel):
    """Breakdown by different similarity dimensions."""

    functional_similarity: float = Field(
        default=0.0, description="Same role/function (0-1)"
    )
    synergy_similarity: float = Field(
        default=0.0, description="Work well together (0-1)"
    )
    manabase_similarity: float = Field(
        default=0.0, description="Similar mana requirements (0-1)"
    )
    archetype_similarity: float = Field(
        default=0.0, description="Same archetype fit (0-1)"
    )
    temporal_similarity: float = Field(
        default=0.0, description="Similar meta timing (0-1)"
    )
    format_similarity: float = Field(
        default=0.0, description="Same format usage (0-1)"
    )
    power_level_similarity: float = Field(
        default=0.0, description="Similar power level (0-1)"
    )
    explanation_per_facet: dict[str, str] = Field(
        default_factory=dict, description="Explanation for each similarity dimension"
    )


class DetailedExplanation(BaseModel):
    """Rich text explanation using graph data."""

    summary: str = Field(
        default="", description="One-sentence summary"
    )
    graph_evidence: str = Field(
        default="", description="Evidence from graph (co-occurrence, Jaccard, etc.)"
    )
    attribute_analysis: str = Field(
        default="", description="Attribute-based comparison"
    )
    contextual_factors: str = Field(
        default="", description="Archetype, format, temporal context"
    )
    substitution_analysis: str = Field(
        default="", description="When/why substitution works or doesn't"
    )
    trade_offs: str = Field(
        default="", description="What you gain/lose by substituting"
    )
    use_cases: list[str] = Field(
        default_factory=list, description="Specific scenarios where relationship matters"
    )
    counter_examples: list[str] = Field(
        default_factory=list, description="When relationship doesn't hold"
    )


class EnrichedCardSimilarityAnnotation(BaseModel):
    """Rich similarity annotation with graph DB context.

    Extends CardSimilarityAnnotation with graph-derived features,
    card attribute comparison, contextual analysis, and rich explanations.
    """

    # Core fields (from CardSimilarityAnnotation)
    card1: str
    card2: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    similarity_type: str
    reasoning: str
    is_substitute: bool
    context_dependent: bool = Field(default=False)
    example_decks: list[str] = Field(default_factory=list)

    # NEW: Graph-derived features
    graph_features: GraphFeatures | None = Field(
        None, description="Graph metrics and co-occurrence statistics"
    )

    # NEW: Card attributes comparison
    card_comparison: CardComparison | None = Field(
        None, description="Side-by-side card attribute comparison"
    )

    # NEW: Contextual analysis
    contextual_analysis: ContextualAnalysis | None = Field(
        None, description="Archetype, format, and temporal context"
    )

    # NEW: Rich text explanations
    detailed_explanation: DetailedExplanation | None = Field(
        None, description="Comprehensive explanation using graph data"
    )

    # NEW: Multi-faceted analysis
    facets: MultiFacetedAnalysis | None = Field(
        None, description="Breakdown by different similarity dimensions"
    )

    # NEW: Visual features
    visual_features: dict[str, Any] | None = Field(
        None,
        description="Visual embedding features (embedding vector, similarity score, model name, image URL)",
    )

    # Metadata (from CardSimilarityAnnotation)
    model_name: str | None = None
    model_params: dict[str, Any] | None = None
    prompt_hash: str | None = None
    annotator_id: str | None = None
    timestamp: str | None = None
    game: str | None = None


