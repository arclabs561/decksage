#!/usr/bin/env python3
"""
FastAPI Similarity Service

Minimal, honest API for card similarity search. Routes are versioned under /v1.

Usage:
    # Repo layout (from project root):
    uvicorn src.ml.api.api:app --reload
    python -m src.ml.api.api --embeddings /path/to/model.wv --port 8000

    # Installed package layout (site-packages):
    uvicorn ml.api.api:app --reload
    python -m ml.api.api --embeddings /path/to/model.wv --port 8000

    # Or via console script after install:
    decksage-api --embeddings /path/to/model.wv --port 8000
"""

import argparse
import json
import logging
import os
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Local application imports
from ..deck_building.deck_completion import (
    CompletionConfig,
    greedy_complete,
    suggest_additions,
)


# deck_patch module - optional dependency
try:
    from ..deck_building.deck_patch import DeckPatch, DeckPatchResult, apply_deck_patch
except ImportError:
    DeckPatch = None
    DeckPatchResult = None
    apply_deck_patch = None
from ..similarity.fusion import FusionWeights, WeightedLateFusion
from ..similarity.similarity_methods import (
    jaccard_similarity as sm_jaccard,
)
from ..similarity.similarity_methods import (
    load_graph as sm_load_graph,
)
from ..utils.paths import PATHS


# Search integration
try:
    from ..search import HybridSearch

    HAS_SEARCH = True
except ImportError:
    HybridSearch = None
    HAS_SEARCH = False

# Optional dependencies with graceful degradation
try:
    import uvicorn  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    uvicorn = None  # type: ignore[assignment]

try:
    from gensim.models import KeyedVectors

    HAS_GENSIM = True
except ImportError:  # pragma: no cover
    KeyedVectors = None  # type: ignore[assignment]
    HAS_GENSIM = False

try:
    from ..enrichment.card_functional_tagger import (
        FunctionalTagger,  # type: ignore[import-not-found]
    )
except Exception:  # pragma: no cover
    FunctionalTagger = None  # type: ignore[assignment]

try:
    from ..similarity.similarity_methods import (
        jaccard_similarity_faceted as sm_jaccard_faceted,
    )
    from ..similarity.similarity_methods import (
        load_card_attributes_csv as sm_load_attrs,
    )
except Exception:  # pragma: no cover
    sm_load_attrs = None  # type: ignore
    sm_jaccard_faceted = None  # type: ignore

# Note: dotenv is loaded twice intentionally: once early for CORS/env-driven config
# and again inside lifespan to catch late environment overrides in tests.

try:
    from ..utils.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger("decksage.api")

if not HAS_GENSIM:
    logger.warning("gensim is not installed; embedding features will be unavailable")


# Models
class SimilarCard(BaseModel):
    card: str = Field(..., description="Card name")
    similarity: float = Field(..., description="Similarity score (0-1)")


class UseCaseEnum(str, Enum):
    substitute = "substitute"
    synergy = "synergy"
    meta = "meta"


class SimilarityRequest(BaseModel):
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
        description="Fusion aggregator: 'weighted' (default), 'rrf', 'combsum', or 'combmnz'",
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
    results: list[SimilarCard]
    model_info: dict
    feedback_url: str | None = Field(None, description="URL for submitting feedback on results")


class HealthResponse(BaseModel):
    status: str
    num_cards: int
    embedding_dim: int


class CardsResponse(BaseModel):
    items: list[str]
    total: int
    next_offset: int | None = None


class ContextualResponse(BaseModel):
    synergies: list[dict]
    alternatives: list[dict]
    upgrades: list[dict]
    downgrades: list[dict]
    feedback_url: str | None = Field(None, description="URL for submitting feedback on suggestions")


class ApiState:
    def __init__(self) -> None:
        self.embeddings: object | None = None
        self.graph_data: dict | None = None
        self.model_info: dict = {}
        self.fusion_default_weights: FusionWeights | None = None
        self.card_attrs: dict | None = None
        # New signals
        self.sideboard_cooccurrence: dict[str, dict[str, float]] | None = None
        self.temporal_cooccurrence: dict[str, dict[str, dict[str, float]]] | None = None
        self.text_embedder: object | None = None
        self.gnn_embedder: object | None = None
        # New signals
        self.archetype_staples: dict[str, dict[str, float]] | None = None
        self.archetype_cooccurrence: dict[str, dict[str, float]] | None = None
        self.format_cooccurrence: dict[str, dict[str, dict[str, float]]] | None = None
        self.cross_format_patterns: dict[str, dict[str, float]] | None = None


def get_state() -> ApiState:
    state = getattr(app.state, "api", None)
    if state is None:
        state = ApiState()
        app.state.api = state
    return state


