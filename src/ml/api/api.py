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
import logging
import os
from contextlib import asynccontextmanager

from enum import Enum

from pathlib import Path
import json

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Local application imports
from ..deck_building.deck_completion import (
    CompletionConfig,
    greedy_complete,
    suggest_additions,
)
from ..deck_building.deck_patch import DeckPatch, DeckPatchResult, apply_deck_patch
from ..similarity.fusion import FusionWeights, WeightedLateFusion
from ..similarity.similarity_methods import (
    jaccard_similarity as sm_jaccard,
    load_graph as sm_load_graph,
)
from ..utils.paths import PATHS

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
    from ..enrichment.card_functional_tagger import FunctionalTagger  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    FunctionalTagger = None  # type: ignore[assignment]

try:
    from ..similarity.similarity_methods import (
        load_card_attributes_csv as sm_load_attrs,
    )
    from ..similarity.similarity_methods import (
        jaccard_similarity_faceted as sm_jaccard_faceted,
    )
except Exception:  # pragma: no cover
    sm_load_attrs = None  # type: ignore
    sm_jaccard_faceted = None  # type: ignore

# Note: dotenv is loaded twice intentionally: once early for CORS/env-driven config
# and again inside lifespan to catch late environment overrides in tests.

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
        description="Optional fusion weights {embed, jaccard, functional}; will be normalized",
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


class HealthResponse(BaseModel):
    status: str
    num_cards: int
    embedding_dim: int


class CardsResponse(BaseModel):
    items: list[str]
    total: int
    next_offset: int | None = None


class ApiState:
    def __init__(self) -> None:
        self.embeddings: object | None = None
        self.graph_data: dict | None = None
        self.model_info: dict = {}
        self.fusion_default_weights: FusionWeights | None = None
        self.card_attrs: dict | None = None


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
    try:
        weights_path = PATHS.experiments / "fusion_grid_search_latest.json"
        if weights_path.exists():
            with open(weights_path) as fh:
                data = json.load(fh)
            bw = data.get("best_weights", {})
            fw = FusionWeights(
                embed=float(bw.get("embed", 0.20)),
                jaccard=float(bw.get("jaccard", 0.40)),
                functional=float(bw.get("functional", 0.40)),
            ).normalized()
            state.fusion_default_weights = fw
            state.model_info["fusion_default_weights"] = {
                "embed": fw.embed,
                "jaccard": fw.jaccard,
                "functional": fw.functional,
            }
            logger.info(
                "Loaded tuned fusion weights: embed=%.2f, jaccard=%.2f, functional=%.2f",
                fw.embed,
                fw.jaccard,
                fw.functional,
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
            state.model_info = {"methods": ["embedding"], "num_cards": len(embeddings), "embedding_dim": getattr(embeddings, "vector_size", 0)}  # type: ignore[arg-type]
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
            logger.info("Loaded card attributes from %s (count=%d)", attrs_path, len(state.card_attrs))
        except Exception:
            logger.exception("Failed to load attributes CSV: %s", attrs_path)
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
_cors_origins_env = os.getenv("CORS_ORIGINS", "*")
_parsed = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
if (not _parsed) or ("*" in _parsed):
    _cors_origins = ["*"]
else:
    _cors_origins = _parsed
_allow_credentials = _cors_origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


## startup event replaced by lifespan


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
    if state.graph_data is not None and state.card_attrs is not None and sm_jaccard_faceted is not None:
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
    base_fw = state.fusion_default_weights or FusionWeights(embed=0.20, jaccard=0.40, functional=0.40)
    fw = FusionWeights(
        embed=float(w.get("embed", base_fw.embed)),
        jaccard=float(w.get("jaccard", base_fw.jaccard)),
        functional=float(w.get("functional", base_fw.functional)),
    ).normalized()
    fusion = WeightedLateFusion(
        state.embeddings,
        state.graph_data["adj"],
        tagger,
        fw,
        aggregator=(request.aggregator or "weighted"),
        rrf_k=int(request.rrf_k or 60),
        mmr_lambda=float(request.mmr_lambda or 0.0),
    )
    if request.also_like:
        queries = [query] + [q for q in request.also_like if isinstance(q, str) and q]
        similar = fusion.similar_multi(queries, k)
    else:
        similar = fusion.similar(query, k)
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
        query=query, results=results, model_info={**state.model_info, "method_used": method}
    )


