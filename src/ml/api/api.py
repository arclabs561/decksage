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

Multi-game serving (single process, multiple games):
    export DECKSAGE_GAMES=magic,pokemon,yugioh
    export DECKSAGE_DEFAULT_GAME=magic

    # Per-game artifacts (required per game you want to serve)
    export EMBEDDINGS_PATH_MAGIC=/path/to/magic.wv
    export PAIRS_PATH_MAGIC=/path/to/magic_pairs.csv
    export ATTRIBUTES_PATH_MAGIC=/path/to/magic_attrs.csv

    export EMBEDDINGS_PATH_POKEMON=/path/to/pokemon.wv
    export PAIRS_PATH_POKEMON=/path/to/pokemon_pairs.csv

    export EMBEDDINGS_PATH_YUGIOH=/path/to/yugioh.wv
    export PAIRS_PATH_YUGIOH=/path/to/yugioh_pairs.csv

    # Optional per-game signals directory (default: experiments/signals/<game>/)
    export SIGNALS_DIR_MAGIC=/path/to/signals/magic

    # Optional per-game tuned fusion weights (JSON)
    export FUSION_WEIGHTS_PATH_MAGIC=/path/to/fusion_weights_magic.json

    # Optional per-game learned reranker (pickle)
    export RERANKER_PATH_MAGIC=/path/to/reranker_magic.pkl

    # Optional per-game search namespaces (default: cards_<game>)
    export MEILISEARCH_INDEX_MAGIC=cards_magic
    export QDRANT_COLLECTION_MAGIC=cards_magic
