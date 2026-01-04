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
from typing import Callable, cast, Iterable, Literal, Sequence, Union, Optional

# from ..deck_building.deck_patch import DeckPatch, DeckPatchResult, apply_deck_patch
# TODO: deck_patch module not found, commenting out for now
try:
    from ..deck_building.deck_patch import DeckPatch, DeckPatchResult, apply_deck_patch
except ImportError:
    DeckPatch = None
    DeckPatchResult = None
    apply_deck_patch = None
from ..data.card_resolver import CardResolver

# Align with current validator models; generic Deck/DeckCard types removed
try:
    from ..validation.validators.models import Partition  # type: ignore
except ImportError:
    # Fallback if validators not available
    Partition = None

logger = logging.getLogger("decksage.completion")


CandidateFn = Callable[[str, int], list[tuple[str, float]]]
PriceFn = Callable[[str], Optional[float]]
TagSetFn = Callable[[str], set[str]]
TagWeightFn = Callable[[str], float]
CMCFn = Callable[[str], Optional[int]]


@dataclass
class CompletionConfig:
    game: Literal["magic", "yugioh", "pokemon"] = "magic"
    target_main_size: Optional[int] = None  # If None, rely on validator rules
    top_k_per_gap: int = 10
    max_steps: int = 60
    budget_max: Optional[float] = None
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
    price_fn: Optional[PriceFn] = None,
    max_unit_price: Optional[float] = None,
    tag_set_fn: Optional[TagSetFn] = None,
    tag_weight_fn: TagWeightFn | None = None,
    coverage_weight: float = 0.0,
    cmc_fn: Optional[CMCFn] = None,
    curve_target: Optional[dict[int, float]] = None,
    curve_weight: float = 0.0,
    return_metrics: bool = False,
    # New parameters for role-aware, archetype-aware suggestions
    archetype: Optional[str] = None,
    archetype_staples: Optional[dict[str, dict[str, float]]] = None,
    role_aware: bool = True,
    max_suggestions: int = 10,
) -> list[tuple[str, float]] | tuple[list[tuple[str, float]], dict]:
    part = _main_partition_name(game)
    resolver = CardResolver()
    have = _cards_in_partition(deck, part)

    # Detect role gaps if role-aware
    role_gaps: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    if role_aware and tag_set_fn:
        # Count cards by functional role
        for p in deck.get("partitions", []) or []:
            if p.get("name") != part:
                continue
            for card in p.get("cards", []) or []:
                card_name = resolver.canonical(str(card.get("name", "")))
                tags = tag_set_fn(card_name)
                count = int(card.get("count", 1))
                for role in ["removal", "threat", "card_draw", "ramp", "counter", "tutor"]:
                    if role in tags:
                        role_counts[role] = role_counts.get(role, 0) + count
        
        # Identify gaps (roles with low counts)
        # Typical deck needs: 8-12 removal, 12-16 threats, 4-8 card draw
        role_targets = {
            "removal": 10,
            "threat": 14,
            "card_draw": 6,
            "ramp": 4,
            "counter": 6,
            "tutor": 2,
        }
        for role, target in role_targets.items():
            current = role_counts.get(role, 0)
            if current < target:
                role_gaps[role] = target - current

    # Pick a seed representative: use the most frequent/current first card if present
    seeds = list(have)[:5] or []
    scores: dict[str, float] = {}
    score_reasons: dict[str, str] = {}  # Track why each card scored well
    
    for s in seeds:
        for cand, score in candidate_fn(s, top_k):
            if any(resolver.equals(cand, h) for h in have):
                continue
            scores[cand] = max(scores.get(cand, 0.0), float(score))
    
    # Boost archetype staples if archetype provided
    if archetype and archetype_staples:
        for card in list(scores.keys()):
            card_staples = archetype_staples.get(card, {})
            if archetype in card_staples:
                inclusion_rate = card_staples[archetype]
                # Boost by inclusion rate (0.7-1.0 range)
                boost = 1.0 + (inclusion_rate * 0.5)  # Up to 50% boost
                scores[card] = scores[card] * boost
                score_reasons[card] = f"Archetype staple ({inclusion_rate:.0%} inclusion)"
    
    # Boost cards that fill role gaps
    if role_aware and tag_set_fn and role_gaps:
        for card in list(scores.keys()):
            cand_tags = tag_set_fn(resolver.canonical(card))
            for role, gap_size in role_gaps.items():
                if role in cand_tags:
                    # Boost proportional to gap size
                    boost = 1.0 + (gap_size / 10.0) * 0.3  # Up to 30% boost
                    scores[card] = scores[card] * boost
                    if card not in score_reasons:
                        score_reasons[card] = f"Fills {role} gap"
                    else:
                        score_reasons[card] += f", fills {role} gap"

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
        
        # Limit to max_suggestions (constrained choice)
        if len(boosted) > max_suggestions:
            boosted = boosted[:max_suggestions]
        
        metrics = {
            "num_candidates_raw": num_raw,
            "num_candidates_legal": num_legal,
            "num_candidates_budget": num_budget,
            "role_gaps": role_gaps,
            "role_counts": role_counts,
            "score_reasons": {card: score_reasons.get(card, "Similarity match") for card, _ in boosted[:5]},
        }
        return (boosted, metrics) if return_metrics else boosted

    # Limit to max_suggestions even without coverage boost
    if len(legal) > max_suggestions:
        legal = legal[:max_suggestions]
    
    metrics = {
        "num_candidates_raw": num_raw,
        "num_candidates_legal": num_legal,
        "num_candidates_budget": num_budget,
        "role_gaps": role_gaps,
        "role_counts": role_counts,
        "score_reasons": {card: score_reasons.get(card, "Similarity match") for card, _ in legal[:5]},
    }
    return (legal, metrics) if return_metrics else legal


