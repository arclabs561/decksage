#!/usr/bin/env python3
"""
Deck completion utilities: candidate generation and greedy completion.

Uses similarity methods (embedding / jaccard / fusion) and functional taggers
to propose add/remove/replace actions, filters by legality/copy limits using
validators, and applies actions via deck_patch.apply_deck_patch.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Callable, cast, Iterable, Literal, Sequence

from ..deck_building.deck_patch import DeckPatch, DeckPatchResult, apply_deck_patch
from ..data.card_resolver import CardResolver

# Align with current validator models; generic Deck/DeckCard types removed
from ..validation.validators.models import Partition  # type: ignore

logger = logging.getLogger("decksage.completion")


CandidateFn = Callable[[str, int], list[tuple[str, float]]]
PriceFn = Callable[[str], float | None]
TagSetFn = Callable[[str], set[str]]
TagWeightFn = Callable[[str], float]
CMCFn = Callable[[str], int | None]


@dataclass
class CompletionConfig:
    game: Literal["magic", "yugioh", "pokemon"] = "magic"
    target_main_size: int | None = None  # If None, rely on validator rules
    top_k_per_gap: int = 10
    max_steps: int = 60
    budget_max: float | None = None
    method: Literal["embedding", "jaccard", "fusion"] = "fusion"
    coverage_weight: float = 0.15  # boost per new functional tag


def _main_partition_name(game: str) -> str:
    if game == "magic":
        return "Main"
    if game == "yugioh":
        return "Main Deck"
    return "Main Deck"  # pokemon


def _current_size(deck: dict, part_name: str) -> int:
    for p in deck.get("partitions", []) or []:
        if p.get("name") == part_name:
            return sum(c.get("count", 0) for c in p.get("cards", []) or [])
    return 0


def _cards_in_partition(deck: dict, part_name: str) -> set[str]:
    for p in deck.get("partitions", []) or []:
        if p.get("name") == part_name:
            return {c.get("name") for c in p.get("cards", []) or []}
    return set()


def _legal_add(
    game: Literal["magic", "yugioh", "pokemon"],
    deck: dict,
    card: str,
) -> bool:
    """
    Legality check for incremental add that ignores deck-size requirements.
    Only enforce simple copy limits to permit incomplete deck building.
    """
    # Compute current total copies across partitions
    total = 0
    for p in deck.get("partitions", []) or []:
        for c in p.get("cards", []) or []:
            if c.get("name") == card:
                total += int(c.get("count", 0))

    # Game-specific copy limits (simplified)
    if game == "yugioh":
        return total + 1 <= 3

    if game == "pokemon":
        # Basic Energy exempt from 4-copy rule
        BASIC_ENERGY = {
            "Grass Energy",
            "Fire Energy",
            "Water Energy",
            "Lightning Energy",
            "Psychic Energy",
            "Fighting Energy",
            "Darkness Energy",
            "Metal Energy",
            "Fairy Energy",
        }
        if card in BASIC_ENERGY:
            return True
        return total + 1 <= 4

    # magic
    BASIC_LANDS = {
        "Plains",
        "Island",
        "Swamp",
        "Mountain",
        "Forest",
        "Wastes",
        "Snow-Covered Plains",
        "Snow-Covered Island",
        "Snow-Covered Swamp",
        "Snow-Covered Mountain",
        "Snow-Covered Forest",
    }

    if card in BASIC_LANDS:
        return True

    fmt = (deck.get("format") or "").strip()
    singleton_formats = {"Commander", "cEDH", "Brawl", "Duel Commander"}
    if fmt in singleton_formats:
        return total + 1 <= 1
    return total + 1 <= 4


def suggest_additions(
    game: Literal["magic", "yugioh", "pokemon"],
    deck: dict,
    candidate_fn: CandidateFn,
    top_k: int = 20,
    *,
    price_fn: PriceFn | None = None,
    max_unit_price: float | None = None,
    tag_set_fn: TagSetFn | None = None,
    tag_weight_fn: TagWeightFn | None = None,
    coverage_weight: float = 0.0,
    cmc_fn: CMCFn | None = None,
    curve_target: dict[int, float] | None = None,
    curve_weight: float = 0.0,
    return_metrics: bool = False,
) -> list[tuple[str, float]] | tuple[list[tuple[str, float]], dict]:
    part = _main_partition_name(game)
    resolver = CardResolver()
    have = _cards_in_partition(deck, part)

    # Pick a seed representative: use the most frequent/current first card if present
    seeds = list(have)[:5] or []
    scores: dict[str, float] = {}
    for s in seeds:
        for cand, score in candidate_fn(s, top_k):
            if any(resolver.equals(cand, h) for h in have):
                continue
            scores[cand] = max(scores.get(cand, 0.0), float(score))

    # Rank by score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    # Legality filter by dry-run add
    legal = [(c, sc) for c, sc in ranked if _legal_add(game, deck, c)]
    num_raw = len(ranked)
    num_legal = len(legal)

    # Budget filter
    if price_fn is not None and max_unit_price is not None:
        affordable: list[tuple[str, float]] = []
        fallbacks: list[tuple[str, float]] = []
        for c, sc in legal:
            p = price_fn(c)
            if p is None:
                # keep as fallback if nothing else survives
                fallbacks.append((c, sc * 0.9))
                continue
            if p <= max_unit_price:
                affordable.append((c, sc))
        legal = affordable if affordable else fallbacks
    num_budget = len(legal)

    # Coverage boost: prefer candidates that add functional tags not yet in deck
    if tag_set_fn is not None and coverage_weight > 0:
        # Build deck tag set
        deck_tag_set: set[str] = set()
        for p in deck.get("partitions", []) or []:
            if p.get("name") != part:
                continue
            for card in p.get("cards", []) or []:
                deck_tag_set |= tag_set_fn(resolver.canonical(str(card.get("name", ""))))

        boosted: list[tuple[str, float]] = []
        # Optional curve heuristic (requires cmc_fn and target)
        def curve_delta_boost(card: str) -> float:
            if cmc_fn is None or not curve_target:
                return 0.0
            # Build current CMC hist
            hist: dict[int, int] = {}
            total = 0
            for p in deck.get("partitions", []) or []:
                if p.get("name") != part:
                    continue
                for cc in p.get("cards", []) or []:
                    cmc = cmc_fn(resolver.canonical(str(cc.get("name", ""))))
                    if cmc is None:
                        continue
                    hist[cmc] = hist.get(cmc, 0) + int(cc.get("count", 0))
                    total += int(cc.get("count", 0))
            if total == 0:
                return 0.0
            # L1 distance between current normalized hist and target
            def l1_dist(h: dict[int, int]) -> float:
                dist = 0.0
                for k, target_p in curve_target.items():
                    actual_p = h.get(k, 0) / total
                    dist += abs(actual_p - float(target_p))
                return dist
            before = l1_dist(hist)
            # After adding one copy of candidate
            cand_cmc = cmc_fn(resolver.canonical(card))
            if cand_cmc is None:
                return 0.0
            hist2 = dict(hist)
            hist2[cand_cmc] = hist2.get(cand_cmc, 0) + 1
            after = l1_dist(hist2)
            improvement = max(0.0, before - after)
            return curve_weight * improvement

        for c, sc in legal:
            cand_tags = tag_set_fn(resolver.canonical(c))
            new_tags = cand_tags - deck_tag_set
            # Weighted tag gain
            if tag_weight_fn is not None:
                wsum = 0.0
                for t in new_tags:
                    try:
                        wsum += float(tag_weight_fn(t))
                    except Exception:
                        continue
                new_score = wsum
            else:
                new_score = float(len(new_tags))
            # Diminishing returns on tag gain
            tag_boost = coverage_weight * (1.0 - (2.718281828459045 ** (-0.5 * new_score)))
            # Curve boost (small)
            cb = curve_delta_boost(c)
            boosted.append((c, sc * (1.0 + tag_boost + cb)))
        boosted.sort(key=lambda x: x[1], reverse=True)
        metrics = {
            "num_candidates_raw": num_raw,
            "num_candidates_legal": num_legal,
            "num_candidates_budget": num_budget,
        }
        return (boosted, metrics) if return_metrics else boosted

    metrics = {
        "num_candidates_raw": num_raw,
        "num_candidates_legal": num_legal,
        "num_candidates_budget": num_budget,
    }
    return (legal, metrics) if return_metrics else legal


def greedy_complete(
    game: Literal["magic", "yugioh", "pokemon"],
    deck: dict,
    candidate_fn: CandidateFn,
    cfg: CompletionConfig | None = None,
    *,
    price_fn: PriceFn | None = None,
    tag_set_fn: TagSetFn | None = None,
) -> tuple[dict, list[dict]]:
    cfg = cfg or CompletionConfig(game=game)
    target_main = cfg.target_main_size
    main_name = _main_partition_name(game)
    steps: list[dict] = []
    state = deck

    # Loop until validator constraints satisfied (size goal heuristic if provided)
    for _ in range(cfg.max_steps):
        size = _current_size(state, main_name)
        if target_main is not None and size >= target_main:
            break

        # Generate candidates
        cands = suggest_additions(
            game,
            state,
            candidate_fn,
            top_k=cfg.top_k_per_gap,
            price_fn=price_fn,
            max_unit_price=cfg.budget_max,
            tag_set_fn=tag_set_fn,
            coverage_weight=cfg.coverage_weight,
        )
        if not cands:
            break

        # Take best candidate
        cand, _ = cands[0]
        patch = DeckPatch(
            ops=[{"op": "add_card", "partition": main_name, "card": cand, "count": 1}],
        )
        res = apply_deck_patch(game, state, patch)
        if not res.is_valid or not res.deck:
            # Skip illegal candidate and continue
            cands = cands[1:]
            if not cands:
                break
            continue

        steps.append({"op": "add_card", "partition": main_name, "card": cand, "count": 1})
        state = res.deck

    return state, steps


__all__ = ["CompletionConfig", "greedy_complete", "suggest_additions"]