"""

import argparse
import dataclasses
import json
import logging
import os
from contextlib import asynccontextmanager, suppress
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
except ImportError:  # pragma: no cover
    uvicorn = None  # type: ignore[assignment]

try:
    from gensim.models import KeyedVectors

    HAS_GENSIM = True
except ImportError:  # pragma: no cover
    KeyedVectors = None  # type: ignore[assignment]
    HAS_GENSIM = False

try:
    from ..similarity.similarity_methods import (
        jaccard_similarity_faceted as sm_jaccard_faceted,
    )
    from ..similarity.similarity_methods import (
        load_card_attributes_csv as sm_load_attrs,
    )
except ImportError:  # pragma: no cover
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


# ---------------------------------------------------------------------------
# Multi-game support
# ---------------------------------------------------------------------------

SUPPORTED_GAMES: set[str] = {"magic", "pokemon", "yugioh"}


def _normalize_game(game: str | None) -> str | None:
    if game is None:
        return None
    g = str(game).strip().lower()
    return g or None


def _configured_games() -> list[str]:
    """Return configured games from app state (fallback: [default_game])."""
    try:
        games = getattr(app.state, "games", None)
        if isinstance(games, list) and games:
            return [str(g).strip().lower() for g in games if str(g).strip()]
    except AttributeError:
        pass
    # Fallback to a single default game
    return [_default_game()]


def _default_game() -> str:
    try:
        g = getattr(app.state, "default_game", None)
        if isinstance(g, str) and g.strip():
            return g.strip().lower()
    except AttributeError:
        pass
    return os.getenv("DECKSAGE_DEFAULT_GAME", "magic").strip().lower() or "magic"


def _require_game(game: str | None) -> str:
    """
    Require an explicit game in multi-game mode.

    - If only one game is configured, default to it.
    - If multiple games are configured, require request to specify it.
    """
    cfg = _configured_games()
    g = _normalize_game(game)
    if g is None:
        if len(cfg) == 1:
            g = cfg[0]
        else:
            raise HTTPException(
                status_code=400,
                detail=f"game is required (configured_games={cfg})",
            )
    if g not in SUPPORTED_GAMES:
        raise HTTPException(status_code=400, detail=f"Unknown game: {game}")
    return g


# Models
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
    model_info: dict
    feedback_url: str | None = Field(None, description="URL for submitting feedback on results")


class HealthResponse(BaseModel):
    status: str
    game: str
    num_cards: int
    embedding_dim: int


class CardSuggestion(BaseModel):
    name: str
    image_url: str | None = None
    type_line: str | None = None
    mana_cost: str | None = None
    rarity: str | None = None
    colors: str | None = None
    total_decks: int | None = None
    ban_status: dict[str, str] | None = None  # {format: "banned"|"restricted"|...}


class CardsResponse(BaseModel):
    items: list[CardSuggestion]
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
        self.embeddings: KeyedVectors | None = None  # type: ignore[assignment]
        self.graph_data: dict | None = None
        self.model_info: dict = {}
        self.fusion_default_weights: FusionWeights | None = None
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


def get_state(game: str | None = None) -> ApiState:
    """
    Get (or create) the API state for a specific game.

    In single-game mode, callers may omit `game` and the default game is used.
    In multi-game mode, request handlers should call `_require_game(...)` and
    pass the resolved game here.
    """
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


def load_embeddings_to_state(
    game: str,
    emb_path: str,
    pairs_csv: str | None = None,
    tuned_weights_path: str | None = None,
) -> None:
    """Load embeddings and graph data into app.state for a specific game."""
    state = get_state(game)
    logger.info("Loading embeddings from %s...", emb_path)
    emb = KeyedVectors.load(emb_path)
    state.embeddings = emb
    state.model_info = {
        "num_cards": len(emb),
        "embedding_dim": emb.vector_size,
        "model_path": emb_path,
        "embedding_source": Path(emb_path).stem,
        "game": game,
        "methods": ["embedding"],
    }
    logger.info("Loaded %s cards (%sD)", f"{len(emb):,}", emb.vector_size)
    if pairs_csv:
        logger.info("Loading graph from %s...", pairs_csv)
        # Only MTG has "lands" semantics; do not apply land filtering to other games.
        adj, weights = sm_load_graph(pairs_csv, filter_lands=(game == "magic"))
        state.graph_data = {"adj": adj, "weights": weights}
        state.model_info["methods"].append("jaccard")
        logger.info("Loaded graph: %s cards, %s weights", f"{len(adj):,}", f"{len(weights):,}")

    # Load tuned fusion weights if available (non-fatal).
    # In multi-game mode this must be configured per game to avoid cross-game contamination.
    try:
        weights_path: Path | None = None
        if tuned_weights_path:
            weights_path = Path(tuned_weights_path)
        elif len(_configured_games()) == 1:
            # Legacy single-game behavior
            weights_path = PATHS.experiments / "optimized_fusion_weights_latest.json"
            if not weights_path.exists():
                weights_path = PATHS.experiments / "fusion_grid_search_latest.json"

        if weights_path and weights_path.exists():
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
                    visual_embed=float(
                        bw.get("visual_embed", 0.20)
                    ),  # Visual (default from recommended weights)
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
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        logger.debug("No tuned fusion weights loaded", exc_info=True)


# API app with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler: load resources on startup, free on shutdown.

    **Worker Configuration**:
    - Each worker loads embeddings independently (memory duplication)
    - Recommended: Use single worker for development/testing
    - Production: Use multiple workers only if memory allows
      - Each worker needs ~2-4GB RAM for embeddings
      - Example: 4 workers = 8-16GB RAM total

    **Shared State** (if needed):
    - For shared caches/counters, use Redis (see load_signals.py)
    - Embeddings are read-only, so per-worker loading is acceptable
    - Consider shared memory (mmap) for very large embeddings if needed
    """
    # Load environment variables lazily (respects test-time monkeypatching)
    with suppress(Exception):
        load_dotenv()

    # ------------------------------------------------------------
    # Configure multi-game mode
    # ------------------------------------------------------------
    games_env = os.getenv("DECKSAGE_GAMES", "").strip()
    if games_env:
        games = [g.strip().lower() for g in games_env.split(",") if g.strip()]
    else:
        games = [os.getenv("DECKSAGE_DEFAULT_GAME", "magic").strip().lower() or "magic"]
    games = [g for g in games if g in SUPPORTED_GAMES]
    if not games:
        games = ["magic"]
    default_game = os.getenv("DECKSAGE_DEFAULT_GAME", games[0]).strip().lower() or games[0]
    if default_game not in games:
        default_game = games[0]

    app.state.games = games
    app.state.default_game = default_game

    multi = len(games) > 1
    logger.info("Configured games: %s (default=%s)", games, default_game)

    # Shared settings (global)
    text_embedder_model = os.getenv("TEXT_EMBEDDER_MODEL", "all-MiniLM-L6-v2")
    visual_embedder_model = os.getenv("VISUAL_EMBEDDER_MODEL", "google/siglip-base-patch16-224")

    # Load resources per game
    for game in games:
        suffix = game.upper()
        emb_key = f"EMBEDDINGS_PATH_{suffix}" if multi else "EMBEDDINGS_PATH"
        pairs_key = f"PAIRS_PATH_{suffix}" if multi else "PAIRS_PATH"
        attrs_key = f"ATTRIBUTES_PATH_{suffix}" if multi else "ATTRIBUTES_PATH"
        weights_key = f"FUSION_WEIGHTS_PATH_{suffix}"
        signals_key = f"SIGNALS_DIR_{suffix}"
        reranker_key = f"RERANKER_PATH_{suffix}" if multi else "RERANKER_PATH"

        emb_path = os.getenv(emb_key)
        pairs_path = os.getenv(pairs_key)
        if not pairs_path:
            # Auto-discover pairs file: prefer largest available
            pairs_dir = Path("data/processed")
            candidates = sorted(
                pairs_dir.glob(f"pairs_{game}_*.csv"),
                key=lambda p: p.stat().st_size,
                reverse=True,
            )
            if candidates:
                pairs_path = str(candidates[0])
                logger.info("Auto-discovered pairs for %s: %s", game, pairs_path)
        attrs_path = os.getenv(attrs_key)
        tuned_weights_path = os.getenv(weights_key)
        signals_dir = os.getenv(signals_key) or None
        reranker_path = os.getenv(reranker_key) or None

        if emb_path:
            if not HAS_GENSIM:
                logger.error(
                    "gensim is not installed; cannot load embeddings for %s from %s",
                    game,
                    emb_path,
                )
            else:
                try:
                    load_embeddings_to_state(
                        game,
                        emb_path,
                        pairs_path,
                        tuned_weights_path=tuned_weights_path,
                    )
                except (OSError, ValueError, RuntimeError):
                    logger.exception(
                        "Failed to load embeddings/graph during startup for game=%s", game
                    )
        else:
            logger.info(
                "%s not set; %s will be unavailable until embeddings are configured",
                emb_key,
                game,
            )

        # Optional attributes CSV (per game)
        if attrs_path and sm_load_attrs is not None and os.path.exists(attrs_path):
            try:
                state = get_state(game)
                state.card_attrs = sm_load_attrs(attrs_path)
                logger.info(
                    "Loaded %s attributes from %s (count=%d)",
                    game,
                    attrs_path,
                    len(state.card_attrs),
                )
            except (OSError, ValueError, KeyError):
                logger.exception("Failed to load attributes CSV for game=%s: %s", game, attrs_path)

        # Load enriched card metadata (with image URLs) for API responses.
        # Uses the enriched CSV which preserves all columns including image_url.
        enriched_path = Path(f"data/processed/card_attributes_{game}_enriched.csv")
        if enriched_path.exists():
            try:
                from ..utils.data_loading import load_card_attributes

                state = get_state(game)
                state.card_metadata = load_card_attributes(attrs_path=enriched_path, game=game)
                logger.info(
                    "Loaded enriched card metadata for %s: %d cards (with image URLs)",
                    game,
                    len(state.card_metadata),
                )
            except (OSError, ValueError, KeyError, ImportError):
                logger.debug(
                    "Failed to load enriched card metadata for game=%s", game, exc_info=True
                )

        # ------------------------------------------------------------------
        # Auto-populate MeiliSearch if index is empty
        # ------------------------------------------------------------------
        state = get_state(game)
        if state.card_metadata and HAS_SEARCH and HybridSearch is not None:
            try:
                idx_name = f"cards_{game}"
                _hs = HybridSearch(
                    embeddings=state.embeddings,
                    index_name=idx_name,
                    collection_name=idx_name,
                )
                if _hs.meilisearch:
                    _idx = _hs.meilisearch.index(idx_name)
                    _stats = _idx.get_stats()
                    if _stats.number_of_documents == 0:
                        _docs = []
                        for _i_card, (_name, _meta) in enumerate(state.card_metadata.items()):
                            _docs.append(
                                {
                                    "id": str(_i_card),
                                    "name": _name,
                                    "text": str(
                                        _meta.get("oracle_text") or _meta.get("text") or ""
                                    )[:2000],
                                    "type_line": str(
                                        _meta.get("type_line") or _meta.get("type") or ""
                                    ),
                                }
                            )
                        for _i in range(0, len(_docs), 500):
                            _idx.add_documents(_docs[_i : _i + 500])
                        logger.info(
                            "Auto-indexed %d cards into MeiliSearch index '%s'",
                            len(_docs),
                            idx_name,
                        )
                    else:
                        logger.info(
                            "MeiliSearch index '%s' already has %d documents, skipping auto-index",
                            idx_name,
                            _stats.number_of_documents,
                        )
            except Exception:
                logger.warning(
                    "MeiliSearch auto-index failed for %s (non-fatal)", game, exc_info=True
                )

        # ------------------------------------------------------------------
        # Enrichment data: banlists, archetypes, deck frequency
        # ------------------------------------------------------------------
        state = get_state(game)

        # Banlists
        banlist_path = Path(f"data/banlists/{game}_banlists.json")
        if banlist_path.exists():
            try:
                with open(banlist_path, encoding="utf-8") as f:
                    bl = json.load(f)
                state.banlist = bl.get("formats", {})
                logger.info("Loaded banlists for %s: %d formats", game, len(state.banlist))
            except (OSError, ValueError, KeyError):
                logger.debug("Failed to load banlists for game=%s", game, exc_info=True)

        # Archetypes: build reverse index (card_name -> [archetype_names])
        archetypes_index: dict[str, list[str]] = {}

        # From game_knowledge (core_cards + flex_slots -> archetype name)
        gk_path = Path(f"data/game_knowledge/{game}.json")
        if gk_path.exists():
            try:
                with open(gk_path, encoding="utf-8") as f:
                    gk = json.load(f)
                for arch in gk.get("archetypes", []):
                    arch_name = arch.get("name", "")
                    if not arch_name:
                        continue
                    for card in arch.get("core_cards", []) + arch.get("flex_slots", []):
                        if isinstance(card, str) and not card.startswith(
                            ("Starter", "Extender", "Tech", "Board")
                        ):
                            archetypes_index.setdefault(card, [])
                            if arch_name not in archetypes_index[card]:
                                archetypes_index[card].append(arch_name)
            except (OSError, ValueError, KeyError):
                logger.debug("Failed to load game_knowledge for game=%s", game, exc_info=True)

        # YGO: merge yugioh_archetype_mapping.json (card -> single archetype)
        if game == "yugioh":
            ygo_map_path = Path("data/yugioh_archetype_mapping.json")
            if ygo_map_path.exists():
                try:
                    with open(ygo_map_path, encoding="utf-8") as f:
                        ygo_map = json.load(f)
                    for card_name, arch_name in ygo_map.items():
                        if arch_name:
                            archetypes_index.setdefault(card_name, [])
                            if arch_name not in archetypes_index[card_name]:
                                archetypes_index[card_name].append(arch_name)
                    logger.info("Merged YGO archetype mapping: %d cards", len(ygo_map))
                except (OSError, ValueError, KeyError):
                    logger.debug("Failed to load YGO archetype mapping", exc_info=True)

        if archetypes_index:
            state.archetypes = archetypes_index
            logger.info("Built archetype index for %s: %d cards", game, len(archetypes_index))

        # Deck frequency
        freq_path = Path(f"data/processed/deck_frequency_{game}.json")
        if freq_path.exists():
            try:
                with open(freq_path, encoding="utf-8") as f:
                    state.deck_frequency = json.load(f)
                logger.info(
                    "Loaded deck frequency for %s: %d cards", game, len(state.deck_frequency)
                )
            except (OSError, ValueError, KeyError):
                logger.debug("Failed to load deck frequency for game=%s", game, exc_info=True)

        # Additional signals (per game)
        try:
            from .load_signals import load_signals_to_state

            state = get_state(game)
            default_signals_dir = (
                (PATHS.experiments / "signals" / game) if multi else (PATHS.experiments / "signals")
            )
            signal_status = load_signals_to_state(
                state=state,
                signals_dir=(signals_dir or default_signals_dir),
                text_embedder_model=text_embedder_model,
                visual_embedder_model=visual_embedder_model,
                reranker_path=reranker_path,
            )
            state.signal_status = signal_status

            loaded_signals = [name for name, loaded in signal_status.items() if loaded]
            missing_signals = [name for name, loaded in signal_status.items() if not loaded]
            logger.info(
                "Game=%s signals: %d/%d loaded. Available=%s Missing=%s",
                game,
                len(loaded_signals),
                len(signal_status),
                (", ".join(loaded_signals) if loaded_signals else "none"),
                (", ".join(missing_signals) if missing_signals else "none"),
            )
        except (ImportError, OSError, ValueError, KeyError):
            logger.debug(
                "Failed to load additional signals for game=%s (optional)", game, exc_info=True
            )
    try:
        yield
    finally:
        # Best-effort cleanup: null fields then delete entire dicts so
        # hot-reload starts fresh (half-loaded state must not survive).
        by_game = getattr(app.state, "api_by_game", None) or {}
        for _g, state in by_game.items():
            state.embeddings = None
            state.graph_data = None
            state.card_attrs = None
            state.sideboard_cooccurrence = None
            state.temporal_cooccurrence = None
            state.archetype_staples = None
            state.archetype_cooccurrence = None
            state.format_cooccurrence = None
            state.cross_format_patterns = None
            state.signal_status = None
            state.reranker = None
            state.card_metadata = None
            state.banlist = None
            state.archetypes = None
            state.deck_frequency = None
        # Remove entire api_by_game dict so next lifespan creates fresh ApiState objects
        with suppress(Exception):
            delattr(app.state, "api_by_game")
        # Reset legacy module globals so hot-reload doesn't carry stale test data
        global embeddings, graph_data, model_info
        embeddings = None
        graph_data = None
        model_info = {}
        # Clear optional app-scoped helpers if they were created
        with suppress(Exception):
            delattr(app.state, "price_manager")
        # Clear cached search clients
        with suppress(Exception):
            delattr(app.state, "search_by_game")


