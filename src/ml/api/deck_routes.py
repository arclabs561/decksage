"""Deck operation endpoints: complete, suggest, patch."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from ..deck_building.deck_completion import (
    CompletionConfig,
    greedy_complete,
    suggest_additions,
)
from .models import (
    ApiState,
    CompleteRequest,
    CompleteResponse,
    DeckParseRequest,
    DeckParseResponse,
    PatchRequest,
    SimilarityRequest,
    SuggestActionsRequest,
    SuggestActionsResponse,
    SuggestedAction,
    UseCaseEnum,
    get_state,
)


# deck_patch module - optional dependency
try:
    from ..deck_building.deck_patch import DeckPatch, DeckPatchResult, apply_deck_patch
except ImportError:
    DeckPatch = None
    DeckPatchResult = None
    apply_deck_patch = None

try:
    from ..utils.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger("decksage.api.deck_routes")


router = APIRouter()


# ---------------------------------------------------------------------------
# Archetype detection (inline, mirrors scripts/training/build_archetype_templates.py)
# ---------------------------------------------------------------------------


def _detect_archetype(
    deck: dict,
    game: str,
    templates: list[dict],
) -> tuple[str | None, dict | None, float]:
    """Detect archetype from seed deck by weighted Jaccard overlap with templates.

    Returns (archetype_name, matching_template_dict, score).
    Returns (None, None, 0.0) if no templates or no match above threshold.
    """
    if not templates:
        return None, None, 0.0

    from ..deck_building.deck_completion import _main_partition_name

    part = _main_partition_name(game)
    deck_set: set[str] = set()
    for p in deck.get("partitions", []) or []:
        if p.get("name") != part:
            continue
        for card in p.get("cards", []) or []:
            name = str(card.get("name", ""))
            if name:
                deck_set.add(name)

    if not deck_set:
        return None, None, 0.0

    best_name: str | None = None
    best_template: dict | None = None
    best_score = 0.0

    for t in templates:
        core_cards = {name for name, _ in (t.get("core_cards") or [])}
        flex_cards = {name for name, _ in (t.get("flex_cards") or [])}
        template_all = core_cards | flex_cards
        if not template_all:
            continue
        core_overlap = len(deck_set & core_cards)
        flex_overlap = len(deck_set & flex_cards)
        # Weighted Jaccard: core matches count double
        denom = (
            2 * len(core_cards) + len(flex_cards) + len(deck_set) - 2 * core_overlap - flex_overlap
        )
        score = (2 * core_overlap + flex_overlap) / denom if denom > 0 else 0.0
        if score > best_score:
            best_score = score
            best_name = t.get("name")
            best_template = t

    # Minimum threshold to avoid spurious matches
    if best_score < 0.02:
        return None, None, 0.0

    return best_name, best_template, round(best_score, 4)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_PARTITIONS = 10
_MAX_CARDS_PER_PARTITION = 500

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
            if len(card_entries) > _MAX_CARDS_PER_PARTITION:
                raise HTTPException(
                    status_code=422,
                    detail=f"Too many cards in partition (max {_MAX_CARDS_PER_PARTITION})",
                )
            # Remap legacy "Main" to game-specific partition name (e.g. "Main Deck" for YGO/Pokemon)
            actual_name = part_name
            if part_name.lower() == "main":
                actual_name = _main_partition_name(game)
            partitions.append({"name": actual_name, "cards": card_entries})
    if len(partitions) > _MAX_PARTITIONS:
        raise HTTPException(status_code=422, detail=f"Too many partitions (max {_MAX_PARTITIONS})")
    if partitions:
        return {"partitions": partitions}
    return deck


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

        # Late import app to avoid circular dependency
        from .api import app

        _pm = getattr(app.state, "price_manager", None) or MarketDataManager()
        app.state.price_manager = _pm

        def price_fn(card: str) -> float | None:
            p = _pm.get_price(card)
            return float(p.usd) if p and p.usd else None

    except (ImportError, OSError):
        # Fallback: Scryfall price data (loaded from JSON)
        if state.price_data:
            _prices = state.price_data

            def price_fn(card: str) -> float | None:
                prices = _prices.get(card, {})
                usd = prices.get("usd")
                return float(usd) if usd else None

        elif state.deck_frequency:
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


def _make_candidate_fn(game: str, mode: str | None, task_type: str | None = None):
    forced = (mode or "").lower().strip()

    def fn(card: str, k: int):
        # Late import to avoid circular dependency
        from .api import _similar_impl

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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/deck/parse", response_model=DeckParseResponse)
def parse_deck(req: DeckParseRequest):
    """Parse a raw deck list text into DeckSage partition format."""
    from ..utils.deck_parser import parse_deck_text

    result = parse_deck_text(req.text, game=req.game)
    if "error" in result:
        return DeckParseResponse(error=result["error"])
    return DeckParseResponse(partitions=result["partitions"])


@router.post("/deck/apply_patch", response_model=DeckPatchResult)
def deck_apply_patch(req: PatchRequest):
    # Late import to avoid circular dependency
    from .models import _require_game

    game = _require_game(req.game)
    req.deck = _normalize_deck_format(req.deck, game)
    return apply_deck_patch(
        game,
        req.deck,
        req.patch,
        lenient_size=not bool(req.strict_size),
        check_legality=bool(req.check_legality),
    )


@router.post("/deck/suggest_actions", response_model=SuggestActionsResponse)
def suggest_actions(req: SuggestActionsRequest):
    # Late import to avoid circular dependency
    from .models import _require_game

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
    except (ImportError, OSError):
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

    t0 = time.time()
    # Build tag weight fn if provided
    tw = req.tag_weights or {}

    def tag_weight_fn(tag: str) -> float:
        return float(tw.get(tag, 1.0))

    # Get archetype from request or auto-detect from deck
    archetype = getattr(req, "archetype", None)
    archetype_staples = state.archetype_staples if hasattr(state, "archetype_staples") else None
    sa_archetype_score: float = 0.0
    if not archetype and state.archetype_templates:
        _det_name, _det_tmpl, sa_archetype_score = _detect_archetype(
            req.deck, game, state.archetype_templates
        )
        if _det_name:
            archetype = _det_name
            logger.debug(
                "suggest_actions: auto-detected archetype '%s' (score=%.4f)",
                archetype,
                sa_archetype_score,
            )

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

        sa_adj = state.graph_data.get("adj") if state.graph_data else None
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
            adj=sa_adj,
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
    if archetype:
        metrics["archetype"] = archetype
        metrics["archetype_score"] = sa_archetype_score

    return SuggestActionsResponse(actions=actions, metrics=metrics, feedback_url="/v1/feedback")


@router.post("/deck/complete", response_model=CompleteResponse)
def complete_deck(req: CompleteRequest):
    # Late import to avoid circular dependency
    from .models import _require_game

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
    except (ImportError, OSError):
        pass  # Non-fatal

    game = _require_game(req.game)
    state = get_state(game)
    req.deck = _normalize_deck_format(req.deck, game)

    # Auto-detect archetype from seed deck if not explicitly set
    detected_archetype: str | None = None
    detected_archetype_score: float = 0.0
    matched_template: dict | None = None
    if req.archetype and state.archetype_templates:
        # Explicit archetype: find matching template by name
        for t in state.archetype_templates:
            if t.get("name", "").lower() == req.archetype.lower():
                matched_template = t
                detected_archetype = t.get("name")
                detected_archetype_score = 1.0
                break
        if not matched_template:
            logger.debug("Requested archetype '%s' not found in templates", req.archetype)
    elif state.archetype_templates:
        # Auto-detect from seed deck
        detected_archetype, matched_template, detected_archetype_score = _detect_archetype(
            req.deck, game, state.archetype_templates
        )
        if detected_archetype:
            logger.debug(
                "Auto-detected archetype '%s' (score=%.4f)",
                detected_archetype,
                detected_archetype_score,
            )

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

    t0 = time.time()

    # Choose completion method
    _ot_metrics: dict = {}
    quality_metrics = None
    if req.method == "ot":
        from ..deck_building.deck_completion import _main_partition_name
        from ..deck_building.ot_completion import OTCompletionConfig, ot_complete_deck

        # Build card color identity map for Commander CI filtering
        card_color_identity: dict[str, set[str]] | None = None
        if deck_colors and state.card_metadata and req.format and req.format.lower() == "commander":
            card_ci: dict[str, set[str]] = {}
            for cname, meta in state.card_metadata.items():
                ci_str = meta.get("color_identity_str", "")
                card_ci[cname] = _effective_color_identity(cname, ci_str)
            card_color_identity = card_ci

        ot_cfg = OTCompletionConfig(
            game=game,
            target_main_size=req.target_main_size or (40 if game == "yugioh" else 60),
            embedding_weight=req.embedding_weight,
            role_weight=req.role_weight,
            curve_weight=req.curve_weight,
            sinkhorn_reg=req.sinkhorn_reg,
            format=req.format,
            legality_data=state.legality_data,
            color_identity=deck_colors,
            card_color_identity=card_color_identity,
            archetype_template=matched_template,
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
        beam_adj = state.graph_data.get("adj") if state.graph_data else None

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
                adj=beam_adj,
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
            curve_target=(
                {int(k): v for k, v in matched_template["cmc_histogram"].items()}
                if matched_template and "cmc_histogram" in matched_template
                else req.curve_target
            ),
        )
        # Extract steps from beam search (simplified - beam search doesn't track steps the same way)
        steps: list[dict] = []  # Beam search doesn't return steps in same format
        quality_metrics = None
    else:
        adj = state.graph_data.get("adj") if state.graph_data else None
        deck_out, steps, quality_metrics = greedy_complete(
            game,  # type: ignore[arg-type]
            req.deck,
            cand_fn,
            cfg,
            price_fn=price_fn,
            tag_set_fn=tag_set_fn,
            adj=adj,
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
        except (ValueError, KeyError) as exc:
            # Do not fail response; record as error with details
            strict_errors = [f"strict_validation_exception: {exc}"]

    elapsed_ms = int((time.time() - t0) * 1000)

    # Assess deck quality if we have the necessary functions
    # (reuse cmc_fn from _build_deck_hooks, don't redefine)
    if tag_set_fn:
        try:
            from ..deck_building.deck_quality import assess_deck_quality

            # Assess quality (reference decks optional for now)
            quality = assess_deck_quality(
                deck=deck_out,
                game=game,
                tag_set_fn=tag_set_fn,
                cmc_fn=cmc_fn,
                reference_decks=(
                    [matched_template["core_cards"]]
                    if matched_template and "core_cards" in matched_template
                    else None
                ),
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
    if detected_archetype:
        metrics["archetype"] = detected_archetype
        metrics["archetype_score"] = detected_archetype_score
    if quality_metrics:
        metrics["quality"] = quality_metrics
    # Include OT-specific metrics when method=ot
    if req.method == "ot" and _ot_metrics:
        metrics["ot"] = _ot_metrics

    return CompleteResponse(
        deck=deck_out, steps=steps, metrics=metrics, feedback_url="/v1/feedback"
    )