def load_embeddings_to_state(emb_path: str, pairs_csv: str | None = None) -> None:
    """Load embeddings and graph data into app.state.api."""
    state = get_state()
    logger.info("Loading embeddings from %s...", emb_path)
    emb = KeyedVectors.load(emb_path)
    state.embeddings = emb
    state.model_info = {
        "num_cards": len(emb),
        "embedding_dim": emb.vector_size,
        "model_path": emb_path,
        "methods": ["embedding"],
    }
    logger.info("Loaded %s cards (%sD)", f"{len(emb):,}", emb.vector_size)
    if pairs_csv:
        logger.info("Loading graph from %s...", pairs_csv)
        adj, weights = sm_load_graph(pairs_csv, filter_lands=True)
        state.graph_data = {"adj": adj, "weights": weights}
        state.model_info["methods"].append("jaccard")
        logger.info("Loaded graph: %s cards, %s weights", f"{len(adj):,}", f"{len(weights):,}")

    # Load tuned fusion weights if available (non-fatal)
    # Try optimized_fusion_weights_latest.json first (from evaluation), then fusion_grid_search_latest.json
    try:
        weights_path = PATHS.experiments / "optimized_fusion_weights_latest.json"
        if not weights_path.exists():
            weights_path = PATHS.experiments / "fusion_grid_search_latest.json"

        if weights_path.exists():
            with open(weights_path) as fh:
                data = json.load(fh)

            # Handle both formats
            if "recommendation" in data:
                rec = data["recommendation"]
                fw = FusionWeights(
                    embed=float(rec.get("embed", 0.25)),
                    jaccard=float(rec.get("jaccard", 0.75)),
                    functional=float(rec.get("functional", 0.0)),
                    text_embed=float(rec.get("text_embed", 0.0)),
                    sideboard=float(rec.get("sideboard", 0.0)),
                    temporal=float(rec.get("temporal", 0.0)),
                    gnn=float(rec.get("gnn", 0.0)),
                    archetype=float(rec.get("archetype", 0.0)),
                    format=float(rec.get("format", 0.0)),
                ).normalized()
            else:
                # Legacy format - include all weight fields for hybrid system compatibility
                # Use recommended defaults if legacy format missing fields
                bw = data.get("best_weights", {})
                fw = FusionWeights(
                    embed=float(
                        bw.get("embed", 0.20)
                    ),  # Co-occurrence (default from recommended weights)
                    jaccard=float(
                        bw.get("jaccard", 0.15)
                    ),  # Jaccard (default from recommended weights)
                    functional=float(
                        bw.get("functional", 0.10)
                    ),  # Functional (default from recommended weights)
                    text_embed=float(
                        bw.get("text_embed", 0.25)
                    ),  # Instruction-tuned (default from recommended weights)
                    sideboard=float(bw.get("sideboard", 0.0)),
                    temporal=float(bw.get("temporal", 0.0)),
                    gnn=float(bw.get("gnn", 0.30)),  # GNN (default from recommended weights)
                    archetype=float(bw.get("archetype", 0.0)),
                    format=float(bw.get("format", 0.0)),
                ).normalized()

            state.fusion_default_weights = fw
            state.model_info["fusion_default_weights"] = {
                "embed": fw.embed,
                "jaccard": fw.jaccard,
                "functional": fw.functional,
            }
            logger.info(
                "Loaded tuned fusion weights: embed=%.2f, jaccard=%.2f, functional=%.2f, text_embed=%.2f, gnn=%.2f",
                fw.embed,
                fw.jaccard,
                fw.functional,
                fw.text_embed,
                fw.gnn,
            )
    except Exception:
        logger.debug("No tuned fusion weights loaded", exc_info=True)


# Legacy globals for backward compatibility in tests
embeddings = None
graph_data = None
model_info = {}


def _adopt_legacy_globals() -> None:
    """If legacy module-level globals are set (by tests), copy them into ApiState."""
    state = get_state()
    global embeddings, graph_data, model_info
    if state.embeddings is None and embeddings is not None:
        state.embeddings = embeddings
        if not state.model_info:
            state.model_info = {
                "methods": ["embedding"],
                "num_cards": len(embeddings),
                "embedding_dim": getattr(embeddings, "vector_size", 0),
            }  # type: ignore[arg-type]
    if state.graph_data is None and graph_data is not None:
        state.graph_data = graph_data
        if "methods" in state.model_info and "jaccard" not in state.model_info["methods"]:
            state.model_info["methods"].append("jaccard")


# API app with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler: load resources on startup, free on shutdown."""
    # Load environment variables lazily (respects test-time monkeypatching)
    try:
        load_dotenv()
    except Exception:
        pass
    emb_path = os.getenv("EMBEDDINGS_PATH")
    pairs_path = os.getenv("PAIRS_PATH")
    attrs_path = os.getenv("ATTRIBUTES_PATH")
    if emb_path:
        if not HAS_GENSIM:
            logger.error("gensim is not installed; cannot load embeddings from %s", emb_path)
        else:
            try:
                load_embeddings_to_state(emb_path, pairs_path)
            except Exception:
                logger.exception("Failed to load embeddings/graph during startup")
    else:
        logger.info("EMBEDDINGS_PATH not set; service will start but /ready returns 503")
    # Optional attributes CSV
    if attrs_path and sm_load_attrs is not None and os.path.exists(attrs_path):
        try:
            state = get_state()
            state.card_attrs = sm_load_attrs(attrs_path)
            logger.info(
                "Loaded card attributes from %s (count=%d)", attrs_path, len(state.card_attrs)
            )
        except Exception:
            logger.exception("Failed to load attributes CSV: %s", attrs_path)
    # Load additional signals (sideboard, temporal, GNN, text embeddings)
    try:
        from .load_signals import load_signals_to_state

        text_embedder_model = os.getenv("TEXT_EMBEDDER_MODEL", "all-MiniLM-L6-v2")
        load_signals_to_state(text_embedder_model=text_embedder_model)
    except Exception:
        logger.debug("Failed to load additional signals (this is optional)", exc_info=True)
    try:
        yield
    finally:
        # Best-effort cleanup
        state = get_state()
        state.embeddings = None
        state.graph_data = None
        state.card_attrs = None
        # Clear optional app-scoped helpers if they were created
        try:
            delattr(app.state, "price_manager")
        except Exception:
            pass
        try:
            delattr(app.state, "mtg_tagger")
        except Exception:
            pass


# Ensure env is loaded early so CORS and other env-driven settings are honored
try:
    load_dotenv()
except Exception:
    pass