# Ensure env is loaded early so CORS and other env-driven settings are honored
with suppress(Exception):
    load_dotenv()

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
        _landing_html = Path(__file__).parent.parent.parent.parent / "frontend" / "test_search.html"
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


def _health_impl(game: str | None = None) -> HealthResponse:
    g = _require_game(game)
    state = get_state(g)
    if state.embeddings is None:
        raise HTTPException(status_code=503, detail="Embeddings not loaded")
    return HealthResponse(
        status="ok",
        game=g,
        num_cards=len(state.embeddings),  # type: ignore[arg-type]
        embedding_dim=state.embeddings.vector_size,  # type: ignore[union-attr]
    )


@router.get("/health", response_model=HealthResponse)
def health_v1(game: str | None = Query(None, description="Game name (magic, yugioh, pokemon)")):
    g = _require_game(game)
    state = get_state(g)
    if state.embeddings is None:
        raise HTTPException(status_code=503, detail="Embeddings not loaded")
    return HealthResponse(
        status="ok",
        game=g,
        num_cards=len(state.embeddings),  # type: ignore[arg-type]
        embedding_dim=state.embeddings.vector_size,  # type: ignore[union-attr]
    )


@router.get("/games")
def games_v1():
    """
    List configured games and readiness for each.

    In multi-game mode, clients should treat `game` as required on most endpoints.
    """
    games = _configured_games()
    default_game = _default_game()
    out: dict[str, Any] = {"default_game": default_game, "games": {}}
    for g in games:
        state = get_state(g)
        ready = state.embeddings is not None
        out["games"][g] = {
            "ready": bool(ready),
            "num_cards": len(state.embeddings) if ready else 0,  # type: ignore[arg-type]
            "embedding_dim": int(getattr(state.embeddings, "vector_size", 0)) if ready else 0,
            "methods": list((state.model_info or {}).get("methods", [])),
        }
    return out


@app.get("/live")
def live():
    return {"status": "live"}


@app.get("/ready")
def ready():
    games = _configured_games()
    default_game = _default_game()
    multi = len(games) > 1

    def _methods_for(state: ApiState) -> list[str]:
        available = ["embedding"] + (["jaccard"] if state.graph_data is not None else [])
        if state.graph_data is not None:
            available.append("fusion")
        if (
            state.graph_data is not None
            and state.card_attrs is not None
            and sm_jaccard_faceted is not None
        ):
            available.append("jaccard_faceted")
        return available

    if not multi:
        g = games[0] if games else default_game
        state = get_state(g)
        if state.embeddings is None:
            raise HTTPException(status_code=503, detail="not ready: embeddings not loaded")
        resp: dict[str, Any] = {
            "status": "ready",
            "game": g,
            "available_methods": _methods_for(state),
        }
        if state.fusion_default_weights is not None:
            resp["fusion_default_weights"] = {
                "embed": state.fusion_default_weights.embed,
                "jaccard": state.fusion_default_weights.jaccard,
                "functional": state.fusion_default_weights.functional,
                "text_embed": state.fusion_default_weights.text_embed,
                "visual_embed": state.fusion_default_weights.visual_embed,
                "gnn": state.fusion_default_weights.gnn,
            }
        return resp

    # Multi-game readiness
    status_by_game: dict[str, Any] = {}
    missing: list[str] = []
    for g in games:
        state = get_state(g)
        if state.embeddings is None:
            status_by_game[g] = {"ready": False, "reason": "embeddings not loaded"}
            missing.append(g)
            continue
        entry: dict[str, Any] = {
            "ready": True,
            "available_methods": _methods_for(state),
            "num_cards": len(state.embeddings),  # type: ignore[arg-type]
            "embedding_dim": int(getattr(state.embeddings, "vector_size", 0)),
        }
        if state.fusion_default_weights is not None:
            entry["fusion_default_weights"] = {
                "embed": state.fusion_default_weights.embed,
                "jaccard": state.fusion_default_weights.jaccard,
                "functional": state.fusion_default_weights.functional,
                "text_embed": state.fusion_default_weights.text_embed,
                "visual_embed": state.fusion_default_weights.visual_embed,
                "gnn": state.fusion_default_weights.gnn,
            }
        status_by_game[g] = entry

    if missing:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not ready",
                "default_game": default_game,
                "missing_games": missing,
                "games": status_by_game,
            },
        )

    return {"status": "ready", "default_game": default_game, "games": status_by_game}