def greedy_complete(
    game: Literal["magic", "yugioh", "pokemon"],
    deck: dict,
    candidate_fn: CandidateFn,
    cfg: Optional[CompletionConfig] = None,
    *,
    price_fn: Optional[PriceFn] = None,
    tag_set_fn: Optional[TagSetFn] = None,
    assess_quality: bool = False,
    quality_threshold: Optional[float] = None,
) -> tuple[dict, list[dict], Optional[dict[str, Any]]]:
    """
    Complete deck using greedy algorithm with optional quality assessment.
    
    Returns:
        (completed_deck, steps, quality_metrics)
        quality_metrics is None if assess_quality=False
    """
    cfg = cfg or CompletionConfig(game=game)
    target_main = cfg.target_main_size
    main_name = _main_partition_name(game)
    steps: list[dict] = []
    state = deck
    quality_metrics = None

    # Assess initial quality if requested
    if assess_quality:
        try:
            from ..deck_building.deck_quality import assess_deck_quality
            def cmc_fn(card: str) -> Optional[int]:
                # Placeholder - would load from card database
                return None
            initial_quality = assess_deck_quality(
                deck=state,
                game=game,
                tag_set_fn=tag_set_fn or (lambda x: set()),
                cmc_fn=cmc_fn,
            )
        except Exception:
            initial_quality = None

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

        # Check quality threshold if set
        if assess_quality and quality_threshold is not None:
            try:
                current_quality = assess_deck_quality(
                    deck=state,
                    game=game,
                    tag_set_fn=tag_set_fn or (lambda x: set()),
                    cmc_fn=cmc_fn,
                )
                if current_quality.overall_score >= quality_threshold:
                    logger.info(f"Quality threshold reached: {current_quality.overall_score:.2f}")
                    break
            except Exception:
                pass

    # Assess final quality if requested
    if assess_quality:
        try:
            final_quality = assess_deck_quality(
                deck=state,
                game=game,
                tag_set_fn=tag_set_fn or (lambda x: set()),
                cmc_fn=cmc_fn,
            )
            quality_metrics = {
                "initial": {
                    "overall_score": initial_quality.overall_score if initial_quality else None,
                    "mana_curve_score": initial_quality.mana_curve_score if initial_quality else None,
                    "tag_balance_score": initial_quality.tag_balance_score if initial_quality else None,
                    "synergy_score": initial_quality.synergy_score if initial_quality else None,
                } if initial_quality else None,
                "final": {
                    "overall_score": final_quality.overall_score,
                    "mana_curve_score": final_quality.mana_curve_score,
                    "tag_balance_score": final_quality.tag_balance_score,
                    "synergy_score": final_quality.synergy_score,
                },
                "improvement": final_quality.overall_score - (initial_quality.overall_score if initial_quality else 0.0),
            }
        except Exception as e:
            logger.warning(f"Failed to assess final quality: {e}")

    return state, steps, quality_metrics


