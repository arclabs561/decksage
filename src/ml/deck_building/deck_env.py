#!/usr/bin/env python3
"""
Minimal deck completion environment (Gym-like).

This is a lightweight interface for planning/learning:
- reset(initial_deck)
- step(action) where action is a patch op (add/remove/replace/move)
- observation() exposes a compact state summary (sizes, unique count)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Literal, Optional

from .deck_patch import DeckPatch, apply_deck_patch
from ..validation.validators.models import DeckCard

logger = logging.getLogger("decksage.deck_env")


# Simplified Deck model for the environment; real validation happens elsewhere
class Deck:
    def __init__(self, game: Literal["magic", "yugioh", "pokemon"], target_main_size: Optional[int] = None):
        self.game = game
        self.target_main_size = target_main_size
        self._deck: dict | None = None

    def reset(self, deck: dict) -> dict:
        self._deck = deck
        return self.observation()

    def observation(self) -> dict:
        assert self._deck is not None
        parts = self._deck.get("partitions", []) or []
        obs = {
            "format": self._deck.get("format"),
            "archetype": self._deck.get("archetype"),
            "partitions": {p.get("name"): {
                "size": sum(c.get("count", 0) for c in p.get("cards", []) or []),
                "unique": len(p.get("cards", []) or []),
            } for p in parts},
        }
        return obs

    def step(self, action: dict) -> StepResult:
        assert self._deck is not None
        patch = DeckPatch(ops=[action])
        res = apply_deck_patch(self.game, self._deck, patch)
        if not res.is_valid or not res.deck:
            # Invalid action: negative reward, no state change
            return StepResult(deck=self._deck, reward=-1.0, done=False, info={"errors": res.errors})

        self._deck = res.deck
        done = False
        reward = 0.0
        if self.target_main_size is not None:
            main = {"magic": "Main", "yugioh": "Main Deck"}.get(self.game, "Main Deck")
            size = 0
            for p in self._deck.get("partitions", []) or []:
                if p.get("name") == main:
                    size = sum(c.get("count", 0) for c in p.get("cards", []) or [])
                    break
            reward = 1.0 if size <= self.target_main_size else -0.1
            done = size >= self.target_main_size

        return StepResult(deck=self._deck, reward=reward, done=done, info={})


__all__ = ["DeckCompletionEnv", "StepResult"]