def _resolve_method(request: SimilarityRequest) -> str:
    forced_mode = (request.mode or "").lower().strip()
    if forced_mode in {"embedding", "jaccard", "jaccard_faceted", "fusion", "meta"}:
        return forced_mode
    if request.use_case is UseCaseEnum.substitute:
        return "embedding"
    if request.use_case is UseCaseEnum.synergy:
        return "jaccard"
    if request.use_case is UseCaseEnum.meta:
        return "meta"
    return "embedding"


def _is_valid(val: object) -> bool:
    """Return True if *val* is a non-None, non-NaN value worth exposing."""
    if val is None:
        return False
    try:
        if val != val:  # NaN
            return False
    except (TypeError, ValueError):
        pass
    return True


# Per-game extra metadata fields (on top of the shared base set).
_GAME_EXTRA_FIELDS: dict[str, tuple[str, ...]] = {
    "magic": (
        "keywords",
        "keyword_abilities",
        "creature_types",
        "color_identity_str",
    ),
    "pokemon": (
        "supertype",
        "subtypes",
        "hp",
        "retreat_cost",
        "weakness_type",
        "resistance_type",
        "regulation_mark",
        "set_name",
        "attacks_detail",
        "abilities_detail",
    ),
    "yugioh": (
        "atk",
        "def_stat",
        "level_rank_link",
        "attribute",
        "race",
        "archetype",
        "monster_type",
        "attribute_enriched",
        "race_enriched",
        "archetype_enriched",
        "pendulum_scale",
        "link_markers",
        "card_category",
        "summoning_requirements",
        "effect_types",
        "frame_type",
        "creature_types",
        "banlist_tcg",
        "banlist_ocg",
        "banlist_goat",
        "name_jp",
        "fandom_categories",
        "fusion_material",
        "synchro_material",
        "fandom_statuses",
    ),
}

# Shared base fields returned for every game.
_BASE_FIELDS: tuple[str, ...] = (
    "image_url",
    "type",
    "mana_cost",
    "cmc",
    "oracle_text",
    "rarity",
    "colors",
    "power",
    "toughness",
    "attribute",
    "race",
    "hp",
    "keywords",
)


def _lookup_ban_status(card_name: str, banlist: dict | None) -> dict[str, str] | None:
    """Look up ban/restriction status for a card across all formats. Returns {format: status} or None."""
    if not banlist:
        return None
    ban = {}
    for fmt, statuses in banlist.items():
        for status_name, cards_list in statuses.items():
            if isinstance(cards_list, list) and card_name in cards_list:
                ban[fmt] = status_name
    return ban or None


def _enrich_similar_card(
    card_name: str,
    similarity: float,
    state: ApiState,
    *,
    game: str = "magic",
) -> SimilarCard:
    """Build a SimilarCard with metadata from enriched card data (image_url, type, etc.)."""
    meta = None
    if state.card_metadata:
        raw = state.card_metadata.get(card_name)
        if raw:
            meta = {}
            # Combine base + per-game fields
            extra = _GAME_EXTRA_FIELDS.get(game, ())
            for key in _BASE_FIELDS + extra:
                val = raw.get(key)
                if not _is_valid(val):
                    continue
                # Truncate oracle_text for the summary view (full text available in detail)
                if key == "oracle_text" and isinstance(val, str) and len(val) > 300:
                    meta["oracle_text_full"] = val
                    val = val[:300] + "..."
                meta[key] = val
            # Use type_line as fallback for "type"
            if "type" not in meta:
                tl = raw.get("type_line")
                if _is_valid(tl):
                    meta["type"] = tl
            if not meta:
                meta = None

    # Inject enrichment data (ban status, archetypes, deck popularity, co-occurrence)
    if meta is None:
        meta = {}

    # Ban status
    ban = _lookup_ban_status(card_name, state.banlist)
    if ban:
        meta["ban_status"] = ban

    # Archetype names
    if state.archetypes:
        arch_names = state.archetypes.get(card_name)
        if arch_names:
            meta["archetype_names"] = arch_names

    # Deck popularity
    if state.deck_frequency:
        freq = state.deck_frequency.get(card_name)
        if freq:
            meta["deck_popularity"] = freq

    # Top co-occurrence (from graph adjacency + weights, top 3 by weight)
    if state.graph_data and "adj" in state.graph_data:
        adj = state.graph_data["adj"]
        neighbors = adj.get(card_name)
        if neighbors:
            weights = state.graph_data.get("weights", {})
            scored = [(n, weights.get((card_name, n), 1)) for n in neighbors]
            scored.sort(key=lambda x: x[1], reverse=True)
            meta["top_cooccurrence"] = [n for n, _w in scored[:3]]

    if not meta:
        meta = None

    return SimilarCard(
        card=card_name, similarity=min(1.0, max(0.0, float(similarity))), metadata=meta,
    )


def _similar_embedding(
    state: ApiState, query: str, k: int, *, game: str = "magic"
) -> list[SimilarCard]:
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
        return [_enrich_similar_card(card, sim, state, game=game) for card, sim in similar]
    except (KeyError, RuntimeError, ValueError) as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(e)) from e


def _similar_jaccard(state: ApiState, query: str, k: int, *, game: str) -> list[SimilarCard]:
    if state.graph_data is None:
        raise HTTPException(status_code=503, detail="Graph data not loaded")
    adj = state.graph_data["adj"]
    if query not in adj:
        # Card exists in embeddings but not in co-occurrence graph -- return
        # empty results instead of 404 (data gap, not a missing card).
        if query in (state.embeddings or {}):
            return []
        raise HTTPException(status_code=404, detail=f"Card '{query}' not found")
    similarities = sm_jaccard(query, adj, top_k=k, filter_lands=(game == "magic"))
    return [_enrich_similar_card(card, sim, state, game=game) for card, sim in similarities]