@router.post("/similar", response_model=SimilarityResponse)
def find_similar_v1(request: SimilarityRequest):
    return _similar_impl(request)


@router.get("/cards/{name}/similar", response_model=SimilarityResponse)
def get_similar_v1(
    name: str,
    mode: UseCaseEnum = UseCaseEnum.substitute,
    k: int = Query(10, ge=1, le=100),
):
    req = SimilarityRequest(query=name, top_k=k, use_case=mode)
    return _similar_impl(req)


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


class SuggestedAction(BaseModel):
    op: str
    partition: str
    card: str
    count: int = 1
    score: float
    reason: str | None = None


class SuggestActionsResponse(BaseModel):
    actions: list[SuggestedAction]
    metrics: dict | None = None


def _make_candidate_fn(mode: str | None):
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

        req = SimilarityRequest(query=card, top_k=k, use_case=UseCaseEnum.substitute)
        req.mode = effective_mode  # type: ignore
        try:
            resp = _similar_impl(req)
            return [(r.card, r.similarity) for r in resp.results]
        except HTTPException:
            return []  # Query not found or method unavailable

    return fn


@router.post("/deck/suggest_actions", response_model=SuggestActionsResponse)
def suggest_actions(req: SuggestActionsRequest):
    game = req.game.lower()
    if game not in {"magic", "yugioh", "pokemon"}:
        raise HTTPException(status_code=400, detail=f"Unknown game: {req.game}")

    cand_fn = _make_candidate_fn(req.mode)

    # Optional price and tag hooks
    price_fn = None
    try:
        from ..enrichment.card_market_data import MarketDataManager  # type: ignore[import-not-found]

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
                return {k for k, v in dc.__dict__.items() if k != "card_name" and isinstance(v, bool) and v}

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

    pairs_or = suggest_additions(
        game,
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
    )
    if isinstance(pairs_or, tuple):
        pairs, s_metrics = pairs_or
    else:
        pairs, s_metrics = pairs_or, {}
    elapsed_ms = int((time.time() - t0) * 1000)
    part = {"magic": "Main", "yugioh": "Main Deck"}.get(game, "Main Deck")
    actions = []
    for c, s in pairs:
        reason = []
        if req.budget_max is not None:
            reason.append(f"budget<=${req.budget_max}")
        if req.coverage_weight:
            reason.append("coverage+")
        actions.append(
            SuggestedAction(
                op="add_card",
                partition=part,
                card=c,
                count=1,
                score=float(s),
                reason=", ".join(reason) if reason else None,
            )
        )
    metrics = {
        "top_k": req.top_k,
        "elapsed_ms": elapsed_ms,
        "budget_max": req.budget_max,
        "coverage_weight": req.coverage_weight,
        "facets_available": bool(get_state().card_attrs is not None),
        **s_metrics,
    }
    return SuggestActionsResponse(actions=actions, metrics=metrics)


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


class CompleteResponse(BaseModel):
    deck: dict
    steps: list[dict]
    metrics: dict | None = None


@router.post("/deck/complete", response_model=CompleteResponse)
def complete_deck(req: CompleteRequest):
    game = req.game.lower()
    if game not in {"magic", "yugioh", "pokemon"}:
        raise HTTPException(status_code=400, detail=f"Unknown game: {req.game}")

    cand_fn = _make_candidate_fn(req.mode)
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
        from ..enrichment.card_market_data import MarketDataManager  # type: ignore[import-not-found]

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
                return {k for k, v in dc.__dict__.items() if k != "card_name" and isinstance(v, bool) and v}

        except Exception:
            tag_set_fn = None

    import time
    t0 = time.time()
    deck_out, steps = greedy_complete(
        game,
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
    metrics = {
        "steps": len(steps),
        "elapsed_ms": elapsed_ms,
        "budget_max": req.budget_max,
        "coverage_weight": req.coverage_weight,
        "strict_size": bool(req.strict_size),
        "check_legality": bool(req.check_legality),
        "strict_errors": strict_errors,
    }
    return CompleteResponse(deck=deck_out, steps=steps, metrics=metrics)


# Ensure router is mounted after routes are defined
app.include_router(router)


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
    # Configure basic logging when running directly
    logging.basicConfig(level=logging.INFO)
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
