#!/usr/bin/env python3
"""
LLM Data Quality Auditor (optional batch validation).

This module uses LLMs for semantic validation that deterministic rules can't catch.
It is intentionally optional and should not be part of the core ML pipeline.

It must remain cheap to import and safe to initialize in dev/test environments:
- No network calls in `__init__`
- Graceful fallback to a tiny tracked fixture when full datasets are absent
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any


try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - pydantic is expected in dev/test
    BaseModel = object  # type: ignore

    def Field(*_args: Any, **_kwargs: Any) -> Any:  # type: ignore
        return None


from ..utils.paths import PATHS
from ..utils.pydantic_ai_helpers import HAS_PYDANTIC_AI, make_agent


logger = logging.getLogger(__name__)

__all__ = ["HAS_PYDANTIC_AI", "DataQualityValidator"]


# Auto-load .env to pick up provider keys (optional).
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except ImportError:
    pass


class ArchetypeValidation(BaseModel):
    """LLM validation of archetype label."""

    deck_id: str = Field(description="Deck identifier")
    claimed_archetype: str = Field(description="Archetype label in metadata")
    top_cards: list[str] = Field(description="Representative card names")
    is_consistent: bool = Field(description="Does archetype match the cards?")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence 0-1")
    issues: list[str] = Field(default_factory=list, description="Problems found")
    suggested_archetype: str | None = Field(None, description="Better label if wrong")
    reasoning: str = Field(description="Short rationale")


ARCHETYPE_SYSTEM_PROMPT = """You are an expert TCG judge validating deck archetype labels.

Task:
- Decide whether the claimed archetype matches the deck's cards.
- Be strict but fair. If uncertain, say so with lower confidence.

Return a structured response that matches the output schema."""


ARCHETYPE_MODEL = os.getenv("VALIDATOR_MODEL_ARCHETYPE", "openai/gpt-4o-mini")
archetype_agent = None
if HAS_PYDANTIC_AI:
    # Creating the agent is cheap and does not make network calls.
    archetype_agent = make_agent(ARCHETYPE_MODEL, ArchetypeValidation, ARCHETYPE_SYSTEM_PROMPT)


class DataQualityValidator:
    """Orchestrates LLM-driven audits (semantic checks, post-hoc)."""

    def __init__(self, output_dir: Path | None = None, decks_path: Path | None = None):
        if not HAS_PYDANTIC_AI:
            raise ImportError("pydantic-ai required")

        self.output_dir = output_dir or (PATHS.experiments / "data_quality")
        self.output_dir.mkdir(exist_ok=True, parents=True)

        self.decks_path = decks_path or self._choose_decks_path()
        self.decks = self._load_decks(self.decks_path)

        logger.info("Loaded %s decks for validation (path=%s)", len(self.decks), self.decks_path)

    @staticmethod
    def _deck_card_names(deck: dict[str, Any]) -> list[str]:
        """Best-effort list of card names for prompting."""
        cards = deck.get("cards")
        out: list[str] = []

        if isinstance(cards, list):
            for c in cards:
                if isinstance(c, str):
                    out.append(c)
                elif isinstance(c, dict):
                    name = c.get("name") or c.get("Name")
                    if isinstance(name, str) and name.strip():
                        out.append(name.strip())
            if out:
                return out

        parts = deck.get("partitions") or deck.get("Partitions")
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict):
                    continue
                cs = part.get("cards") or part.get("Cards")
                if not isinstance(cs, list):
                    continue
                for c in cs:
                    if not isinstance(c, dict):
                        continue
                    name = c.get("name") or c.get("Name")
                    if isinstance(name, str) and name.strip():
                        out.append(name.strip())

        return out

    async def validate_archetype_sample(self, sample_size: int = 50) -> list[ArchetypeValidation]:
        """Validate archetype labels on a random sample (real LLM calls)."""
        if not HAS_PYDANTIC_AI or archetype_agent is None:
            raise ImportError("pydantic-ai required")

        import random

        if not self.decks:
            return []

        sample = random.sample(self.decks, min(sample_size, len(self.decks)))
        results: list[ArchetypeValidation] = []

        for deck in sample:
            deck_id = str(deck.get("deck_id") or "unknown")
            claimed = str(deck.get("archetype") or "Unknown")
            fmt = str(deck.get("format") or "Unknown")
            top_cards = self._deck_card_names(deck)[:15]

            prompt = (
                "Deck ID: "
                + deck_id
                + "\nClaimed Archetype: "
                + claimed
                + "\nFormat: "
                + fmt
                + "\nTop Cards: "
                + ", ".join(top_cards)
                + "\n\nDoes this archetype label accurately describe these cards?"
            )

            run = await archetype_agent.run(prompt)
            results.append(run.output)

        return results

    @staticmethod
    def _fixture_decks_path() -> Path:
        return (
            Path(__file__).resolve().parent.parent
            / "tests"
            / "fixtures"
            / "decks_export_hetero_small.jsonl"
        )

    @classmethod
    def _choose_decks_path(cls) -> Path:
        candidates: list[Path] = [
            PATHS.decks_with_metadata,
            PATHS.decks_all_final,
            PATHS.decks_all_enhanced,
            PATHS.decks_all_unified,
            PATHS.backend / "decks_hetero.jsonl",
            cls._fixture_decks_path(),
        ]

        for p in candidates:
            if p.exists():
                if p == cls._fixture_decks_path():
                    logger.warning("Using small test fixture decks at %s", p)
                return p

        raise FileNotFoundError(f"No deck metadata found. Checked: {[str(p) for p in candidates]}")

    @staticmethod
    def _load_decks(path: Path) -> list[dict[str, Any]]:
        # Validate + normalize using deterministic Pydantic deck models.
        from .validators.loader import load_decks_lenient

        validated_decks = load_decks_lenient(
            path,
            game="auto",
            check_legality=False,
            verbose=False,
        )
        return [d.model_dump() for d in validated_decks]