def _similar_fusion(
    state: ApiState, request: SimilarityRequest, query: str, k: int, *, game: str
) -> list[SimilarCard]:
    if state.embeddings is None:
        raise HTTPException(status_code=503, detail="Embeddings not loaded")
    if state.graph_data is None:
        raise HTTPException(status_code=503, detail="Graph data not loaded")
    w = request.weights or {}
    base_fw = state.fusion_default_weights or FusionWeights()
    # Zero out weights for modalities not loaded on this state
    if state.text_embedder is None:
        base_fw = dataclasses.replace(base_fw, text_embed=0.0)
    if state.visual_embedder is None:
        base_fw = dataclasses.replace(base_fw, visual_embed=0.0)
    if getattr(state, "gnn_embedder", None) is None:
        base_fw = dataclasses.replace(base_fw, gnn=0.0)
    fw = FusionWeights(
        embed=float(w.get("embed", base_fw.embed)),
        jaccard=float(w.get("jaccard", base_fw.jaccard)),
        functional=float(w.get("functional", base_fw.functional)),
        text_embed=float(w.get("text_embed", base_fw.text_embed)),
        visual_embed=float(w.get("visual_embed", base_fw.visual_embed)),
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
        None,  # tagger (not loaded)
        fw,
        aggregator=(
            request.aggregator or "rrf"
        ),  # RRF recommended default for heterogeneous signals
        rrf_k=int(request.rrf_k or 60),
        mmr_lambda=float(request.mmr_lambda or 0.0),
        text_embedder=state.text_embedder,
        visual_embedder=state.visual_embedder,
        card_data=state.card_attrs,  # Use card_attrs for Oracle text access
        sideboard_cooccurrence=state.sideboard_cooccurrence,
        temporal_cooccurrence=state.temporal_cooccurrence,
        gnn_embedder=state.gnn_embedder,
        archetype_staples=state.archetype_staples,
        archetype_cooccurrence=state.archetype_cooccurrence,
        format_cooccurrence=state.format_cooccurrence,
        cross_format_patterns=state.cross_format_patterns,
        task_type=task_type,
        graph=state.graph_data.get("graph") if state.graph_data else None,
    )

    # Use reranking if available
    use_reranking = state.reranker is not None
    if use_reranking:
        # Two-stage pipeline: retrieve → rerank
        from ml.reranking.hybrid_search import HybridSearchWithReranking

        hybrid_search = HybridSearchWithReranking(
            retriever=fusion,
            reranker=state.reranker,
            top_k_retrieve=100,  # Retrieve more candidates
            top_k_final=k,  # Final results after reranking
            use_reranking=True,
        )
        if request.also_like:
            # Multi-query not yet supported in hybrid search, fallback to fusion
            queries = [query] + [q for q in request.also_like if isinstance(q, str) and q]
            similar = fusion.similar_multi(queries, k)
        else:
            similar = hybrid_search.search(query)
    else:
        # Fallback to manual fusion
        if request.also_like:
            queries = [query] + [q for q in request.also_like if isinstance(q, str) and q]
            similar = fusion.similar_multi(queries, k)
        else:
            similar = fusion.similar(query, k, task_type=task_type)

    return [_enrich_similar_card(card, sim, state, game=game) for card, sim in similar]


def _similar_jaccard_faceted(
    state: ApiState, request: SimilarityRequest, query: str, k: int, *, game: str
) -> list[SimilarCard]:
    if game != "magic":
        raise HTTPException(status_code=400, detail="jaccard_faceted is only supported for magic")
    if state.graph_data is None:
        raise HTTPException(status_code=503, detail="Graph data not loaded")
    if state.card_attrs is None or sm_jaccard_faceted is None:
        raise HTTPException(status_code=503, detail="Attributes not loaded")
    adj = state.graph_data["adj"]
    if query not in adj:
        if query in (state.embeddings or {}):
            return []
        raise HTTPException(status_code=404, detail=f"Card '{query}' not found")
    facet = (request.facet or "type").lower().strip()
    similar = sm_jaccard_faceted(query, adj, state.card_attrs, facet=facet, top_k=k)
    return [_enrich_similar_card(card, sim, state, game=game) for card, sim in similar]


def _apply_mmr_postprocess(
    state: ApiState, results: list[SimilarCard], mmr_lambda: float, k: int
) -> list[SimilarCard]:
    """Apply MMR diversification as a post-processing step using embedding cosine similarity."""
    if state.embeddings is None or len(results) <= 1:
        return results

    import numpy as np

    # Build embedding matrix for result cards (skip cards not in embeddings)
    valid = [(i, r) for i, r in enumerate(results) if r.card in state.embeddings]
    if len(valid) <= 1:
        return results

    vecs = np.array([state.embeddings[r.card] for _, r in valid])
    # Normalize for cosine similarity
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms

    selected: list[int] = [0]  # Always keep the top result
    candidates = list(range(1, len(valid)))

    while len(selected) < min(k, len(valid)) and candidates:
        best_idx = -1
        best_score = -float("inf")
        for c in candidates:
            relevance = valid[c][1].similarity
            # Max similarity to any already-selected item
            max_sim = max(float(vecs[c] @ vecs[s]) for s in selected)
            mmr_score = mmr_lambda * relevance - (1 - mmr_lambda) * max_sim
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = c
        if best_idx < 0:
            break
        selected.append(best_idx)
        candidates.remove(best_idx)

    return [valid[i][1] for i in selected]


def _similar_impl(request: SimilarityRequest) -> SimilarityResponse:
    """Find similar cards based on resolved method and return normalized response."""
    game = _require_game(request.game)
    state = get_state(game)
    query = request.query
    k = request.top_k
    method = _resolve_method(request)
    if method == "embedding":
        results = _similar_embedding(state, query, k, game=game)
    elif method == "jaccard":
        results = _similar_jaccard(state, query, k, game=game)
    elif method == "jaccard_faceted":
        results = _similar_jaccard_faceted(state, request, query, k, game=game)
    elif method == "fusion":
        results = _similar_fusion(state, request, query, k, game=game)
    elif method == "meta":
        # Meta mode: jaccard co-occurrence re-scored by competitive popularity
        results = _similar_jaccard(state, query, k * 2, game=game)
        if state.deck_frequency and results:
            max_freq = (
                max(
                    (state.deck_frequency.get(r.card, {}).get("total_decks", 0) for r in results),
                    default=1,
                )
                or 1
            )
            for r in results:
                freq = state.deck_frequency.get(r.card, {}).get("total_decks", 0)
                pop_ratio = freq / max_freq
                r.similarity = round(0.5 * r.similarity + 0.5 * pop_ratio, 4)
            results.sort(key=lambda r: r.similarity, reverse=True)
        results = results[:k]
    else:  # pragma: no cover - shouldn't happen
        raise HTTPException(status_code=400, detail=f"Unknown similarity method: {method}")

    # Apply MMR post-processing for non-fusion modes (fusion handles MMR internally)
    if method != "fusion" and request.mmr_lambda is not None:
        results = _apply_mmr_postprocess(state, results, request.mmr_lambda, k)

    # Look up query card metadata (image, type, etc.) -- reuse enrichment logic
    query_enriched = _enrich_similar_card(query, 1.0, state, game=game)
    query_meta = query_enriched.metadata

    return SimilarityResponse(
        query=query,
        query_metadata=query_meta,
        results=results,
        model_info={**state.model_info, "method_used": method, "game": game},
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
                "game": request.game,
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
    game: str | None = Query(None, description="Game name (magic, yugioh, pokemon)"),
    mmr_lambda: float | None = Query(
        None, ge=0.0, le=1.0, description="MMR diversification strength"
    ),
):
    # Log query for analytics
    try:
        from .query_history import log_query

        log_query(
            endpoint="/v1/cards/{name}/similar",
            query=name,
            user_id=None,  # Could extract from request if available
            session_id=None,
            metadata={
                "game": game,
                "mode": mode.value if hasattr(mode, "value") else str(mode),
                "top_k": k,
            },
        )
    except Exception:
        pass  # Non-fatal - don't break API if logging fails
    req = SimilarityRequest(game=game, query=name, top_k=k, use_case=mode, mmr_lambda=mmr_lambda)
    return _similar_impl(req)