app = FastAPI(
    title="DeckSage Similarity API",
    description="Card similarity search using graph embeddings",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for web frontends (env-driven)
# SECURITY: Default to empty list (no CORS) unless explicitly configured
# Use CORS_ORIGINS env var to specify allowed origins (comma-separated)
# Example: CORS_ORIGINS=http://localhost:3000,https://decksage.com
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
_parsed = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
if (not _parsed) or ("*" in _parsed):
    # Only allow * in development - warn in production
    if os.getenv("ENVIRONMENT", "development") == "production" and "*" in _parsed:
        logger.warning("CORS_ORIGINS='*' is insecure for production. Specify exact origins.")
    _cors_origins = ["*"] if _parsed and "*" in _parsed else []
else:
    _cors_origins = _parsed
_allow_credentials = _cors_origins != ["*"] and len(_cors_origins) > 0
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


## startup event replaced by lifespan


# Root route - serve HTML landing page or JSON based on Accept header
@app.get("/")
def root(request: Request):
    """Root endpoint - serves HTML landing page or JSON API info."""
    accept = request.headers.get("accept", "").lower()
    # Browsers send "text/html" or "*/*", API clients send "application/json"
    # Default to HTML unless explicitly requesting JSON
    wants_json = "application/json" in accept and "text/html" not in accept

    # Serve HTML for browsers (default)
    if not wants_json:
        # Serve HTML landing page for browsers
        _landing_html = Path(__file__).parent.parent.parent.parent / "test_search.html"
        if _landing_html.exists():
            return FileResponse(str(_landing_html), media_type="text/html")
        # Fallback to redirect
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/search.html")

    # Return JSON for API clients that explicitly request it
    return {
        "name": "DeckSage Similarity API",
        "version": "0.1.0",
        "docs": "/docs",
        "search_ui": "/search.html",
        "health": "/health",
        "ready": "/ready",
        "live": "/live",
        "api_prefix": "/v1",
        "endpoints": {
            "similarity": "/v1/similar",
            "cards": "/v1/cards",
            "search": "/v1/search",
            "deck_complete": "/v1/deck/complete",
        },
    }


# Versioned router
router = APIRouter(prefix="/v1")


def _health_impl() -> HealthResponse:
    state = get_state()
    if state.embeddings is None:
        raise HTTPException(status_code=503, detail="Embeddings not loaded")
    return HealthResponse(
        status="ok",
        num_cards=len(state.embeddings),  # type: ignore[arg-type]
        embedding_dim=state.embeddings.vector_size,  # type: ignore[union-attr]
    )


@router.get("/health", response_model=HealthResponse)
def health_v1():
    return _health_impl()


@app.get("/live")
def live():
    return {"status": "live"}


@app.get("/ready")
def ready():
    _adopt_legacy_globals()
    state = get_state()
    if state.embeddings is None:
        raise HTTPException(status_code=503, detail="not ready: embeddings not loaded")
    available = ["embedding"] + (["jaccard"] if state.graph_data is not None else [])
    if state.graph_data is not None:
        available.append("fusion")
    if (
        state.graph_data is not None
        and state.card_attrs is not None
        and sm_jaccard_faceted is not None
    ):
        available.append("jaccard_faceted")
    resp = {"status": "ready", "available_methods": available}
    if state.fusion_default_weights is not None:
        resp["fusion_default_weights"] = {
            "embed": state.fusion_default_weights.embed,
            "jaccard": state.fusion_default_weights.jaccard,
            "functional": state.fusion_default_weights.functional,
        }
    return resp


def _resolve_method(request: SimilarityRequest) -> str:
    forced_mode = (request.mode or "").lower().strip()
    if forced_mode in {"embedding", "jaccard", "jaccard_faceted", "fusion"}:
        return forced_mode
    if request.use_case is UseCaseEnum.substitute:
        return "embedding"
    if request.use_case in (UseCaseEnum.synergy, UseCaseEnum.meta):
        return "jaccard"
    return "embedding"


def _similar_embedding(query: str, k: int) -> list[SimilarCard]:
    state = get_state()
    if state.embeddings is None:
        raise HTTPException(status_code=503, detail="Embeddings not loaded")
    if query not in state.embeddings:
        all_cards = list(state.embeddings.index_to_key)
        suggestions = [c for c in all_cards if query.lower() in c.lower()][:5]
        raise HTTPException(
            status_code=404, detail=f"Card '{query}' not found. Suggestions: {suggestions}"
        )
    try:
        similar = state.embeddings.most_similar(query, topn=k)
        return [SimilarCard(card=card, similarity=float(sim)) for card, sim in similar]
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(e)) from e


def _similar_jaccard(query: str, k: int) -> list[SimilarCard]:
    state = get_state()
    if state.graph_data is None:
        raise HTTPException(status_code=503, detail="Graph data not loaded")
    adj = state.graph_data["adj"]
    if query not in adj:
        raise HTTPException(status_code=404, detail=f"Card '{query}' not in graph")
    similarities = sm_jaccard(query, adj, top_k=k, filter_lands=True)
    return [SimilarCard(card=card, similarity=float(sim)) for card, sim in similarities]


def _similar_fusion(request: SimilarityRequest, query: str, k: int) -> list[SimilarCard]:
    state = get_state()
    if state.embeddings is None:
        raise HTTPException(status_code=503, detail="Embeddings not loaded")
    if state.graph_data is None:
        raise HTTPException(status_code=503, detail="Graph data not loaded")
    tagger = FunctionalTagger() if FunctionalTagger is not None else None
    w = request.weights or {}
    base_fw = (
        state.fusion_default_weights or FusionWeights()
    )  # Uses recommended defaults (30% GNN, 25% Instruction, 20% Co-occurrence, 15% Jaccard, 10% Functional)
    fw = FusionWeights(
        embed=float(w.get("embed", base_fw.embed)),
        jaccard=float(w.get("jaccard", base_fw.jaccard)),
        functional=float(w.get("functional", base_fw.functional)),
        text_embed=float(w.get("text_embed", base_fw.text_embed)),
        sideboard=float(w.get("sideboard", base_fw.sideboard)),
        temporal=float(w.get("temporal", base_fw.temporal)),
        gnn=float(w.get("gnn", base_fw.gnn)),
        archetype=float(w.get("archetype", base_fw.archetype)),
        format=float(w.get("format", base_fw.format)),
    ).normalized()

    # Map use_case to task_type for instruction-tuned embeddings
    use_case_to_task = {
        UseCaseEnum.substitute: "substitution",
        UseCaseEnum.synergy: "synergy",
        UseCaseEnum.meta: "similar",  # Meta uses general similarity
    }
    task_type = use_case_to_task.get(request.use_case, "substitution")

    fusion = WeightedLateFusion(
        state.embeddings,
        state.graph_data["adj"],
        tagger,
        fw,
        aggregator=(request.aggregator or "weighted"),
        rrf_k=int(request.rrf_k or 60),
        mmr_lambda=float(request.mmr_lambda or 0.0),
        text_embedder=state.text_embedder,
        card_data=state.card_attrs,  # Use card_attrs for Oracle text access
        sideboard_cooccurrence=state.sideboard_cooccurrence,
        temporal_cooccurrence=state.temporal_cooccurrence,
        gnn_embedder=state.gnn_embedder,
        archetype_staples=state.archetype_staples,
        archetype_cooccurrence=state.archetype_cooccurrence,
        format_cooccurrence=state.format_cooccurrence,
        cross_format_patterns=state.cross_format_patterns,
        task_type=task_type,
    )
    if request.also_like:
        queries = [query] + [q for q in request.also_like if isinstance(q, str) and q]
        similar = fusion.similar_multi(queries, k)
    else:
        similar = fusion.similar(query, k, task_type=task_type)
    return [SimilarCard(card=card, similarity=float(sim)) for card, sim in similar]