def suggest_removals(
    game: Literal["magic", "yugioh", "pokemon"],
    deck: dict,
    candidate_fn: CandidateFn,
    *,
    archetype: Optional[str] = None,
    archetype_staples: Optional[dict[str, dict[str, float]]] = None,
    tag_set_fn: Optional[TagSetFn] = None,
    preserve_roles: bool = True,
    max_suggestions: int = 10,
) -> list[tuple[str, float, str]]:
    """
    Suggest cards to remove from the deck.
    
    Returns list of (card, removal_score, reason) tuples.
    Higher score = stronger recommendation to remove.
    
    Strategy:
    1. Find cards with low archetype match (if archetype provided)
    2. Find redundant cards (multiple filling same role)
    3. Consider format legality
    4. Preserve role coverage if requested
    """
    part = _main_partition_name(game)
    resolver = CardResolver()
    have = _cards_in_partition(deck, part)
    
    removals: list[tuple[str, float, str]] = []
    
    # 1. Find cards with low archetype match
    if archetype and archetype_staples:
        for card in have:
            card_staples = archetype_staples.get(card, {})
            if archetype not in card_staples:
                # Card not in archetype staples - candidate for removal
                # Check if it appears in other archetypes (might be meta call)
                other_archetypes = [arch for arch in card_staples.keys() if arch != archetype]
                if not other_archetypes:
                    # Not in any archetype staples - likely weak
                    removals.append((card, 0.8, "low_archetype_match"))
                else:
                    # In other archetypes but not this one - might be meta call
                    removals.append((card, 0.5, f"not_archetype_staple (in {len(other_archetypes)} other archetypes)"))
            else:
                # Card is in archetype, but check inclusion rate
                inclusion_rate = card_staples[archetype]
                if inclusion_rate < 0.3:  # Low inclusion rate
                    removals.append((card, 0.6, f"low_archetype_inclusion ({inclusion_rate:.0%})"))
    
    # 2. Find redundant cards (multiple filling same role)
    if preserve_roles and tag_set_fn:
        role_cards: dict[str, list[str]] = {}
        for p in deck.get("partitions", []) or []:
            if p.get("name") != part:
                continue
            for card_obj in p.get("cards", []) or []:
                # card_obj is a dict with "name" and "count"
                if isinstance(card_obj, dict):
                    card_name = resolver.canonical(str(card_obj.get("name", "")))
                    tags = tag_set_fn(card_name)
                    count = int(card_obj.get("count", 1))
                else:
                    # Fallback: card_obj is already a string
                    card_name = resolver.canonical(str(card_obj))
                    tags = tag_set_fn(card_name)
                    count = 1
                for role in ["removal", "threat", "card_draw", "ramp", "counter", "tutor"]:
                    if role in tags:
                        if role not in role_cards:
                            role_cards[role] = []
                        # Add card once per copy
                        for _ in range(count):
                            role_cards[role].append(card_name)
        
        # If a role has too many cards, suggest removing weakest
        role_thresholds = {
            "removal": 12,  # More than 12 removal spells is excessive
            "threat": 20,   # More than 20 threats is excessive
            "card_draw": 10,  # More than 10 card draw is excessive
            "ramp": 8,      # More than 8 ramp is excessive
            "counter": 10,  # More than 10 counters is excessive
            "tutor": 4,     # More than 4 tutors is excessive
        }
        
        for role, threshold in role_thresholds.items():
            if role in role_cards and len(role_cards[role]) > threshold:
                # Score cards in this role by archetype match
                scored_cards: list[tuple[str, float]] = []
                for card in set(role_cards[role]):  # Unique cards
                    score = 0.5  # Default score
                    if archetype and archetype_staples:
                        card_staples = archetype_staples.get(card, {})
                        if archetype in card_staples:
                            score = card_staples[archetype]  # Use inclusion rate
                    scored_cards.append((card, score))
                
                # Sort by score (lowest = weakest = remove first)
                scored_cards.sort(key=lambda x: x[1])
                
                # Suggest removing weakest cards
                excess = len(role_cards[role]) - threshold
                for card, score in scored_cards[:excess]:
                    if card not in [r[0] for r in removals]:  # Avoid duplicates
                        removals.append((card, 0.7, f"redundant_{role} (excess {role} cards)"))
    
    # Sort by removal score (highest = remove first)
    removals.sort(key=lambda x: x[1], reverse=True)
    
    # Limit to max_suggestions
    if len(removals) > max_suggestions:
        removals = removals[:max_suggestions]
    
    return removals


