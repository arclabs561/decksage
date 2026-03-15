"""
Pydantic models, ApiState dataclass, and get_state helper for the DeckSage API.

Extracted from api.py to reduce monolith size. All model definitions live here;
endpoint handlers remain in api.py.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# deck_patch module - optional dependency (needed for PatchRequest type annotation)
try:
    from ..deck_building.deck_patch import DeckPatch
except ImportError:
    DeckPatch = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Multi-game support (shared constant)
# ---------------------------------------------------------------------------

SUPPORTED_GAMES: set[str] = {"magic", "pokemon", "yugioh"}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SimilarCard(BaseModel):
    card: str = Field(..., description="Card name")
    similarity: float = Field(..., description="Similarity score, clamped to [0, 1]")
    metadata: dict[str, Any] | None = Field(
        None, description="Card metadata (image_url, type, mana_cost, etc.)"
    )


class UseCaseEnum(str, Enum):
    substitute = "substitute"
    synergy = "synergy"
    meta = "meta"


class SimilarityRequest(BaseModel):
    game: str | None = Field(None, description="Game name (magic, yugioh, pokemon)")
    query: str = Field(..., description="Query card name")
    top_k: int = Field(10, ge=1, le=100, description="Number of results")
    use_case: UseCaseEnum = Field(
        UseCaseEnum.substitute,
        description="Use case: 'substitute' (functional replacements), 'synergy' (co-occurrence partners), 'meta' (popular pairings; currently maps to co-occurrence)",
    )
    mode: str | None = Field(
        None,
        description="Optional override: 'embedding', 'jaccard', 'jaccard_faceted', or 'fusion'",
    )
    weights: dict[str, float] | None = Field(
        None,
        description="Optional fusion weights {embed, jaccard, functional, text_embed, sideboard, temporal, gnn, archetype, format}; will be normalized",
    )
    aggregator: str | None = Field(
        None,
        description="Fusion aggregator: 'rrf' (default), 'isr', 'weighted', 'combsum', 'combmnz', 'combmax', 'combmin'",
    )
    rrf_k: int | None = Field(
        None,
        ge=1,
        description="RRF constant k0 (typical 60). Only used when aggregator='rrf'",
    )
    mmr_lambda: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="MMR diversification strength in [0,1]; 0 disables",
    )
    also_like: list[str] | None = Field(
        None,
        description="Optional additional queries to fuse with the main query (multi-query fusion)",
    )
    facet: str | None = Field(
        None,
        description="Facet for jaccard_faceted: 'type' or 'cmc'",
    )


class SimilarityResponse(BaseModel):
    query: str
    query_metadata: dict[str, Any] | None = Field(
        None, description="Metadata for the query card (image_url, type, etc.)"
    )
    results: list[SimilarCard]
    model_info: dict[str, Any] = Field(
        default_factory=dict,
        description="Model metadata (vocab_size, dimension, method, game, etc.)",
    )
    feedback_url: str | None = Field(None, description="URL for submitting feedback on results")


class HealthResponse(BaseModel):
    status: str
    game: str
    num_cards: int
    embedding_dim: int


class CardSuggestion(BaseModel):
    name: str
    image_url: str | None = None
    type_line: str | None = None  # "type" for Pokemon/YGO, "type_line" for Magic
    rarity: str | None = None
    total_decks: int | None = None
    ban_status: dict[str, str] | None = None  # {format: "banned"|"restricted"|...}
    # Game-specific fields (populated per-game, None for others)
    mana_cost: str | None = None  # Magic only
    colors: str | None = None  # Magic only
    attribute: str | None = None  # YGO only
    hp: int | None = None  # Pokemon only


class CardsResponse(BaseModel):
    items: list[CardSuggestion]
    total: int
    next_offset: int | None = None


class ContextualItem(BaseModel):
    card: str = Field(..., description="Card name")
    similarity: float = Field(..., description="Similarity score")
    metadata: dict[str, Any] | None = None


class ContextualResponse(BaseModel):
    synergies: list[ContextualItem | dict] = Field(default_factory=list)
    alternatives: list[ContextualItem | dict] = Field(default_factory=list)
    upgrades: list[ContextualItem | dict] = Field(default_factory=list)
    downgrades: list[ContextualItem | dict] = Field(default_factory=list)
    feedback_url: str | None = Field(None, description="URL for submitting feedback on suggestions")


class SearchRequest(BaseModel):
    game: str | None = Field(None, description="Game name (magic, yugioh, pokemon)")
    query: str = Field(..., description="Search query text")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")
    text_weight: float = Field(0.5, ge=0.0, le=1.0, description="Weight for text search (0-1)")
    vector_weight: float = Field(0.5, ge=0.0, le=1.0, description="Weight for vector search (0-1)")


class SearchResultItem(BaseModel):
    card_name: str = Field(..., description="Card name")
    score: float = Field(..., description="Search score")
    source: str = Field(..., description="Source: meilisearch, qdrant, or hybrid")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class SearchResponse(BaseModel):
    query: str = Field(..., description="Original query")
    results: list[SearchResultItem] = Field(..., description="Search results")
    total: int = Field(..., description="Total number of results")


class PatchRequest(BaseModel):
    game: str = Field(..., description="magic|yugioh|pokemon")
    deck: dict = Field(..., description="Deck object matching validators schema")
    patch: DeckPatch
    strict_size: bool | None = Field(None, description="If true, enforce size constraints")
    check_legality: bool | None = Field(None, description="If true, enforce banlist legality")


class SuggestActionsRequest(BaseModel):
    game: str
    deck: dict
    seed_card: str | None = None
    top_k: int = 20
    mode: str | None = None  # embedding|jaccard|fusion
    budget_max: float | None = None
    coverage_weight: float | None = None
    tag_weights: dict[str, float] | None = None  # optional per-tag weights
    curve_weight: float | None = None
    curve_target: dict[int, float] | None = None  # desired CMC distribution
    archetype: str | None = None  # Archetype name for context-aware suggestions
    action_type: str = "add"  # add|remove|replace|suggest (suggest = all)


class SuggestedAction(BaseModel):
    op: str  # add_card|remove_card|replace_card
    partition: str
    card: str
    count: int = 1
    score: float
    reason: str | None = None
    target: str | None = None  # For replace_card: card to replace


class SuggestActionsResponse(BaseModel):
    actions: list[SuggestedAction]
    metrics: dict | None = None
    feedback_url: str | None = Field(None, description="URL for submitting feedback on suggestions")


class CompleteRequest(BaseModel):
    game: str
    deck: dict
    target_main_size: int | None = None
    mode: str | None = None
    max_steps: int = Field(60, le=200)
    budget_max: float | None = None
    coverage_weight: float | None = None
    strict_size: bool | None = None
    check_legality: bool | None = None
    method: str = "greedy"  # "greedy", "beam", or "ot"
    beam_width: int = Field(5, ge=1, le=50)  # For beam search
    # OT-specific parameters
    sinkhorn_reg: float = 0.01  # Entropic regularization for OT
    embedding_weight: float = 0.3  # Cost weight for embedding distance
    role_weight: float = 0.1  # Cost weight for role gap filling
    curve_weight: float = 0.6  # Cost weight for mana curve fit


class CompleteResponse(BaseModel):
    deck: dict
    steps: list[dict]
    metrics: dict | None = None
    feedback_url: str | None = Field(None, description="URL for submitting feedback on completion")


# ---------------------------------------------------------------------------
# ApiState (runtime state per game, not a Pydantic model)
# ---------------------------------------------------------------------------


class ApiState:
    def __init__(self) -> None:
        self.embeddings: Any = None  # KeyedVectors | None (gensim optional)
        self.graph_data: dict | None = None
        self.model_info: dict = {}
        self.fusion_default_weights: Any = None  # FusionWeights | None
        self.card_attrs: dict | None = None
        # Optional signal providers (loaded by load_signals_to_state)
        self.sideboard_cooccurrence: dict[str, dict[str, float]] | None = None
        self.temporal_cooccurrence: dict[str, dict[str, dict[str, float]]] | None = None
        self.text_embedder: object | None = None
        self.visual_embedder: object | None = None
        self.gnn_embedder: object | None = None
        self.archetype_staples: dict[str, dict[str, float]] | None = None
        self.archetype_cooccurrence: dict[str, dict[str, float]] | None = None
        self.format_cooccurrence: dict[str, dict[str, dict[str, float]]] | None = None
        self.cross_format_patterns: dict[str, dict[str, float]] | None = None
        self.signal_status: dict[str, bool] | None = None  # Signal loading status
        self.reranker: object | None = None  # Learned reranker (optional)
        self.card_metadata: dict[str, dict[str, Any]] | None = None  # Full card attrs w/ image_url
        # Enrichment data (loaded from data/ assets)
        self.banlist: dict[str, dict[str, list[str]]] | None = None  # {format: {status: [cards]}}
        self.archetypes: dict[str, list[str]] | None = None  # {card_name: [archetype_names]}
        self.deck_frequency: dict[str, dict] | None = None  # {card_name: {total_decks, by_format}}


# ---------------------------------------------------------------------------
# get_state helper
# ---------------------------------------------------------------------------


def _normalize_game(game: str | None) -> str | None:
    if game is None:
        return None
    g = str(game).strip().lower()
    return g or None


def get_state(game: str | None = None) -> ApiState:
    """
    Get (or create) the API state for a specific game.

    In single-game mode, callers may omit `game` and the default game is used.
    In multi-game mode, request handlers should call `_require_game(...)` and
    pass the resolved game here.
    """
    # Lazy import to avoid circular dependency (app is defined in api.py)
    from .api import _default_game, app

    # Store per-game state in app.state
    by_game = getattr(app.state, "api_by_game", None)
    if by_game is None:
        by_game = {}
        app.state.api_by_game = by_game

    g = _normalize_game(game) or _default_game()
    if g not in SUPPORTED_GAMES:
        # Keep this as ValueError (not HTTPException) so non-request call sites
        # don't accidentally turn into 4xx responses.
        raise ValueError(f"Unknown game: {game}")

    state = by_game.get(g)
    if state is None:
        state = ApiState()
        by_game[g] = state
    return state