def _similar_jaccard_faceted(request: SimilarityRequest, query: str, k: int) -> list[SimilarCard]:
    state = get_state()
    if state.graph_data is None:
        raise HTTPException(status_code=503, detail="Graph data not loaded")
    if state.card_attrs is None or sm_jaccard_faceted is None:
        raise HTTPException(status_code=503, detail="Attributes not loaded")
    adj = state.graph_data["adj"]
    if query not in adj:
        raise HTTPException(status_code=404, detail=f"Card '{query}' not in graph")
    facet = (request.facet or "type").lower().strip()
    similar = sm_jaccard_faceted(query, adj, state.card_attrs, facet=facet, top_k=k)
    return [SimilarCard(card=card, similarity=float(sim)) for card, sim in similar]


def _similar_impl(request: SimilarityRequest) -> SimilarityResponse:
    """Find similar cards based on resolved method and return normalized response."""
    _adopt_legacy_globals()
    query = request.query
    k = request.top_k
    method = _resolve_method(request)
    if method == "embedding":
        results = _similar_embedding(query, k)
    elif method == "jaccard":
        results = _similar_jaccard(query, k)
    elif method == "jaccard_faceted":
        results = _similar_jaccard_faceted(request, query, k)
    elif method == "fusion":
        results = _similar_fusion(request, query, k)
    else:  # pragma: no cover - shouldn't happen
        raise HTTPException(status_code=400, detail=f"Unknown similarity method: {method}")
    state = get_state()
    return SimilarityResponse(
        query=query,
        results=results,
        model_info={**state.model_info, "method_used": method},
        feedback_url="/v1/feedback",  # Endpoint for submitting feedback
    )


@router.post("/similar", response_model=SimilarityResponse)
def find_similar_v1(request: SimilarityRequest):
    # Log query for analytics
    try:
        from .query_history import log_query

        user_id = getattr(request, "user_id", None)
        session_id = getattr(request, "session_id", None)
        log_query(
            endpoint="/v1/similar",
            query=request.query,
            user_id=user_id,
            session_id=session_id,
            metadata={
                "method": getattr(request, "mode", None),
                "top_k": request.top_k,
                "use_case": request.use_case.value
                if hasattr(request.use_case, "value")
                else str(request.use_case),
            },
        )
    except Exception:
        pass  # Non-fatal - don't break API if logging fails
    return _similar_impl(request)


@router.get("/cards/{name}/similar", response_model=SimilarityResponse)
def get_similar_v1(
    name: str,
    mode: UseCaseEnum = UseCaseEnum.substitute,
    k: int = Query(10, ge=1, le=100),
):
    # Log query for analytics
    try:
        from .query_history import log_query

        log_query(
            endpoint="/v1/cards/{name}/similar",
            query=name,
            user_id=None,  # Could extract from request if available
            session_id=None,
            metadata={"mode": mode.value if hasattr(mode, "value") else str(mode), "top_k": k},
        )
    except Exception:
        pass  # Non-fatal - don't break API if logging fails
    req = SimilarityRequest(query=name, top_k=k, use_case=mode)
    return _similar_impl(req)


@router.get("/cards/{card}/contextual", response_model=ContextualResponse)
def get_contextual_suggestions(
    card: str,
    game: str = Query(..., description="Game name (magic, yugioh, pokemon)"),
    format: str | None = Query(None, description="Format name (e.g., Modern, Legacy)"),
    archetype: str | None = Query(None, description="Archetype name (e.g., Burn, Control)"),
    top_k: int = Query(10, description="Number of results per category"),
):
    """
    Get contextual suggestions for a card:
    - Synergies: Cards that work well together
    - Alternatives: Functional equivalents
    - Upgrades: Better versions (more expensive)
    - Downgrades: Budget alternatives (cheaper)
    """
    # Log query for analytics
    try:
        from .query_history import log_query

        log_query(
            endpoint="/v1/cards/{card}/contextual",
            query=card,
            user_id=None,  # Could extract from request if available
            session_id=None,
            metadata={"game": game, "format": format, "archetype": archetype, "top_k": top_k},
        )
    except Exception:
        pass  # Non-fatal

    game_lower = game.lower()
    if game_lower not in {"magic", "yugioh", "pokemon"}:
        raise HTTPException(status_code=400, detail=f"Unknown game: {game}")

    state = get_state()

    # Build fusion instance for similarity with task-specific instructions
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    # Contextual discovery uses different task types per category
    # We'll use "synergy" as default, but each method can override
    fusion = WeightedLateFusion(
        embeddings=state.embeddings,
        adj=state.graph_data.get("adj", {}) if state.graph_data else {},
        weights=FusionWeights(),  # Use defaults
        task_type="synergy",  # Default for contextual discovery
    )

    # Get price function
    price_fn = None
    try:
        from ..enrichment.card_market_data import (
            MarketDataManager,  # type: ignore[import-not-found]
        )

        _pm = getattr(app.state, "price_manager", None) or MarketDataManager()
        app.state.price_manager = _pm

        def price_fn(card_name: str) -> float | None:
            p = _pm.get_price(card_name)
            return float(p.usd) if p and p.usd else None
    except Exception:
        price_fn = None

    # Get tag function
    tag_set_fn = None
    if FunctionalTagger is not None and game_lower == "magic":
        try:
            _tagger = getattr(app.state, "mtg_tagger", None) or FunctionalTagger()
            app.state.mtg_tagger = _tagger

            def tag_set_fn(card_name: str) -> set[str]:
                dc = _tagger.tag_card(card_name)
                return {
                    k
                    for k, v in dc.__dict__.items()
                    if k != "card_name" and isinstance(v, bool) and v
                }
        except Exception:
            tag_set_fn = None

    # Get archetype data
    archetype_staples = state.archetype_staples if hasattr(state, "archetype_staples") else None
    archetype_cooccurrence = (
        state.archetype_cooccurrence if hasattr(state, "archetype_cooccurrence") else None
    )
    format_cooccurrence = (
        state.format_cooccurrence if hasattr(state, "format_cooccurrence") else None
    )

    # Create discovery instance
    from ..deck_building.contextual_discovery import ContextualCardDiscovery

    discovery = ContextualCardDiscovery(
        fusion=fusion,
        price_fn=price_fn,
        tag_set_fn=tag_set_fn,
        archetype_staples=archetype_staples,
        archetype_cooccurrence=archetype_cooccurrence,
        format_cooccurrence=format_cooccurrence,
    )

    # Find all contextual relationships
    synergies = discovery.find_synergies(
        card,
        format=format,
        archetype=archetype,
        top_k=top_k,
    )

    alternatives = discovery.find_alternatives(card, top_k=top_k)
    upgrades = discovery.find_upgrades(card, top_k=top_k)
    downgrades = discovery.find_downgrades(card, top_k=top_k)

    # Convert to dict format for JSON response
    return ContextualResponse(
        synergies=[
            {
                "card": s.card,
                "score": s.score,
                "co_occurrence_rate": s.co_occurrence_rate,
                "reasoning": s.reasoning,
            }
            for s in synergies
        ],
        alternatives=[
            {
                "card": a.card,
                "score": a.score,
                "reasoning": a.reasoning,
            }
            for a in alternatives
        ],
        upgrades=[
            {
                "card": u.card,
                "score": u.score,
                "price_delta": u.price_delta,
                "reasoning": u.reasoning,
            }
            for u in upgrades
        ],
        downgrades=[
            {
                "card": d.card,
                "score": d.score,
                "price_delta": d.price_delta,
                "reasoning": d.reasoning,
            }
            for d in downgrades
        ],
        feedback_url="/v1/feedback",
    )