def suggest_replacements(
    game: Literal["magic", "yugioh", "pokemon"],
    deck: dict,
    card: str,
    candidate_fn: CandidateFn,
    top_k: int = 10,
    *,
    price_fn: Optional[PriceFn] = None,
    max_unit_price: Optional[float] = None,
    tag_set_fn: Optional[TagSetFn] = None,
    archetype: Optional[str] = None,
    archetype_staples: Optional[dict[str, dict[str, float]]] = None,
    upgrade: bool = False,  # If True, prefer better (more expensive) cards
    downgrade: bool = False,  # If True, prefer cheaper alternatives
) -> list[tuple[str, float, str]]:
    """
    Suggest replacements for a specific card.
    
    Returns list of (replacement_card, score, reason) tuples.
    
    Strategy:
    1. Find functional alternatives (similar role)
    2. Consider upgrades (better, more expensive)
    3. Consider downgrades (worse, cheaper)
    4. Maintain role coverage
    """
    part = _main_partition_name(game)
    resolver = CardResolver()
    
    # Get current card's role
    current_role: set[str] = set()
    if tag_set_fn:
        current_role = tag_set_fn(resolver.canonical(card))
    
    # Get current card's price
    current_price = price_fn(card) if price_fn else None
    
    # Find similar cards using candidate function
    candidates: list[tuple[str, float]] = []
    for cand, score in candidate_fn(card, top_k * 2):
        if resolver.equals(cand, card):
            continue
        candidates.append((cand, score))
    
    replacements: list[tuple[str, float, str]] = []
    
    for replacement, similarity_score in candidates:
        # Check if replacement fills same role
        replacement_role: set[str] = set()
        if tag_set_fn:
            replacement_role = tag_set_fn(resolver.canonical(replacement))
        
        role_overlap = len(current_role & replacement_role) / len(current_role | replacement_role) if (current_role | replacement_role) else 0.0
        
        # Base score from similarity
        score = similarity_score
        
        # Boost if fills same role
        if role_overlap > 0.5:
            score *= 1.2
            reason = "functional_alternative"
        else:
            reason = "similar_card"
        
        # Consider upgrades/downgrades
        replacement_price = price_fn(replacement) if price_fn else None
        
        if upgrade and current_price and replacement_price:
            if replacement_price > current_price:
                score *= 1.3  # Boost upgrades
                reason = f"upgrade (${current_price:.2f} → ${replacement_price:.2f})"
        
        if downgrade and current_price and replacement_price:
            if replacement_price < current_price:
                score *= 1.2  # Boost downgrades
                reason = f"budget_alternative (${current_price:.2f} → ${replacement_price:.2f})"
        
        # Boost archetype staples
        if archetype and archetype_staples:
            replacement_staples = archetype_staples.get(replacement, {})
            if archetype in replacement_staples:
                inclusion_rate = replacement_staples[archetype]
                score *= (1.0 + inclusion_rate * 0.3)  # Up to 30% boost
                if "archetype" not in reason:
                    reason += f", archetype_staple ({inclusion_rate:.0%})"
        
        replacements.append((replacement, score, reason))
    
    # Sort by score
    replacements.sort(key=lambda x: x[1], reverse=True)
    
    # Limit to top_k
    if len(replacements) > top_k:
        replacements = replacements[:top_k]
    
    return replacements


__all__ = ["CompletionConfig", "greedy_complete", "suggest_additions", "suggest_removals", "suggest_replacements"]


