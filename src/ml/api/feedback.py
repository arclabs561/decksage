"""
User feedback collection API endpoint.

Collects user judgments on model suggestions for training data.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from collections import defaultdict
from time import time

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

try:
    from ..utils.paths import PATHS
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    PATHS = None

# Import for card validation
# Note: get_state() requires app to be initialized, so we use lazy import
# to avoid circular import issues (api.py imports feedback.py at module level)
try:
    from ..data.card_database import CardDatabase
    HAS_CARD_DB = True
except ImportError:
    HAS_CARD_DB = False

# get_state is imported lazily in _validate_card_name to avoid circular imports
# DO NOT import get_state at module level - it causes circular import
HAS_VALIDATION = HAS_CARD_DB

router = APIRouter(prefix="/v1/feedback", tags=["feedback"])


class TaskType(str, Enum):
    """Type of task being evaluated."""
    similarity = "similarity"
    deck_completion = "deck_completion"
    deck_refinement = "deck_refinement"
    substitution = "substitution"
    contextual_discovery = "contextual_discovery"


class FeedbackRequest(BaseModel):
    """User feedback on a model suggestion."""
    query_card: str = Field(..., description="Query card name")
    suggested_card: str = Field(..., description="Suggested card name")
    task_type: TaskType = Field(..., description="Type of task")
    rating: int = Field(..., ge=0, le=4, description="Relevance rating (0-4)")
    is_substitute: bool | None = Field(None, description="Can suggested_card replace query_card?")
    feedback_text: str | None = Field(None, description="Optional detailed feedback")
    user_id: str | None = Field(None, description="Optional user identifier")
    session_id: str | None = Field(None, description="Optional session identifier")
    context: dict[str, Any] | None = Field(None, description="Optional context (deck, format, archetype, etc.)")


class FeedbackResponse(BaseModel):
    """Response to feedback submission."""
    status: str
    feedback_id: str
    message: str


class BatchFeedbackRequest(BaseModel):
    """Batch feedback submission."""
    feedbacks: list[FeedbackRequest] = Field(..., description="List of feedback entries", max_length=100)


class BatchFeedbackResponse(BaseModel):
    """Response to batch feedback submission."""
    status: str
    processed: int
    failed: int
    feedback_ids: list[str]
    errors: list[dict[str, Any]]


def get_feedback_storage_path() -> Path:
    """Get path to feedback storage file."""
    if PATHS:
        feedback_dir = PATHS.DATA_DIR / "annotations"
    else:
        feedback_dir = Path("data/annotations")
    
    feedback_dir.mkdir(parents=True, exist_ok=True)
    return feedback_dir / "user_feedback.jsonl"


# Rate limiting storage (in-memory, simple implementation)
_rate_limit_storage: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = 3600  # 1 hour
RATE_LIMIT_MAX_REQUESTS = 100  # Max requests per hour per user/session


def _check_rate_limit(user_id: str | None, session_id: str | None) -> tuple[bool, str | None]:
    """Check if user/session has exceeded rate limit."""
    identifier = user_id or session_id or "anonymous"
    now = time()
    
    # Clean old entries
    _rate_limit_storage[identifier] = [
        t for t in _rate_limit_storage[identifier]
        if now - t < RATE_LIMIT_WINDOW
    ]
    
    # Check limit
    if len(_rate_limit_storage[identifier]) >= RATE_LIMIT_MAX_REQUESTS:
        return False, f"Rate limit exceeded: {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW}s"
    
    # Record this request
    _rate_limit_storage[identifier].append(now)
    return True, None


def _validate_card_name(card_name: str, game: str | None = None) -> tuple[bool, str | None]:
    """
    Validate card name exists in embeddings or card database.
    
    Uses lazy import to avoid circular dependency issues.
    Non-fatal: logs warnings but doesn't block feedback submission.
    """
    if not HAS_CARD_DB:
        # If CardDatabase not available, skip (non-fatal)
        return True, None
    
    try:
        # Lazy import to avoid circular dependency
        # api.py imports feedback.py, so we can't import get_state at module level
        try:
            from ..api.api import get_state
        except (ImportError, AttributeError):
            # App not initialized yet, skip validation
            logger.debug("get_state() not available (app not initialized), skipping validation")
            return True, None
        
        # First check embeddings (faster) - but only if app is initialized
        try:
            state = get_state()
            if state and hasattr(state, 'embeddings') and state.embeddings:
                # Check if card exists in embeddings
                if card_name in state.embeddings:
                    return True, None
                # Try case-insensitive match (but limit search to avoid performance issue)
                card_lower = card_name.lower()
                # Only check first 1000 cards to avoid performance issue
                for emb_card in list(state.embeddings.index_to_key)[:1000]:
                    if emb_card.lower() == card_lower:
                        return True, None
        except (AttributeError, RuntimeError) as e:
            # App not initialized or state not available
            logger.debug(f"State not available for validation: {e}")
        
        # Fallback to CardDatabase if available
        try:
            db = CardDatabase()
            if game:
                if db.is_valid_card(card_name, game):
                    return True, None
            else:
                # Try all games
                for g in ["magic", "pokemon", "yugioh"]:
                    if db.is_valid_card(card_name, g):
                        return True, None
        except Exception as e:
            logger.debug(f"CardDatabase validation error: {e}")
        
        # Card not found, but don't fail (might be new card or validation unavailable)
        logger.warning(f"Card '{card_name}' not found in embeddings/database (validation non-fatal)")
        return True, None  # Non-fatal validation
        
    except Exception as e:
        logger.debug(f"Card validation error (non-fatal): {e}")
        return True, None  # Non-fatal validation


def _check_duplicate_feedback(
    query_card: str,
    suggested_card: str,
    user_id: str | None = None,
    session_id: str | None = None,
) -> bool:
    """
    Check if feedback already exists for this pair.
    
    Note: Only checks last 1000 entries for performance.
    For production, use database with indexed queries.
    """
    feedback_path = get_feedback_storage_path()
    if not feedback_path.exists():
        return False
    
    # Check last 1000 lines for duplicates (avoid reading entire file)
    # For small files, could check all entries, but 1000 is reasonable limit
    try:
        with open(feedback_path, "r", encoding="utf-8") as f:
            # Read last 1000 lines efficiently
            # For very large files, this could be optimized with tail command
            lines = f.readlines()
            # Check last 1000 lines (or all if file is smaller)
            start_idx = max(0, len(lines) - 1000)
            for line in lines[start_idx:]:
                if line.strip():
                    try:
                        existing = json.loads(line)
                        if (existing.get("query_card") == query_card and
                            existing.get("suggested_card") == suggested_card):
                            # If user_id provided, check for same user
                            if user_id and existing.get("user_id") == user_id:
                                return True
                            # If session_id provided, check for same session
                            if session_id and existing.get("session_id") == session_id:
                                return True
                            # If no user/session tracking, allow duplicates
                            # (different users can rate same pair)
                    except (json.JSONDecodeError, ValueError) as e:
                        # Skip malformed entries
                        logger.debug(f"Skipping malformed feedback entry: {e}")
                        continue
                    except Exception as e:
                        logger.debug(f"Error checking duplicate feedback: {e}")
                        continue
    except (OSError, IOError) as e:
        logger.warning(f"Error reading feedback file for duplicate check: {e}")
        # Don't block on read errors - allow submission
        return False
    except Exception as e:
        logger.warning(f"Unexpected error checking duplicates: {e}")
        return False
    
    return False


def store_feedback(feedback: dict[str, Any]) -> str:
    """
    Store feedback in JSONL file.
    
    Note: File I/O is not thread-safe. For production with multiple workers,
    consider using a database or message queue.
    """
    feedback_path = get_feedback_storage_path()
    
    # Add metadata
    feedback["timestamp"] = datetime.now().isoformat()
    # Use MD5 hash for more reliable ID generation (Python hash() can collide)
    import hashlib
    id_string = f"{feedback.get('query_card', '')}_{feedback.get('suggested_card', '')}_{feedback['timestamp']}"
    feedback["feedback_id"] = hashlib.md5(id_string.encode()).hexdigest()
    
    # Append to JSONL file with error handling
    try:
        with open(feedback_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(feedback, ensure_ascii=False) + "\n")
        logger.info(f"Stored feedback: {feedback['feedback_id']} ({feedback.get('task_type', 'unknown')})")
    except (OSError, IOError) as e:
        # File I/O error (disk full, permissions, etc.)
        logger.error(f"Failed to store feedback (I/O error): {e}")
        raise HTTPException(status_code=500, detail="Failed to store feedback: I/O error")
    except Exception as e:
        # Unexpected error
        logger.error(f"Failed to store feedback (unexpected error): {e}")
        raise HTTPException(status_code=500, detail="Failed to store feedback")
    
    return feedback["feedback_id"]


@router.post("", response_model=FeedbackResponse)
def submit_feedback(req: FeedbackRequest) -> FeedbackResponse:
    """
    Collect user feedback on model suggestions.
    
    Stores feedback for:
    - Training data generation (conversion to substitution pairs)
    - Model evaluation (user satisfaction metrics)
    - Quality tracking (IAA with other annotators)
    
    TODO: Add validation, duplicate detection, rate limiting
    """
    try:
        # Validate and normalize card names
        query_card = req.query_card.strip()
        suggested_card = req.suggested_card.strip()
        
        # Basic validation
        if not query_card or not suggested_card:
            raise HTTPException(status_code=400, detail="query_card and suggested_card are required")
        
        # Check for extremely long names (potential abuse)
        if len(query_card) > 500 or len(suggested_card) > 500:
            raise HTTPException(status_code=400, detail="Card names too long (max 500 characters)")
        
        # Check for control characters (security) - allow tab, newline, carriage return
        invalid_chars = [c for c in query_card + suggested_card if ord(c) < 32 and c not in '\t\n\r']
        if invalid_chars:
            raise HTTPException(status_code=400, detail="Card names contain invalid control characters")
        
        # Rate limiting
        allowed, error_msg = _check_rate_limit(req.user_id, req.session_id)
        if not allowed:
            raise HTTPException(status_code=429, detail=error_msg)
        
        # Validate card names (non-fatal, but logs warnings)
        game = req.context.get("game") if req.context else None
        _validate_card_name(query_card, game)
        _validate_card_name(suggested_card, game)
        
        # Check for duplicate feedback (if user_id or session_id provided)
        if req.user_id or req.session_id:
            is_duplicate = _check_duplicate_feedback(
                query_card,
                suggested_card,
                req.user_id,
                req.session_id,
            )
            if is_duplicate:
                logger.warning(f"Duplicate feedback detected: {query_card} → {suggested_card}")
                # Allow but log - user might want to update their rating
        
        # Prepare feedback data with normalized names
        feedback_data = req.model_dump(exclude_none=True)
        feedback_data["query_card"] = query_card
        feedback_data["suggested_card"] = suggested_card
        feedback_id = store_feedback(feedback_data)
        
        return FeedbackResponse(
            status="success",
            feedback_id=feedback_id,
            message="Feedback recorded successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing feedback: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to store feedback: {e}")


@router.post("/batch", response_model=BatchFeedbackResponse)
def submit_batch_feedback(req: BatchFeedbackRequest) -> BatchFeedbackResponse:
    """
    Submit multiple feedback entries in a single request.
    
    Useful for UI that collects multiple ratings at once.
    Max 100 entries per batch.
    
    Note: Rate limiting is checked per entry, not per batch.
    If user exceeds rate limit mid-batch, remaining entries will fail.
    """
    # Validate batch size (Pydantic max_items should catch this, but double-check)
    if len(req.feedbacks) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 feedback entries per batch")
    
    if len(req.feedbacks) == 0:
        raise HTTPException(status_code=400, detail="Batch must contain at least one feedback entry")
    
    # Check rate limit for entire batch upfront (more user-friendly)
    # This prevents partial failures due to rate limiting
    user_id = req.feedbacks[0].user_id if req.feedbacks else None
    session_id = req.feedbacks[0].session_id if req.feedbacks else None
    
    # Estimate if batch would exceed rate limit
    # Allow batch if user has at least (batch_size + 10) requests remaining
    allowed, error_msg = _check_rate_limit(user_id, session_id)
    if not allowed:
        # Check if we can still process some entries
        # Get current count
        identifier = user_id or session_id or "anonymous"
        now = time()
        current_count = len([
            t for t in _rate_limit_storage.get(identifier, [])
            if now - t < RATE_LIMIT_WINDOW
        ])
        remaining = RATE_LIMIT_MAX_REQUESTS - current_count
        
        if remaining < len(req.feedbacks):
            # Batch too large for remaining quota
            raise HTTPException(
                status_code=429,
                detail=f"Batch size ({len(req.feedbacks)}) exceeds remaining rate limit ({remaining} requests remaining)"
            )
    
    processed = 0
    failed = 0
    feedback_ids = []
    errors = []
    
    for i, feedback_req in enumerate(req.feedbacks):
        try:
            # Use same validation as single feedback
            response = submit_feedback(feedback_req)
            feedback_ids.append(response.feedback_id)
            processed += 1
        except HTTPException as e:
            errors.append({
                "index": i,
                "query_card": feedback_req.query_card,
                "suggested_card": feedback_req.suggested_card,
                "error": e.detail,
                "status_code": e.status_code,
            })
            failed += 1
        except Exception as e:
            errors.append({
                "index": i,
                "query_card": feedback_req.query_card,
                "suggested_card": feedback_req.suggested_card,
                "error": str(e),
                "status_code": 500,
            })
            failed += 1
    
    return BatchFeedbackResponse(
        status="partial" if failed > 0 else "success",
        processed=processed,
        failed=failed,
        feedback_ids=feedback_ids,
        errors=errors,
    )


@router.get("/stats")
def get_feedback_stats() -> dict[str, Any]:
    """
    Get statistics on collected feedback.
    
    Reads entire file - for large files, consider pagination or sampling.
    """
    feedback_path = get_feedback_storage_path()
    
    if not feedback_path.exists():
        return {
            "total_feedback": 0,
            "by_task_type": {},
            "by_rating": {},
            "substitution_rate": 0.0,
        }
    
    total = 0
    by_task_type: dict[str, int] = {}
    by_rating: dict[int, int] = {}
    substitutions = 0
    
    try:
        # Use line-by-line reading to avoid loading entire file
        with open(feedback_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        feedback = json.loads(line)
                        total += 1
                        
                        task_type = feedback.get("task_type", "unknown")
                        by_task_type[task_type] = by_task_type.get(task_type, 0) + 1
                        
                        rating = feedback.get("rating", 0)
                        by_rating[rating] = by_rating.get(rating, 0) + 1
                        
                        if feedback.get("is_substitute") is True:
                            substitutions += 1
                    except (json.JSONDecodeError, ValueError) as e:
                        # Skip malformed entries
                        logger.debug(f"Skipping malformed feedback entry in stats: {e}")
                        continue
                    except Exception as e:
                        logger.debug(f"Error processing feedback entry in stats: {e}")
                        continue
    except (OSError, IOError) as e:
        logger.error(f"Error reading feedback file for stats: {e}")
        return {
            "total_feedback": 0,
            "by_task_type": {},
            "by_rating": {},
            "substitution_rate": 0.0,
            "error": "Failed to read feedback file",
        }
    except Exception as e:
        logger.error(f"Unexpected error reading feedback stats: {e}")
        return {
            "total_feedback": 0,
            "by_task_type": {},
            "by_rating": {},
            "substitution_rate": 0.0,
            "error": "Unexpected error",
        }
    
    return {
        "total_feedback": total,
        "by_task_type": by_task_type,
        "by_rating": by_rating,
        "substitution_rate": substitutions / total if total > 0 else 0.0,
    }


@router.get("/queries")
def get_query_analytics(days: int = 7) -> dict[str, Any]:
    """Get query analytics for the last N days."""
    try:
        from .query_history import get_query_stats
        return get_query_stats(days=days)
    except ImportError:
        return {
            "error": "Query history not available",
            "total_queries": 0,
            "by_endpoint": {},
            "top_queries": [],
            "unique_users": 0,
        }