@router.get("/cards", response_model=CardsResponse)
def list_cards_v1(
    prefix: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    List available cards with pagination.
    """
    state = get_state()
    if state.embeddings is None:
        raise HTTPException(status_code=503, detail="Embeddings not loaded")

    all_cards = list(state.embeddings.index_to_key)
    if prefix:
        all_cards = [c for c in all_cards if c.lower().startswith(prefix.lower())]

    total = len(all_cards)
    start = max(0, offset)
    end = max(0, min(start + limit, total))
    items = all_cards[start:end]
    next_offset = end if end < total else None

    return CardsResponse(items=items, total=total, next_offset=next_offset)


# ---------------------------------------------------------------------------
# Card search (Meilisearch + Qdrant)
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
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


def _get_search_client() -> HybridSearch | None:
    """Get or create hybrid search client."""
    if not HAS_SEARCH or HybridSearch is None:
        return None

    state = get_state()
    if state.embeddings is None:
        return None

    # Check if search client is cached in app state
    if hasattr(app.state, "search_client"):
        return app.state.search_client

    # Create new client
    try:
        client = HybridSearch(embeddings=state.embeddings)
        app.state.search_client = client
        return client
    except Exception as e:
        logger.error(f"Failed to create search client: {e}")
        return None


@router.post("/search", response_model=SearchResponse)
def search_cards_v1(request: SearchRequest):
    """
    Hybrid card search combining Meilisearch (text) and Qdrant (vector).
    Falls back to embeddings-only search if Meilisearch/Qdrant unavailable.

    Performs both text-based keyword search and semantic vector search,
    then combines results based on weights.
    """
    client = _get_search_client()

    # Fallback to embeddings-only search if hybrid search unavailable
    if client is None:
        state = get_state()
        if not hasattr(state, "embeddings") or not state.embeddings:
            raise HTTPException(
                status_code=503,
                detail="Search not available. Embeddings not loaded.",
            )

        # Use embeddings for simple name matching
        try:
            from gensim.models import KeyedVectors

            embeddings = state.embeddings
            if embeddings and isinstance(embeddings, KeyedVectors):
                # Simple fallback: find cards with query in name using embeddings
                query_lower = request.query.lower()
                matching_cards = [
                    card for card in embeddings.key_to_index.keys() if query_lower in card.lower()
                ][: request.limit]

                # Create fallback results from embeddings
                results = []
                for i, card_name in enumerate(matching_cards):
                    # Try to get full metadata from card attributes if available
                    metadata = {}
                    if state.card_attrs:
                        card_data = state.card_attrs.get(card_name) or state.card_attrs.get(
                            card_name.lower()
                        )
                        if card_data and isinstance(card_data, dict):
                            # Extract all available metadata
                            metadata = {
                                "image_url": (
                                    card_data.get("image_url")
                                    or card_data.get("image")
                                    or (
                                        card_data.get("images", {}).get("large")
                                        if isinstance(card_data.get("images"), dict)
                                        else None
                                    )
                                ),
                                "ref_url": card_data.get("ref_url")
                                or card_data.get("scryfall_uri"),
                                "type": card_data.get("type") or card_data.get("type_line", ""),
                                "mana_cost": card_data.get("mana_cost", ""),
                                "cmc": card_data.get("cmc", 0),
                                "colors": card_data.get("colors", ""),
                                "rarity": card_data.get("rarity", ""),
                                "power": card_data.get("power", ""),
                                "toughness": card_data.get("toughness", ""),
                                "set": card_data.get("set", ""),
                                "set_name": card_data.get("set_name", ""),
                                "oracle_text": card_data.get("oracle_text", ""),
                                "keywords": card_data.get("keywords", ""),
                                "functional_tags": card_data.get("functional_tags", ""),
                                "archetype": card_data.get("archetype", ""),
                                "format_legal": card_data.get("format_legal", ""),
                            }
                            # Remove empty values
                            metadata = {k: v for k, v in metadata.items() if v}

                    results.append(
                        SearchResultItem(
                            card_name=card_name,
                            score=max(0.5, 1.0 - (i * 0.05)),  # Decreasing scores, min 0.5
                            source="embedding_fallback",
                            metadata=metadata if metadata else {"image_url": None, "ref_url": None},
                        )
                    )

                if results:
                    return SearchResponse(query=request.query, total=len(results), results=results)
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No cards found matching '{request.query}'. Try a different search term.",
                    )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Fallback search failed: {e}")

        raise HTTPException(
            status_code=503,
            detail="Search not available. Ensure Meilisearch and Qdrant are running and embeddings are loaded.",
        )

    results = client.search(
        query=request.query,
        limit=request.limit,
        text_weight=request.text_weight,
        vector_weight=request.vector_weight,
    )

    return SearchResponse(
        query=request.query,
        results=[
            SearchResultItem(
                card_name=r.card_name,
                score=r.score,
                source=r.source,
                metadata=r.metadata,
            )
            for r in results
        ],
        total=len(results),
    )


@router.get("/search", response_model=SearchResponse)
def search_cards_get_v1(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    text_weight: float = Query(0.5, ge=0.0, le=1.0, description="Weight for text search"),
    vector_weight: float = Query(0.5, ge=0.0, le=1.0, description="Weight for vector search"),
):
    """GET version of card search endpoint."""
    request = SearchRequest(
        query=q, limit=limit, text_weight=text_weight, vector_weight=vector_weight
    )
    return search_cards_v1(request)


# ---------------------------------------------------------------------------
# Deck patching and completion
# ---------------------------------------------------------------------------


class PatchRequest(BaseModel):
    game: str = Field(..., description="magic|yugioh|pokemon")
    deck: dict = Field(..., description="Deck object matching validators schema")
    patch: DeckPatch
    strict_size: bool | None = Field(None, description="If true, enforce size constraints")
    check_legality: bool | None = Field(None, description="If true, enforce banlist legality")


@router.post("/deck/apply_patch", response_model=DeckPatchResult)
def deck_apply_patch(req: PatchRequest):
    game = req.game.lower()
    if game not in {"magic", "yugioh", "pokemon"}:
        raise HTTPException(status_code=400, detail=f"Unknown game: {req.game}")
    return apply_deck_patch(
        game,
        req.deck,
        req.patch,
        lenient_size=not bool(req.strict_size),
        check_legality=bool(req.check_legality),
    )


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


def _make_candidate_fn(mode: str | None, task_type: str | None = None):
    forced = (mode or "").lower().strip()

    def fn(card: str, k: int):
        # If no embeddings, default to jaccard if available
        state = get_state()
        effective_mode = forced
        if not effective_mode:
            if state.embeddings is not None:
                effective_mode = "embedding"
            elif state.graph_data is not None:
                effective_mode = "jaccard"
            else:
                return []  # No data available

        # Map task_type to use_case if provided
        use_case = UseCaseEnum.substitute  # Default
        if task_type == "completion":
            use_case = UseCaseEnum.substitute  # Completion uses substitution-like similarity
        elif task_type == "synergy":
            use_case = UseCaseEnum.synergy
        elif task_type == "substitution":
            use_case = UseCaseEnum.substitute

        req = SimilarityRequest(query=card, top_k=k, use_case=use_case)
        req.mode = effective_mode  # type: ignore
        try:
            resp = _similar_impl(req)
            return [(r.card, r.similarity) for r in resp.results]
        except HTTPException:
            return []  # Query not found or method unavailable

    return fn


@router.post("/deck/suggest_actions", response_model=SuggestActionsResponse)
def suggest_actions(req: SuggestActionsRequest):
    # Log query for analytics
    try:
        from .query_history import log_query

        user_id = getattr(req, "user_id", None)
        session_id = getattr(req, "session_id", None)
        log_query(
            endpoint="/v1/deck/suggest_actions",
            query=f"deck_refinement_{req.action_type}",
            user_id=user_id,
            session_id=session_id,
            metadata={"game": req.game, "action_type": req.action_type, "top_k": req.top_k},
        )
    except Exception:
        pass  # Non-fatal

    game = req.game.lower()
    if game not in {"magic", "yugioh", "pokemon"}:
        raise HTTPException(status_code=400, detail=f"Unknown game: {req.game}")

    cand_fn = _make_candidate_fn(req.mode)

    # Optional price and tag hooks
    price_fn = None
    try:
        from ..enrichment.card_market_data import (
            MarketDataManager,  # type: ignore[import-not-found]
        )

        _pm = getattr(app.state, "price_manager", None) or MarketDataManager()
        app.state.price_manager = _pm

        def price_fn(card: str) -> float | None:
            p = _pm.get_price(card)
            return float(p.usd) if p and p.usd else None

    except Exception:
        price_fn = None

    tag_set_fn = None
    if FunctionalTagger is not None and game == "magic":
        try:
            _tagger = getattr(app.state, "mtg_tagger", None) or FunctionalTagger()
            app.state.mtg_tagger = _tagger

            def tag_set_fn(card_name: str) -> set[str]:
                dc = _tagger.tag_card(card_name)
                return {
                    k
                    for k, v in dc.__dict__.items()
                    if k != "card_name" and isinstance(v, bool) and v
                }

        except Exception:
            tag_set_fn = None

    # Use greedy candidate generation (top additions) without applying
    import time

    t0 = time.time()
    # Build tag weight fn if provided
    tw = req.tag_weights or {}

    def tag_weight_fn(tag: str) -> float:
        return float(tw.get(tag, 1.0))

    # Build cmc fn from attributes if present
    def cmc_fn(card: str) -> int | None:
        attrs = get_state().card_attrs
        if not attrs:
            return None
        data = attrs.get(card) or attrs.get(card.lower())
        if not data:
            return None
        try:
            return int(data.get("cmc"))
        except Exception:
            return None

    # Get archetype from request or infer from deck
    archetype = getattr(req, "archetype", None)
    state = get_state()
    archetype_staples = state.archetype_staples if hasattr(state, "archetype_staples") else None

    part = {"magic": "Main", "yugioh": "Main Deck"}.get(game, "Main Deck")
    actions = []
    action_type = (req.action_type or "add").lower()

    # Map action_type to task_type for instruction-tuned embeddings
    action_to_task = {
        "add": "completion",
        "suggest": "completion",
        "replace": "substitution",
        "remove": None,  # No instruction needed for removal
    }
    task_type = action_to_task.get(action_type, "substitution")
    cand_fn = _make_candidate_fn(req.mode, task_type=task_type)

    # Handle different action types
    if action_type in ("add", "suggest"):
        from ..deck_building.deck_completion import suggest_additions

        pairs_or = suggest_additions(
            game,  # type: ignore[arg-type]
            req.deck,
            cand_fn,
            top_k=req.top_k,
            price_fn=price_fn,
            max_unit_price=req.budget_max,
            tag_set_fn=tag_set_fn,
            tag_weight_fn=tag_weight_fn if tw else None,
            coverage_weight=(req.coverage_weight or 0.0),
            cmc_fn=cmc_fn if get_state().card_attrs else None,
            curve_target=req.curve_target,
            curve_weight=(req.curve_weight or 0.0),
            return_metrics=True,
            archetype=archetype,
            archetype_staples=archetype_staples,
            role_aware=True,
            max_suggestions=min(req.top_k, 10),  # Constrained choice
        )
        if isinstance(pairs_or, tuple):
            pairs, s_metrics = pairs_or
        else:
            pairs, s_metrics = pairs_or, {}

        # Get score reasons from metrics if available
        score_reasons = s_metrics.get("score_reasons", {})
        for c, s in pairs:
            reason_parts = []

            # Use score reason if available (archetype staple, role gap, etc.)
            if c in score_reasons:
                reason_parts.append(score_reasons[c])

            # Add budget info if applicable
            if req.budget_max is not None:
                reason_parts.append(f"budget<=${req.budget_max}")

            # Add coverage info if applicable
            if req.coverage_weight:
                reason_parts.append("coverage+")

            actions.append(
                SuggestedAction(
                    op="add_card",
                    partition=part,
                    card=c,
                    count=1,
                    score=float(s),
                    reason=", ".join(reason_parts) if reason_parts else "Similarity match",
                )
            )

    if action_type in ("remove", "suggest"):
        from ..deck_building.deck_completion import suggest_removals

        removals = suggest_removals(
            game,  # type: ignore[arg-type]
            req.deck,
            cand_fn,
            archetype=archetype,
            archetype_staples=archetype_staples,
            tag_set_fn=tag_set_fn,
            preserve_roles=True,
            max_suggestions=min(req.top_k, 10),
        )

        for card, score, reason in removals:
            actions.append(
                SuggestedAction(
                    op="remove_card",
                    partition=part,
                    card=card,
                    count=1,
                    score=float(score),
                    reason=reason,
                )
            )

    if action_type == "replace" and req.seed_card:
        from ..deck_building.deck_completion import suggest_replacements

        replacements = suggest_replacements(
            game,  # type: ignore[arg-type]
            req.deck,
            req.seed_card,
            cand_fn,
            top_k=req.top_k,
            price_fn=price_fn,
            max_unit_price=req.budget_max,
            tag_set_fn=tag_set_fn,
            archetype=archetype,
            archetype_staples=archetype_staples,
        )

        for replacement, score, reason in replacements:
            actions.append(
                SuggestedAction(
                    op="replace_card",
                    partition=part,
                    card=replacement,
                    count=1,
                    score=float(score),
                    reason=reason,
                    target=req.seed_card,
                )
            )

    # Sort all actions by score (descending)
    actions.sort(key=lambda a: a.score, reverse=True)

    # Limit total actions
    if len(actions) > req.top_k:
        actions = actions[: req.top_k]

    elapsed_ms = int((time.time() - t0) * 1000)
    metrics = {
        "top_k": req.top_k,
        "elapsed_ms": elapsed_ms,
        "action_type": action_type,
        "num_actions": len(actions),
        "budget_max": req.budget_max,
        "coverage_weight": req.coverage_weight,
        "facets_available": bool(get_state().card_attrs is not None),
    }

    return SuggestActionsResponse(actions=actions, metrics=metrics, feedback_url="/v1/feedback")


class CompleteRequest(BaseModel):
    game: str
    deck: dict
    target_main_size: int | None = None
    mode: str | None = None
    max_steps: int = 60
    budget_max: float | None = None
    coverage_weight: float | None = None
    strict_size: bool | None = None
    check_legality: bool | None = None
    method: str = "greedy"  # "greedy" or "beam"
    beam_width: int = 5  # For beam search


class CompleteResponse(BaseModel):
    deck: dict
    steps: list[dict]
    metrics: dict | None = None
    feedback_url: str | None = Field(None, description="URL for submitting feedback on completion")


@router.post("/deck/complete", response_model=CompleteResponse)
def complete_deck(req: CompleteRequest):
    # Log query for analytics
    try:
        from .query_history import log_query

        user_id = getattr(req, "user_id", None)
        session_id = getattr(req, "session_id", None)
        deck_size = len(req.deck.get("Main", [])) if isinstance(req.deck, dict) else 0
        log_query(
            endpoint="/v1/deck/complete",
            query=f"deck_completion_{req.game}",
            user_id=user_id,
            session_id=session_id,
            metadata={
                "game": req.game,
                "target_size": req.target_main_size,
                "current_size": deck_size,
                "method": req.method,
            },
        )
    except Exception:
        pass  # Non-fatal

    game = req.game.lower()
    if game not in {"magic", "yugioh", "pokemon"}:
        raise HTTPException(status_code=400, detail=f"Unknown game: {req.game}")

    # Deck completion uses "completion" task type
    cand_fn = _make_candidate_fn(req.mode, task_type="completion")
    cfg = CompletionConfig(
        game=game,
        target_main_size=req.target_main_size,
        max_steps=req.max_steps,
        budget_max=req.budget_max,
        coverage_weight=(req.coverage_weight or 0.0),
    )

    # Optional price and tag hooks
    price_fn = None
    try:
        from ..enrichment.card_market_data import (
            MarketDataManager,  # type: ignore[import-not-found]
        )

        _pm = getattr(app.state, "price_manager", None) or MarketDataManager()
        app.state.price_manager = _pm

        def price_fn(card: str) -> float | None:
            p = _pm.get_price(card)
            return float(p.usd) if p and p.usd else None

    except Exception:
        price_fn = None

    tag_set_fn = None
    if FunctionalTagger is not None and game == "magic":
        try:
            _tagger = getattr(app.state, "mtg_tagger", None) or FunctionalTagger()
            app.state.mtg_tagger = _tagger

            def tag_set_fn(card_name: str) -> set[str]:
                dc = _tagger.tag_card(card_name)
                return {
                    k
                    for k, v in dc.__dict__.items()
                    if k != "card_name" and isinstance(v, bool) and v
                }

        except Exception:
            tag_set_fn = None

    import time

    t0 = time.time()

    # Choose completion method
    if req.method == "beam":
        from ..deck_building.beam_search import beam_search_completion

        # Build CMC function for beam search
        def cmc_fn(card: str) -> int | None:
            state = get_state()
            attrs = state.card_attrs
            if not attrs:
                return None
            data = attrs.get(card) or attrs.get(card.lower())
            if not data:
                return None
            try:
                return int(data.get("cmc", 0))
            except Exception:
                return None

        # Convert candidate_fn to beam search format
        def beam_candidate_fn(deck: dict, top_k: int) -> list[tuple[str, float]]:
            result = suggest_additions(
                game,  # type: ignore[arg-type]
                deck,
                cand_fn,
                top_k=top_k,
                price_fn=price_fn,
                max_unit_price=cfg.budget_max,
                tag_set_fn=tag_set_fn,
                coverage_weight=cfg.coverage_weight,
            )
            # Handle tuple return (with metrics) or list return
            if isinstance(result, tuple):
                candidates, _ = result
            else:
                candidates = result
            return candidates

        deck_out = beam_search_completion(
            initial_deck=req.deck,
            candidate_fn=beam_candidate_fn,  # type: ignore[arg-type]
            config=cfg,
            beam_width=req.beam_width,
            tag_set_fn=tag_set_fn,
            cmc_fn=cmc_fn,
            curve_target=None,  # TODO: Load from archetype
        )
        # Extract steps from beam search (simplified - beam search doesn't track steps the same way)
        steps: list[dict] = []  # Beam search doesn't return steps in same format
        quality_metrics = None
    else:
        deck_out, steps, quality_metrics = greedy_complete(
            game,  # type: ignore[arg-type]
            req.deck,
            cand_fn,
            cfg,
            price_fn=price_fn,
            tag_set_fn=tag_set_fn,
        )
    # Final strict validation pass according to flags
    strict_errors: list[str] = []
    if req.strict_size or req.check_legality:
        try:
            _strict = apply_deck_patch(
                game,
                deck_out,
                DeckPatch(ops=[]),
                lenient_size=not bool(req.strict_size),
                check_legality=bool(req.check_legality),
            )
            if not _strict.is_valid:
                strict_errors = _strict.errors
        except Exception:
            # Do not fail response; record as error
            strict_errors = ["strict_validation_exception"]

    elapsed_ms = int((time.time() - t0) * 1000)

    # Assess deck quality if we have the necessary functions
    quality_metrics = None
    if tag_set_fn:
        try:
            from ..deck_building.deck_quality import assess_deck_quality

            # Build CMC function from card attributes
            def cmc_fn(card: str) -> int | None:
                state = get_state()
                attrs = state.card_attrs
                if not attrs:
                    return None
                data = attrs.get(card) or attrs.get(card.lower())
                if not data:
                    return None
                try:
                    return int(data.get("cmc", 0))
                except Exception:
                    return None

            # Assess quality (reference decks optional for now)
            quality = assess_deck_quality(
                deck=deck_out,
                game=game,
                tag_set_fn=tag_set_fn,
                cmc_fn=cmc_fn,
                reference_decks=None,  # TODO: Load reference decks from archetype
            )
            quality_metrics = {
                "mana_curve_score": quality.mana_curve_score,
                "tag_balance_score": quality.tag_balance_score,
                "synergy_score": quality.synergy_score,
                "overall_score": quality.overall_score,
                "num_cards": quality.num_cards,
                "num_unique_tags": quality.num_unique_tags,
                "avg_tags_per_card": quality.avg_tags_per_card,
            }
        except Exception as e:
            logger.debug("Failed to assess deck quality: %s", e, exc_info=True)

    metrics = {
        "steps": len(steps),
        "elapsed_ms": elapsed_ms,
        "budget_max": req.budget_max,
        "coverage_weight": req.coverage_weight,
        "strict_size": bool(req.strict_size),
        "check_legality": bool(req.check_legality),
        "strict_errors": strict_errors,
    }
    if quality_metrics:
        metrics["quality"] = quality_metrics

    return CompleteResponse(
        deck=deck_out, steps=steps, metrics=metrics, feedback_url="/v1/feedback"
    )


# Ensure router is mounted after routes are defined
app.include_router(router)

# Include feedback router
try:
    from .feedback import router as feedback_router

    app.include_router(feedback_router)
except ImportError:
    logger.debug("Feedback router not available (optional)")

# Serve static HTML files for frontend interface
# Mount static directory if it exists
_static_dir = Path(__file__).parent.parent.parent.parent / "test"
if _static_dir.exists():
    try:
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
    except Exception as e:
        logger.debug("Could not mount static files: %s", e)

# Serve main search interface at /search.html
_search_html = Path(__file__).parent.parent.parent.parent / "test_search.html"
if _search_html.exists():

    @app.get("/search.html")
    def search_html():
        """Serve the main search interface."""
        return FileResponse(str(_search_html))

    # Also serve at root if no other root handler
    @app.get("/search")
    def search_redirect():
        """Redirect to search interface."""
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/search.html")


def main():
    parser = argparse.ArgumentParser(description="Run similarity API")
    parser.add_argument("--embeddings", type=str, required=True, help="Path to .wv file")
    parser.add_argument("--pairs", type=str, help="Path to pairs.csv (for Jaccard)")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    if not HAS_GENSIM:
        logger.error("gensim not installed")
        return 1

    # Load embeddings and graph
    load_embeddings_to_state(args.embeddings, args.pairs)

    logger.info("Available methods: %s", get_state().model_info["methods"])
    logger.info(
        "Recommendation: Use 'jaccard' if co-occurrence is available. See README for latest metrics."
    )

    # Run server
    # Logging is already configured via get_logger above
    if uvicorn is None:
        logger.error("uvicorn is not installed; cannot start the server")
        return 1
    # annotate model_info with embedding source for clarity
    state = get_state()
    src = Path(args.embeddings).name if args.embeddings else "unknown"
    state.model_info["embedding_source"] = src
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    import sys

    sys.exit(main())
