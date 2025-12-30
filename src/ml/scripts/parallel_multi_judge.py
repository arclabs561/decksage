#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-ai>=0.0.12",
# ]
# ///
"""
Parallel multi-judge labeling for faster processing.

Uses concurrent.futures to parallelize judge calls.
"""

from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any

try:
    from pydantic_ai import Agent
    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import with path handling
import sys
from pathlib import Path as P

script_dir = P(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

try:
    from generate_labels_for_new_queries_optimized import (
        make_label_generation_agent,
        generate_labels_for_query_with_retry,
    )
    HAS_LABELING = True
except ImportError as e:
    HAS_LABELING = False
    logger.error(f"Labeling scripts not available: {e}")

# Try to use cache invalidation strategy
try:
    from ml.utils.cache_invalidation import CacheInvalidationStrategy
    from ml.evaluation.expanded_judge_criteria import get_prompt_version
    HAS_CACHE_INVALIDATION = True
    _current_prompt_version = get_prompt_version()
    _cache_strategy = CacheInvalidationStrategy(
        prompt_version=_current_prompt_version,
        max_age_days=30,
    )
except ImportError:
    HAS_CACHE_INVALIDATION = False
    _cache_strategy = None
    _current_prompt_version = None

# Try to use LLM cache
try:
    from ml.utils.llm_cache import LLMCache, load_config
    HAS_LLM_CACHE = True
    _llm_cache = LLMCache(load_config(), scope="labeling")
except ImportError:
    HAS_LLM_CACHE = False
    _llm_cache = None


def generate_labels_single_judge(
    query: str,
    judge_id: int,
    use_case: str | None = None,
    game: str | None = None,
) -> dict[str, list[str]]:
    """Generate labels from a single judge (for parallel execution)."""
    # Try cache first (if available)
    if HAS_LLM_CACHE and _llm_cache:
        # Use cache invalidation strategy if available
        if HAS_CACHE_INVALIDATION and _cache_strategy:
            cache_key = _cache_strategy.get_cache_key(
                query=query,
                use_case=use_case,
                game=game,
                judge_id=judge_id,
            )
        else:
            # Fallback to simple cache key
            cache_key = f"label_{query}_{use_case}_{game}_{judge_id}"
        
        cached = _llm_cache.get(cache_key)
        
        # Check if cached entry should be invalidated (if strategy available)
        if cached and HAS_CACHE_INVALIDATION and _cache_strategy:
            # Handle both dict and non-dict cached values
            cache_entry = cached if isinstance(cached, dict) else {"data": cached}
            if _cache_strategy.should_invalidate(
                cache_entry,
                current_prompt_version=_current_prompt_version,
            ):
                logger.debug(f"  Cache entry invalidated for judge {judge_id} (prompt version mismatch)")
                cached = None
        
        if cached:
            # Extract data from annotated cache entry or use directly
            if isinstance(cached, dict) and "data" in cached:
                labels = cached["data"]
            else:
                labels = cached
            logger.debug(f"  Using cached labels for judge {judge_id}")
            return labels if labels and any(labels.values()) else {}
    
    # Generate labels (cache miss or no cache)
    agent = make_label_generation_agent()
    if not agent:
        logger.warning(f"Could not create agent for judge {judge_id}")
        return {}
    
    # Pass game parameter if function supports it
    try:
        import inspect
        sig = inspect.signature(generate_labels_for_query_with_retry)
        if 'game' in sig.parameters:
            labels = generate_labels_for_query_with_retry(agent, query, use_case, game=game)
        else:
            labels = generate_labels_for_query_with_retry(agent, query, use_case)
    except Exception:
        # Fallback if inspection fails
        labels = generate_labels_for_query_with_retry(agent, query, use_case)
    
    # Cache the result with version metadata
    if labels and HAS_LLM_CACHE and _llm_cache:
        # Ensure cache_key is defined (reuse from earlier or generate new)
        if 'cache_key' not in locals():
            if HAS_CACHE_INVALIDATION and _cache_strategy:
                cache_key = _cache_strategy.get_cache_key(
                    query=query,
                    use_case=use_case,
                    game=game,
                    judge_id=judge_id,
                )
            else:
                cache_key = f"label_{query}_{use_case}_{game}_{judge_id}"
        
        if HAS_CACHE_INVALIDATION and _cache_strategy:
            # Annotate with version metadata
            annotated = _cache_strategy.annotate_cache_entry(
                {"data": labels},
                prompt_version=_current_prompt_version,
            )
            _llm_cache.set(cache_key, annotated)
        else:
            _llm_cache.set(cache_key, labels)
    
    return labels if labels and any(labels.values()) else {}


def generate_labels_parallel(
    query: str,
    num_judges: int = 3,
    use_case: str | None = None,
    game: str | None = None,
    max_workers: int = 3,
    timeout: float = 120.0,  # 2 minutes per judge
) -> dict[str, Any]:
    """
    Generate labels using multiple judges in parallel.
    
    Faster than sequential multi-judge for large batches.
    """
    if not HAS_PYDANTIC_AI or not HAS_LABELING:
        logger.error("Required dependencies not available")
        return {}
    
    # Generate labels in parallel
    all_judgments = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(generate_labels_single_judge, query, judge_id, use_case, game): judge_id
            for judge_id in range(num_judges)
        }
        
        # Wait for all futures with overall timeout
        try:
            for future in as_completed(futures, timeout=timeout * num_judges):
                judge_id = futures[future]
                try:
                    labels = future.result(timeout=1.0)  # Small timeout for result retrieval
                    if labels:
                        all_judgments.append(labels)
                except FutureTimeoutError:
                    logger.warning(f"Judge {judge_id} timed out retrieving result")
                except Exception as e:
                    logger.warning(f"Judge {judge_id} failed: {e}")
        except FutureTimeoutError:
            logger.warning(f"Overall labeling timed out after {timeout * num_judges}s")
            # Cancel remaining futures
            for future in futures:
                future.cancel()
    
    if not all_judgments:
        logger.warning(f"No valid judgments for {query}")
        return {
            "highly_relevant": [],
            "relevant": [],
            "somewhat_relevant": [],
            "marginally_relevant": [],
            "irrelevant": [],
            "iaa": {
                "num_judges": 0,
                "agreement_rate": 0.0,
            },
        }
    
    # Validate each judgment for internal contradictions (same as sequential version)
    # Judges are isolated - each runs independently with no information sharing
    validated_judgments = []
    for i, judgment in enumerate(all_judgments):
        # Check for contradictions within a single judgment
        card_to_levels = {}  # card -> set of levels it appears in
        for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant", "irrelevant"]:
            for card in judgment.get(level, []):
                if card not in card_to_levels:
                    card_to_levels[card] = set()
                card_to_levels[card].add(level)
        
        # Fix contradictions: keep card in highest relevance level only
        cleaned_judgment = {
            "highly_relevant": [],
            "relevant": [],
            "somewhat_relevant": [],
            "marginally_relevant": [],
            "irrelevant": [],
        }
        
        level_priority = {
            "highly_relevant": 4,
            "relevant": 3,
            "somewhat_relevant": 2,
            "marginally_relevant": 1,
            "irrelevant": 0,
        }
        
        for card, levels in card_to_levels.items():
            if len(levels) > 1:
                # Contradiction detected - keep highest level
                best_level = max(levels, key=lambda l: level_priority[l])
                logger.warning(f"Judge {i} contradiction: {card} in multiple levels {levels}, keeping {best_level}")
                cleaned_judgment[best_level].append(card)
            else:
                # No contradiction
                cleaned_judgment[list(levels)[0]].append(card)
        
        validated_judgments.append(cleaned_judgment)
    
    # Majority vote (same logic as sequential version)
    # Note: Judges may disagree (expected - measured by IAA)
    # But each judge should be internally consistent (no contradictions)
    card_votes: dict[str, dict[str, int]] = {}
    
    for judgment in validated_judgments:
        for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
            for card in judgment.get(level, []):
                if card not in card_votes:
                    card_votes[card] = {}
                card_votes[card][level] = card_votes[card].get(level, 0) + 1
    
    final_labels = {
        "highly_relevant": [],
        "relevant": [],
        "somewhat_relevant": [],
        "marginally_relevant": [],
        "irrelevant": [],
    }
    
    threshold = len(validated_judgments) / 2
    for card, votes in card_votes.items():
        if votes:
            best_level, vote_count = max(votes.items(), key=lambda x: x[1])
            if vote_count >= threshold:
                final_labels[best_level].append(card)
            # If no majority, card is excluded (judges disagreed too much)
    
    # Compute agreement
    agreement_scores = []
    for card, votes in card_votes.items():
        total_votes = sum(votes.values())
        max_votes = max(votes.values()) if votes else 0
        agreement = max_votes / len(all_judgments) if all_judgments else 0.0
        agreement_scores.append(agreement)
    
    avg_agreement = sum(agreement_scores) / len(agreement_scores) if agreement_scores else 0.0
    
    return {
        **final_labels,
        "iaa": {
            "num_judges": len(all_judgments),
            "agreement_rate": avg_agreement,
            "num_cards": len(card_votes),
        },
    }


def main() -> int:
    """Test parallel multi-judge."""
    parser = argparse.ArgumentParser(description="Parallel multi-judge labeling")
    parser.add_argument("--query", type=str, required=True, help="Query card name")
    parser.add_argument("--num-judges", type=int, default=3, help="Number of judges")
    parser.add_argument("--max-workers", type=int, default=3, help="Max parallel workers")
    
    args = parser.parse_args()
    
    if not HAS_PYDANTIC_AI:
        logger.error("pydantic-ai required")
        return 1
    
    result = generate_labels_parallel(
        args.query,
        num_judges=args.num_judges,
        max_workers=args.max_workers,
    )
    
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