@router.get("/cards/{card}/contextual", response_model=ContextualResponse)
def get_contextual_suggestions(
    card: str,
    game: str | None = Query(None, description="Game name (magic, yugioh, pokemon)"),
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

    game_lower = _require_game(game)
    state = get_state(game_lower)
    if state.embeddings is None or state.graph_data is None:
        raise HTTPException(
            status_code=503,
            detail=f"not ready for game={game_lower}: embeddings/graph not loaded",
        )

    # Build fusion instance for similarity with task-specific instructions
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    # Contextual discovery uses different task types per category
    # We'll use "synergy" as default, but each method can override
    # Fast-only weights: skip per-candidate neural inference (text_embed, visual_embed, gnn)
    # to keep contextual discovery <5s. Pre-computed signals suffice here.
    fast_weights = FusionWeights(
        embed=0.5,
        jaccard=0.4,
        functional=0.1,
        text_embed=0.0,
        visual_embed=0.0,
        gnn=0.0,
    )
    fusion = WeightedLateFusion(
        embeddings=state.embeddings,
        adj=state.graph_data.get("adj", {}) if state.graph_data else {},
        weights=fast_weights,
        task_type="synergy",  # Default for contextual discovery
        card_data=state.card_attrs,
    )

    price_fn, tag_set_fn, _ = _build_deck_hooks(state)
    price_label = "popularity" if (price_fn and state.deck_frequency) else "price"

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
        price_label=price_label,
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
    game: str | None = Query(None, description="Game name (magic, yugioh, pokemon)"),
    prefix: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    List available cards with pagination.
    """
    g = _require_game(game)
    state = get_state(g)
    if state.embeddings is None:
        raise HTTPException(status_code=503, detail="Embeddings not loaded")

    all_cards = list(state.embeddings.index_to_key)
    if prefix:
        all_cards = [c for c in all_cards if c.lower().startswith(prefix.lower())]

    total = len(all_cards)
    start = max(0, offset)
    end = max(0, min(start + limit, total))
    page = all_cards[start:end]
    next_offset = end if end < total else None

    # Build rich suggestions
    items: list[CardSuggestion] = []
    for card_name in page:
        suggestion = CardSuggestion(name=card_name)

        # Card metadata (image, type, mana, rarity, colors)
        if state.card_metadata:
            raw = state.card_metadata.get(card_name)
            if raw:
                suggestion.image_url = raw.get("image_url") or None
                suggestion.type_line = raw.get("type") or raw.get("type_line") or None
                suggestion.mana_cost = raw.get("mana_cost") or None
                suggestion.rarity = raw.get("rarity") or None
                suggestion.colors = raw.get("colors") or None

        # Deck frequency
        if state.deck_frequency:
            freq = state.deck_frequency.get(card_name)
            if freq:
                suggestion.total_decks = freq.get("total_decks")

        # Ban status
        suggestion.ban_status = _lookup_ban_status(card_name, state.banlist)

        items.append(suggestion)

    return CardsResponse(items=items, total=total, next_offset=next_offset)


# ---------------------------------------------------------------------------
# Card search (Meilisearch + Qdrant)
# ---------------------------------------------------------------------------


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


def _get_search_client(game: str) -> HybridSearch | None:
    """Get or create hybrid search client for a specific game."""
    if not HAS_SEARCH or HybridSearch is None:
        return None

    state = get_state(game)

    # Check if search client is cached in app state (per game)
    by_game = getattr(app.state, "search_by_game", None)
    if by_game is None:
        by_game = {}
        app.state.search_by_game = by_game
    cached = by_game.get(game)
    if cached is not None:
        # Rebuild if embeddings object changed (new .wv file loaded, hot-reload, etc.)
        # Use identity check, not truthiness, to detect stale embedding references.
        try:
            cached_emb = getattr(cached, "embeddings", None)
        except AttributeError:
            cached_emb = None
        if cached_emb is state.embeddings:
            return cached
        by_game.pop(game, None)

    # Per-game index/collection naming (override via env)
    idx_env = os.getenv(f"MEILISEARCH_INDEX_{game.upper()}")
    col_env = os.getenv(f"QDRANT_COLLECTION_{game.upper()}")
    index_name = (idx_env or f"cards_{game}").strip()
    collection_name = (col_env or f"cards_{game}").strip()

    # Create new client
    try:
        client = HybridSearch(
            embeddings=state.embeddings,
            index_name=index_name,
            collection_name=collection_name,
        )
        has_text = getattr(client, "meilisearch", None) is not None
        has_vector = getattr(client, "qdrant", None) is not None and state.embeddings is not None

        # Quintessential functionality: do not pretend search exists if neither backend
        # can answer queries for this game.
        if not has_text and not has_vector:
            logger.error(
                "Search backends unavailable for game=%s (no Meilisearch; Qdrant needs embeddings)",
                game,
            )
            return None
        if getattr(client, "qdrant", None) is not None and state.embeddings is None:
            logger.warning(
                "Qdrant is configured for game=%s but embeddings are not loaded; vector search disabled",
                game,
            )
        by_game[game] = client
        return client
    except Exception as e:
        # Broad catch: MeilisearchCommunicationError extends Exception directly,
        # not OSError/ConnectionError. Degrade to no-search rather than crash.
        logger.error(f"Failed to create search client: {e}")
        return None


@router.post("/search", response_model=SearchResponse)
def search_cards_v1(request: SearchRequest):
    """
    Hybrid card search combining Meilisearch (text) and Qdrant (vector).
    Requires at least one configured backend per game:
    - Text search works if Meilisearch is configured.
    - Vector search works if Qdrant is configured *and* embeddings are loaded.

    Performs both text-based keyword search and semantic vector search,
    then combines results based on weights.
    """
    game = _require_game(request.game)

    # Reject empty/whitespace-only queries
    if not request.query or not request.query.strip():
        return SearchResponse(query=request.query, results=[], total=0)

    client = _get_search_client(game)

    if client is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Search not available for game={game}: hybrid search backends are not configured. "
                "Run Meilisearch and/or Qdrant and ensure deps are installed "
                "(see src/ml/search/README.md)."
            ),
        )

    try:
        results = client.search(
            query=request.query,
            limit=request.limit,
            text_weight=request.text_weight,
            vector_weight=request.vector_weight,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Search backend error: {exc}",
        )

    # Enrich search results with full card metadata (image_url, type, stats, etc.)
    state = get_state(game)
    enriched = []
    for r in results:
        merged = dict(r.metadata) if r.metadata else {}
        if state.card_metadata:
            raw = state.card_metadata.get(r.card_name)
            if raw:
                extra = _GAME_EXTRA_FIELDS.get(game, ())
                for key in _BASE_FIELDS + extra:
                    if key in merged and _is_valid(merged[key]):
                        continue  # don't overwrite valid search-provided fields
                    val = raw.get(key)
                    if not _is_valid(val):
                        continue
                    if key == "oracle_text" and isinstance(val, str) and len(val) > 300:
                        merged["oracle_text_full"] = val
                        val = val[:300] + "..."
                    merged[key] = val
                if "type" not in merged:
                    tl = raw.get("type_line")
                    if _is_valid(tl):
                        merged["type"] = tl

        # Ban status
        ban = _lookup_ban_status(r.card_name, state.banlist)
        if ban:
            merged["ban_status"] = ban

        # Archetype names
        if state.archetypes:
            arch_names = state.archetypes.get(r.card_name)
            if arch_names:
                merged["archetype_names"] = arch_names

        # Deck popularity
        if state.deck_frequency:
            freq = state.deck_frequency.get(r.card_name)
            if freq:
                merged["deck_popularity"] = freq

        # Top co-occurrence
        if state.graph_data and "adj" in state.graph_data:
            adj = state.graph_data["adj"]
            neighbors = adj.get(r.card_name)
            if neighbors:
                weights_data = state.graph_data.get("weights", {})
                scored = [(n, weights_data.get((r.card_name, n), 1)) for n in neighbors]
                scored.sort(key=lambda x: x[1], reverse=True)
                merged["top_cooccurrence"] = [n for n, _w in scored[:3]]

        enriched.append(
            SearchResultItem(
                card_name=r.card_name,
                score=r.score,
                source=r.source,
                metadata=merged or None,
            )
        )

    return SearchResponse(
        query=request.query,
        results=enriched,
        total=len(enriched),
    )


@router.get("/search", response_model=SearchResponse)
def search_cards_get_v1(
    game: str | None = Query(None, description="Game name (magic, yugioh, pokemon)"),
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    text_weight: float = Query(0.5, ge=0.0, le=1.0, description="Weight for text search"),
    vector_weight: float = Query(0.5, ge=0.0, le=1.0, description="Weight for vector search"),
):
    """GET version of card search endpoint."""
    request = SearchRequest(
        game=game, query=q, limit=limit, text_weight=text_weight, vector_weight=vector_weight
    )
    return search_cards_v1(request)


# ---------------------------------------------------------------------------
# Deck patching and completion
# ---------------------------------------------------------------------------


_MAX_PARTITIONS = 10
_MAX_CARDS_PER_PARTITION = 500


def _normalize_deck_format(deck: dict, game: str) -> dict:
    """Normalize legacy deck format {"Main": [...]} to partitions format.

    Legacy: {"Main": ["card1", "card2"]}
    Partitions: {"partitions": [{"name": "Main", "cards": [{"name": "card1", "count": 1}]}]}
    """
    if "partitions" in deck:
        # Validate size limits on existing partitions format
        parts = deck.get("partitions")
        if isinstance(parts, list):
            if len(parts) > _MAX_PARTITIONS:
                raise HTTPException(
                    status_code=422, detail=f"Too many partitions (max {_MAX_PARTITIONS})"
                )
            for p in parts:
                cards = p.get("cards") if isinstance(p, dict) else None
                if isinstance(cards, list) and len(cards) > _MAX_CARDS_PER_PARTITION:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Too many cards in partition (max {_MAX_CARDS_PER_PARTITION})",
                    )
        return deck
    if not isinstance(deck, dict):
        return deck
    partitions = []
    from ..deck_building.deck_completion import _main_partition_name

    for part_name, cards in deck.items():
        if isinstance(cards, list):
            card_entries = []
            for c in cards:
                if isinstance(c, str):
                    card_entries.append({"name": c, "count": 1})
                elif isinstance(c, dict):
                    card_entries.append(c)
            # Remap legacy "Main" to game-specific partition name (e.g. "Main Deck" for YGO/Pokemon)
            actual_name = part_name
            if part_name.lower() == "main":
                actual_name = _main_partition_name(game)
            partitions.append({"name": actual_name, "cards": card_entries})
    if partitions:
        return {"partitions": partitions}
    return deck


class PatchRequest(BaseModel):
    game: str = Field(..., description="magic|yugioh|pokemon")
    deck: dict = Field(..., description="Deck object matching validators schema")
    patch: DeckPatch
    strict_size: bool | None = Field(None, description="If true, enforce size constraints")
    check_legality: bool | None = Field(None, description="If true, enforce banlist legality")


@router.post("/deck/apply_patch", response_model=DeckPatchResult)
def deck_apply_patch(req: PatchRequest):
    game = _require_game(req.game)
    req.deck = _normalize_deck_format(req.deck, game)
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


def _make_candidate_fn(game: str, mode: str | None, task_type: str | None = None):
    forced = (mode or "").lower().strip()

    def fn(card: str, k: int):
        # If no embeddings, default to jaccard if available
        state = get_state(game)
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

        # Over-fetch by 10x so candidates survive both English-name filtering AND
        # deck-membership filtering in suggest_additions (which removes already-in-deck
        # cards *after* this function returns).  Without enough headroom the greedy
        # completer exhausts the candidate pool around 40-50 cards.
        req = SimilarityRequest(
            game=game, query=card, top_k=min(k * 10, 100), use_case=use_case, mode=effective_mode
        )
        try:
            resp = _similar_impl(req)
            # Filter to cards with English metadata (removes Japanese/Spanish names in pool)
            known = state.card_metadata
            pairs = [(r.card, r.similarity) for r in resp.results]
            if known:
                pairs = [(c, s) for c, s in pairs if c in known]
            # Return the full over-fetched pool (up to 100 after English
            # filtering).  suggest_additions removes already-in-deck cards
            # *after* this function returns, so truncating to k here would
            # starve the greedy completer once ~k neighbors are already in
            # the deck.
            return pairs
        except HTTPException:
            return []  # Query not found or method unavailable

    return fn


# Basic lands have color_identity_str="C" in the enriched CSV but produce colored mana.
_BASIC_LAND_COLORS: dict[str, str] = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
    # Snow-covered basics
    "Snow-Covered Plains": "W",
    "Snow-Covered Island": "U",
    "Snow-Covered Swamp": "B",
    "Snow-Covered Mountain": "R",
    "Snow-Covered Forest": "G",
}


def _effective_color_identity(card_name: str, ci_str: str) -> set[str]:
    """Return the effective color identity for a card, fixing basic lands."""
    override = _BASIC_LAND_COLORS.get(card_name)
    if override:
        return {override}
    colors = set(ci_str) if isinstance(ci_str, str) else set()
    colors.discard("C")  # colorless is not a color identity constraint
    return colors


def _extract_deck_colors(deck: dict, game: str, card_metadata: dict | None) -> set[str] | None:
    """Extract the color identity of a deck from its cards.

    Returns a set of single-letter color codes (e.g. {"W", "U", "B"})
    or None if color identity data is unavailable or game is not Magic.
    """
    if game != "magic" or not card_metadata:
        return None

    from ..deck_building.deck_completion import _main_partition_name

    part = _main_partition_name(game)
    colors: set[str] = set()
    for p in deck.get("partitions", []) or []:
        if p.get("name") != part:
            continue
        for card in p.get("cards", []) or []:
            name = str(card.get("name", ""))
            meta = card_metadata.get(name)
            if meta:
                ci = meta.get("color_identity_str", "")
                colors.update(_effective_color_identity(name, ci))
    return colors if colors else None


def _wrap_cand_fn_color_filter(cand_fn, deck_colors: set[str], card_metadata: dict):
    """Wrap a candidate function to filter out cards outside the deck's color identity."""

    def filtered(card: str, k: int) -> list[tuple[str, float]]:
        # Pass k through; the inner cand_fn already over-fetches 10x
        results = cand_fn(card, k)
        filtered_results = []
        for cand, score in results:
            meta = card_metadata.get(cand)
            if meta:
                ci = meta.get("color_identity_str", "")
                cand_colors = _effective_color_identity(cand, ci)
                if cand_colors and not cand_colors.issubset(deck_colors):
                    continue
            filtered_results.append((cand, score))
        return filtered_results

    return filtered


def _build_deck_hooks(
    state: ApiState,
) -> tuple:
    """Build shared price_fn, tag_set_fn, cmc_fn from ApiState.

    Returns (price_fn, tag_set_fn, cmc_fn). tag_set_fn is always None
    (FunctionalTagger not loaded).
    """
    # Price: try MarketDataManager, fall back to deck frequency
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
        if state.deck_frequency:
            _freq = state.deck_frequency

            def price_fn(card: str) -> float | None:
                entry = _freq.get(card)
                if entry:
                    return float(entry.get("total_decks", 0))
                return None

    tag_set_fn = None  # FunctionalTagger not loaded

    # CMC from card attributes
    def cmc_fn(card: str) -> int | None:
        attrs = state.card_attrs
        if not attrs:
            return None
        data = attrs.get(card) or attrs.get(card.lower())
        if not data:
            return None
        try:
            return int(data.get("cmc", 0))
        except (ValueError, TypeError):
            return None

    return price_fn, tag_set_fn, cmc_fn if state.card_attrs else None


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

    game = _require_game(req.game)
    state = get_state(game)
    req.deck = _normalize_deck_format(req.deck, game)
    cand_fn = _make_candidate_fn(game, req.mode)

    # Color identity filtering (Magic only)
    deck_colors = _extract_deck_colors(req.deck, game, state.card_metadata)
    if deck_colors and state.card_metadata:
        cand_fn = _wrap_cand_fn_color_filter(cand_fn, deck_colors, state.card_metadata)

    price_fn, tag_set_fn, cmc_fn = _build_deck_hooks(state)

    import time

    t0 = time.time()
    # Build tag weight fn if provided
    tw = req.tag_weights or {}

    def tag_weight_fn(tag: str) -> float:
        return float(tw.get(tag, 1.0))

    # Get archetype from request or infer from deck
    archetype = getattr(req, "archetype", None)
    archetype_staples = state.archetype_staples if hasattr(state, "archetype_staples") else None

    from ..deck_building.deck_completion import _main_partition_name

    part = _main_partition_name(game)
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
    cand_fn = _make_candidate_fn(game, req.mode, task_type=task_type)

    # Re-apply color identity filtering to the task-specific candidate fn
    if deck_colors and state.card_metadata:
        cand_fn = _wrap_cand_fn_color_filter(cand_fn, deck_colors, state.card_metadata)

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
            cmc_fn=cmc_fn if state.card_attrs else None,
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
        "facets_available": bool(state.card_attrs is not None),
    }

    return SuggestActionsResponse(actions=actions, metrics=metrics, feedback_url="/v1/feedback")


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
    beam_width: int = 5  # For beam search
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

    game = _require_game(req.game)
    state = get_state(game)
    req.deck = _normalize_deck_format(req.deck, game)

    # Deck completion uses "completion" task type
    cand_fn = _make_candidate_fn(game, req.mode, task_type="completion")

    # Color identity filtering (Magic only)
    deck_colors = _extract_deck_colors(req.deck, game, state.card_metadata)
    if deck_colors and state.card_metadata:
        cand_fn = _wrap_cand_fn_color_filter(cand_fn, deck_colors, state.card_metadata)
    cfg = CompletionConfig(
        game=game,
        target_main_size=req.target_main_size,
        max_steps=req.max_steps,
        budget_max=req.budget_max,
        coverage_weight=(req.coverage_weight or 0.0),
    )

    price_fn, tag_set_fn, cmc_fn = _build_deck_hooks(state)

    import time

    t0 = time.time()

    # Choose completion method
    if req.method == "ot":
        from ..deck_building.deck_completion import _main_partition_name
        from ..deck_building.ot_completion import OTCompletionConfig, ot_complete_deck

        ot_cfg = OTCompletionConfig(
            game=game,
            target_main_size=req.target_main_size or (40 if game == "yugioh" else 60),
            embedding_weight=req.embedding_weight,
            role_weight=req.role_weight,
            curve_weight=req.curve_weight,
            sinkhorn_reg=req.sinkhorn_reg,
        )

        # Detect role gaps for role-aware OT cost
        role_gaps: dict[str, int] | None = None
        if tag_set_fn:
            part = _main_partition_name(game)
            role_counts: dict[str, int] = {}
            for p in req.deck.get("partitions", []) or []:
                if p.get("name") != part:
                    continue
                for card in p.get("cards", []) or []:
                    tags = tag_set_fn(str(card.get("name", "")))
                    count = int(card.get("count", 1))
                    for role in ["removal", "threat", "card_draw", "ramp", "counter", "tutor"]:
                        if role in tags:
                            role_counts[role] = role_counts.get(role, 0) + count
            role_targets = {"removal": 10, "threat": 14, "card_draw": 6, "ramp": 4}
            role_gaps = {
                r: t - role_counts.get(r, 0)
                for r, t in role_targets.items()
                if role_counts.get(r, 0) < t
            }

        ot_result = ot_complete_deck(
            game=game,
            deck=req.deck,
            embeddings=state.embeddings,
            cfg=ot_cfg,
            candidate_fn=cand_fn,
            tag_set_fn=tag_set_fn,
            cmc_fn=cmc_fn,
            role_gaps=role_gaps,
        )

        deck_out = ot_result.deck
        steps = [
            {
                "op": "add_card",
                "partition": _main_partition_name(game),
                "card": a["card"],
                "count": a["count"],
            }
            for a in ot_result.additions
        ]
        # Store OT-specific metrics for later inclusion in response
        _ot_metrics = ot_result.metrics
        quality_metrics = None

    elif req.method == "beam":
        from ..deck_building.beam_search import beam_search_completion

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
        except (ValueError, KeyError, AttributeError, TypeError):
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
                attrs = state.card_attrs
                if not attrs:
                    return None
                data = attrs.get(card) or attrs.get(card.lower())
                if not data:
                    return None
                try:
                    return int(data.get("cmc", 0))
                except (ValueError, TypeError):
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
        except (ImportError, AttributeError, ValueError, TypeError) as e:
            logger.debug("Failed to assess deck quality: %s", e, exc_info=True)

    metrics: dict[str, Any] = {
        "steps": len(steps),
        "elapsed_ms": elapsed_ms,
        "method": req.method,
        "budget_max": req.budget_max,
        "coverage_weight": req.coverage_weight,
        "strict_size": bool(req.strict_size),
        "check_legality": bool(req.check_legality),
        "strict_errors": strict_errors,
    }
    if quality_metrics:
        metrics["quality"] = quality_metrics
    # Include OT-specific metrics when method=ot
    if req.method == "ot":
        try:
            metrics["ot"] = _ot_metrics  # type: ignore[possibly-undefined]
        except NameError:
            pass

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

