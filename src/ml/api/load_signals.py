#!/usr/bin/env python3
"""
Load text embedding, visual embedding, and archetype signals into API state.

This module provides functions to load pre-computed signals from disk
and make them available to the API.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..utils.paths import PATHS


logger = logging.getLogger("decksage.api.signals")

try:
    from ..similarity.text_embeddings import CardTextEmbedder

    HAS_TEXT_EMBED = True
except ImportError:
    HAS_TEXT_EMBED = False
    CardTextEmbedder = None

try:
    from ..similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder

    HAS_INSTRUCTION_EMBED = True
except ImportError:
    HAS_INSTRUCTION_EMBED = False
    InstructionTunedCardEmbedder = None

try:
    from ..similarity.visual_embeddings import CardVisualEmbedder

    HAS_VISUAL_EMBED = True
except ImportError:
    HAS_VISUAL_EMBED = False
    CardVisualEmbedder = None


def load_signals_to_state(
    state: Any,
    signals_dir: Path | str | None = None,
    text_embedder_model: str | None = None,
    visual_embedder_model: str | None = None,
    archetype_staples_path: Path | str | None = None,
    archetype_cooccur_path: Path | str | None = None,
    skip_embedders: bool = False,
    # Legacy kwargs accepted but ignored (callers may still pass them).
    **_kwargs: Any,
) -> dict[str, bool]:
    """
    Load pre-computed signals into API state.

    Args:
        text_embedder_model: Model name for text embedder (creates if provided)
        visual_embedder_model: Model name for visual embedder (creates if provided)
        archetype_staples_path: Path to archetype staples JSON
        archetype_cooccur_path: Path to archetype co-occurrence JSON
        skip_embedders: Skip loading text/visual embedders (when shared instances
            are assigned externally by the caller)

    Returns:
        Dict mapping signal name -> is_loaded (bool)
    """
    if signals_dir is None:
        signals_dir = PATHS.experiments / "signals"
    if isinstance(signals_dir, str):
        signals_dir = Path(signals_dir)

    # Track signal loading status
    status: dict[str, bool] = {
        "text_embedder": False,
        "visual_embedder": False,
        "archetype": False,
    }

    # Initialize text/visual embedders (skipped when caller provides shared instances)
    if not skip_embedders:
        import os

        instruction_model = os.getenv("INSTRUCTION_EMBEDDER_MODEL", "intfloat/e5-base-v2")

        if HAS_INSTRUCTION_EMBED and InstructionTunedCardEmbedder is not None:
            try:
                state.text_embedder = InstructionTunedCardEmbedder(model_name=instruction_model)
                status["text_embedder"] = True
                logger.info("[ok] Initialized instruction-tuned embedder: %s", instruction_model)
            except Exception as e:
                logger.warning("Failed to initialize instruction-tuned embedder: %s", e)
                if text_embedder_model and HAS_TEXT_EMBED:
                    try:
                        state.text_embedder = CardTextEmbedder(model_name=text_embedder_model)
                        status["text_embedder"] = True
                        logger.info(
                            "[ok] Initialized fallback text embedder: %s", text_embedder_model
                        )
                    except Exception as e2:
                        logger.warning("Failed to initialize fallback text embedder: %s", e2)
                        state.text_embedder = None
                else:
                    state.text_embedder = None
        elif text_embedder_model and HAS_TEXT_EMBED:
            try:
                state.text_embedder = CardTextEmbedder(model_name=text_embedder_model)
                status["text_embedder"] = True
                logger.info("[ok] Initialized text embedder: %s", text_embedder_model)
            except Exception as e:
                logger.warning("Failed to initialize text embedder: %s", e)
                state.text_embedder = None
        elif not HAS_TEXT_EMBED and not HAS_INSTRUCTION_EMBED:
            logger.debug("Text embeddings not available (sentence-transformers not installed)")
            state.text_embedder = None

        if visual_embedder_model is None:
            visual_embedder_model = os.getenv(
                "VISUAL_EMBEDDER_MODEL", "google/siglip2-so400m-patch16-384"
            )

        if visual_embedder_model and HAS_VISUAL_EMBED and CardVisualEmbedder is not None:
            try:
                state.visual_embedder = CardVisualEmbedder(model_name=visual_embedder_model)
                status["visual_embedder"] = True
                logger.info("[ok] Initialized visual embedder: %s", visual_embedder_model)
            except Exception as e:
                logger.warning("Failed to initialize visual embedder: %s", e)
                state.visual_embedder = None
        elif not HAS_VISUAL_EMBED:
            logger.debug(
                "Visual embeddings not available (sentence-transformers or pillow not installed)"
            )
            state.visual_embedder = None
        else:
            state.visual_embedder = None
    else:
        # Embedders managed externally; mark status based on what's on state
        status["text_embedder"] = state.text_embedder is not None
        status["visual_embedder"] = state.visual_embedder is not None

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
            status["archetype"] = True
            logger.info(
                f"[ok] Loaded archetype signals: {len(state.archetype_staples)} cards with staples, {len(state.archetype_cooccurrence)} cards with co-occurrence"
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

    # Summary (caller logs the per-game summary; keep debug-level here)
    loaded_count = sum(status.values())
    total_count = len(status)
    loaded_signals = [name for name, loaded in status.items() if loaded]
    missing_signals = [name for name, loaded in status.items() if not loaded]

    logger.debug(
        "Signal loading: %d/%d loaded. Available: %s",
        loaded_count,
        total_count,
        ", ".join(loaded_signals) if loaded_signals else "none",
    )
    if missing_signals:
        logger.debug(f"Missing signals: {', '.join(missing_signals)}")

    return status
