#!/usr/bin/env python3
"""
Load sideboard, temporal, text embedding, and GNN signals into API state.

This module provides functions to load pre-computed signals from disk
and make them available to the API.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path


logger = logging.getLogger("decksage.api.signals")

try:
    from ..similarity.text_embeddings import CardTextEmbedder

    HAS_TEXT_EMBED = True
except ImportError:
    HAS_TEXT_EMBED = False
    CardTextEmbedder = None

try:
    from ..similarity.gnn_embeddings import CardGNNEmbedder

    HAS_GNN = True
except ImportError:
    HAS_GNN = False
    CardGNNEmbedder = None

try:
    from ..similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder

    HAS_INSTRUCTION_EMBED = True
except ImportError:
    HAS_INSTRUCTION_EMBED = False
    InstructionTunedCardEmbedder = None

from ..utils.paths import PATHS
from .api import get_state


try:
    from ..similarity.archetype_signal import (
        compute_archetype_cooccurrence,
        compute_archetype_staples,
    )
    from ..similarity.format_signal import (
        compute_format_cooccurrence,
        compute_format_transition_patterns,
    )

    HAS_ARCHETYPE_FORMAT = True
except ImportError:
    HAS_ARCHETYPE_FORMAT = False


def load_signals_to_state(
    sideboard_path: Path | str | None = None,
    temporal_path: Path | str | None = None,
    gnn_path: Path | str | None = None,
    text_embedder_model: str | None = None,
    archetype_staples_path: Path | str | None = None,
    archetype_cooccur_path: Path | str | None = None,
    format_cooccur_path: Path | str | None = None,
    cross_format_path: Path | str | None = None,
) -> None:
    """
    Load pre-computed signals into API state.

    Args:
        sideboard_path: Path to sideboard co-occurrence JSON
        temporal_path: Path to temporal co-occurrence JSON
        gnn_path: Path to GNN embeddings JSON
        text_embedder_model: Model name for text embedder (creates if provided)
    """
    state = get_state()
    signals_dir = PATHS.experiments / "signals"

    # Load sideboard signal
    if sideboard_path is None:
        sideboard_path = signals_dir / "sideboard_cooccurrence.json"

    if isinstance(sideboard_path, str):
        sideboard_path = Path(sideboard_path)

    if sideboard_path.exists():
        try:
            with open(sideboard_path) as f:
                state.sideboard_cooccurrence = json.load(f)
            logger.info(
                f"Loaded sideboard co-occurrence: {len(state.sideboard_cooccurrence)} cards"
            )
        except Exception as e:
            logger.warning(f"Failed to load sideboard signal: {e}")
            state.sideboard_cooccurrence = None
    else:
        logger.debug(f"Sideboard signal not found: {sideboard_path}")
        state.sideboard_cooccurrence = None

    # Load temporal signal
    if temporal_path is None:
        temporal_path = signals_dir / "temporal_cooccurrence.json"

    if isinstance(temporal_path, str):
        temporal_path = Path(temporal_path)

    if temporal_path.exists():
        try:
            with open(temporal_path) as f:
                state.temporal_cooccurrence = json.load(f)
            logger.info(f"Loaded temporal co-occurrence: {len(state.temporal_cooccurrence)} months")
        except Exception as e:
            logger.warning(f"Failed to load temporal signal: {e}")
            state.temporal_cooccurrence = None
    else:
        logger.debug(f"Temporal signal not found: {temporal_path}")
        state.temporal_cooccurrence = None

    # Load GNN embeddings (hybrid system)
    if gnn_path is None:
        # Try multiple default paths
        gnn_path = PATHS.embeddings / "gnn_graphsage.json"
        if not gnn_path.exists():
            gnn_path = signals_dir / "gnn_graphsage.json"
        if not gnn_path.exists():
            gnn_path = signals_dir / "gnn_embeddings.json"

    if isinstance(gnn_path, str):
        gnn_path = Path(gnn_path)

    if gnn_path.exists() and HAS_GNN and CardGNNEmbedder is not None:
        try:
            state.gnn_embedder = CardGNNEmbedder(model_path=gnn_path)
            logger.info(f"Loaded GNN embeddings: {gnn_path}")
        except Exception as e:
            logger.warning(f"Failed to load GNN embeddings: {e}")
            state.gnn_embedder = None
    else:
        logger.debug(f"GNN embeddings not found or not available: {gnn_path}")
        state.gnn_embedder = None

    # Initialize text embedder - prefer instruction-tuned (hybrid system)
    import os

    instruction_model = os.getenv("INSTRUCTION_EMBEDDER_MODEL", "intfloat/e5-base-v2")

    # Try instruction-tuned embedder first (better for new cards)
    if HAS_INSTRUCTION_EMBED and InstructionTunedCardEmbedder is not None:
        try:
            state.text_embedder = InstructionTunedCardEmbedder(model_name=instruction_model)
            logger.info(f"Initialized instruction-tuned embedder: {instruction_model}")
        except Exception as e:
            logger.warning(f"Failed to initialize instruction-tuned embedder: {e}")
            # Fallback to regular text embedder
            if text_embedder_model and HAS_TEXT_EMBED:
                try:
                    state.text_embedder = CardTextEmbedder(model_name=text_embedder_model)
                    logger.info(f"Initialized fallback text embedder: {text_embedder_model}")
                except Exception as e2:
                    logger.warning(f"Failed to initialize fallback text embedder: {e2}")
                    state.text_embedder = None
            else:
                state.text_embedder = None
    elif text_embedder_model and HAS_TEXT_EMBED:
        # Fallback to regular text embedder if instruction-tuned not available
        try:
            state.text_embedder = CardTextEmbedder(model_name=text_embedder_model)
            logger.info(f"Initialized text embedder: {text_embedder_model}")
        except Exception as e:
            logger.warning(f"Failed to initialize text embedder: {e}")
            state.text_embedder = None
    elif not HAS_TEXT_EMBED and not HAS_INSTRUCTION_EMBED:
        logger.debug("Text embeddings not available (sentence-transformers not installed)")
        state.text_embedder = None

    # Load archetype signals
    if archetype_staples_path is None:
        archetype_staples_path = signals_dir / "archetype_staples.json"
    if archetype_cooccur_path is None:
        archetype_cooccur_path = signals_dir / "archetype_cooccurrence.json"

    if isinstance(archetype_staples_path, str):
        archetype_staples_path = Path(archetype_staples_path)
    if isinstance(archetype_cooccur_path, str):
        archetype_cooccur_path = Path(archetype_cooccur_path)

    if archetype_staples_path.exists() and archetype_cooccur_path.exists():
        try:
            with open(archetype_staples_path) as f:
                state.archetype_staples = json.load(f)
            with open(archetype_cooccur_path) as f:
                state.archetype_cooccurrence = json.load(f)
            logger.info(
                f"Loaded archetype signals: {len(state.archetype_staples)} cards with staples, {len(state.archetype_cooccurrence)} cards with co-occurrence"
            )
        except Exception as e:
            logger.warning(f"Failed to load archetype signals: {e}")
            state.archetype_staples = None
            state.archetype_cooccurrence = None
    else:
        logger.debug(
            f"Archetype signals not found: {archetype_staples_path}, {archetype_cooccur_path}"
        )
        state.archetype_staples = None
        state.archetype_cooccurrence = None

    # Load format signals
    if format_cooccur_path is None:
        format_cooccur_path = signals_dir / "format_cooccurrence.json"
    if cross_format_path is None:
        cross_format_path = signals_dir / "cross_format_patterns.json"

    if isinstance(format_cooccur_path, str):
        format_cooccur_path = Path(format_cooccur_path)
    if isinstance(cross_format_path, str):
        cross_format_path = Path(cross_format_path)

    if format_cooccur_path.exists() and cross_format_path.exists():
        try:
            with open(format_cooccur_path) as f:
                state.format_cooccurrence = json.load(f)
            with open(cross_format_path) as f:
                state.cross_format_patterns = json.load(f)
            logger.info(
                f"Loaded format signals: {len(state.format_cooccurrence)} formats, {len(state.cross_format_patterns)} cards with cross-format patterns"
            )
        except Exception as e:
            logger.warning(f"Failed to load format signals: {e}")
            state.format_cooccurrence = None
            state.cross_format_patterns = None
    else:
        logger.debug(f"Format signals not found: {format_cooccur_path}, {cross_format_path}")
        state.format_cooccurrence = None
        state.cross_format_patterns = None
