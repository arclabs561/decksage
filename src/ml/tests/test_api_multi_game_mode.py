#!/usr/bin/env python3
"""
Multi-game mode invariants.

These tests ensure that when multiple games are configured, request handlers
require an explicit `game` selection (fail-closed).
"""

from __future__ import annotations

import pytest


try:
    import fastapi  # noqa: F401

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")


def test_multi_game_requires_explicit_game(monkeypatch: pytest.MonkeyPatch):
    from ml.api import api as api_mod

    monkeypatch.setattr(api_mod.app.state, "games", ["magic", "pokemon"], raising=False)
    monkeypatch.setattr(api_mod.app.state, "default_game", "magic", raising=False)

    with pytest.raises(Exception) as e:
        api_mod._require_game(None)
    assert getattr(e.value, "status_code", None) == 400
    assert "game is required" in str(getattr(e.value, "detail", ""))

    # Similarity request without game should fail before inspecting embeddings/graph.
    req = api_mod.SimilarityRequest(query="A", top_k=5)  # type: ignore[call-arg]
    with pytest.raises(Exception) as e2:
        api_mod._similar_impl(req)
    assert getattr(e2.value, "status_code", None) == 400

    # Other handlers should also fail closed when game is omitted.
    with pytest.raises(Exception) as e3:
        api_mod.list_cards_v1(game=None, prefix=None, limit=1, offset=0)
    assert getattr(e3.value, "status_code", None) == 400

    with pytest.raises(Exception) as e4:
        api_mod.search_cards_v1(
            api_mod.SearchRequest(  # type: ignore[call-arg]
                query="bolt", limit=1, text_weight=1.0, vector_weight=0.0
            )
        )
    assert getattr(e4.value, "status_code", None) == 400


def test_feedback_requires_game_in_multi_game_mode(monkeypatch: pytest.MonkeyPatch):
    from ml.api import api as api_mod
    from ml.api import feedback as fb

    monkeypatch.setattr(api_mod.app.state, "games", ["magic", "pokemon"], raising=False)
    monkeypatch.setattr(api_mod.app.state, "default_game", "magic", raising=False)

    req = fb.FeedbackRequest(  # type: ignore[call-arg]
        query_card="A",
        suggested_card="B",
        task_type=fb.TaskType.similarity,
        rating=4,
    )
    with pytest.raises(Exception) as e:
        fb.submit_feedback(req)
    assert getattr(e.value, "status_code", None) == 400
    assert "game is required" in str(getattr(e.value, "detail", ""))