# Include chat router (LLM assistant with tool calling)
try:
    from .chat import chat_router

    app.include_router(chat_router)
except ImportError:
    logger.debug("Chat router not available (pydantic-ai required)")

# Include explain router (LLM similarity explanations)
try:
    from .explain import explain_router

    app.include_router(explain_router)
    logger.info("Explain router loaded")
except ImportError:
    logger.debug("Explain router not available (openai package required)")
except Exception as e:
    logger.warning("Explain router failed to load: %s", e)

# Serve static HTML files for frontend interface
# Mount static directory if it exists
_static_dir = Path(__file__).parent.parent.parent.parent / "frontend" / "static"
if _static_dir.exists():
    try:
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
    except (OSError, RuntimeError) as e:
        logger.debug("Could not mount static files: %s", e)

# Serve main search interface at /search.html
_search_html = Path(__file__).parent.parent.parent.parent / "frontend" / "test_search.html"
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
    parser.add_argument(
        "--game",
        type=str,
        default=os.getenv("DECKSAGE_DEFAULT_GAME", "magic"),
        help="Game name (magic|pokemon|yugioh). For true multi-game serving, use DECKSAGE_GAMES + per-game env vars.",
    )
    parser.add_argument("--embeddings", type=str, required=True, help="Path to .wv file")
    parser.add_argument("--pairs", type=str, help="Path to pairs.csv (for Jaccard)")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    if not HAS_GENSIM:
        logger.error("gensim not installed")
        return 1

    # Load embeddings and graph
    game = _require_game(args.game)
    # In single-game CLI mode, set app state hints for downstream helpers.
    app.state.games = [game]
    app.state.default_game = game
    load_embeddings_to_state(game, args.embeddings, args.pairs)

    logger.info("Available methods (%s): %s", game, get_state(game).model_info.get("methods"))
    logger.info(
        "Recommendation: Use 'jaccard' if co-occurrence is available. See README for latest metrics."
    )

    # Run server
    # Logging is already configured via get_logger above
    if uvicorn is None:
        logger.error("uvicorn is not installed; cannot start the server")
        return 1
    # annotate model_info with embedding source for clarity
    state = get_state(game)
    src = Path(args.embeddings).name if args.embeddings else "unknown"
    state.model_info["embedding_source"] = src
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    import sys

    sys.exit(main())
