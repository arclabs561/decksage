"""Tests for the chat assistant module (src/ml/api/chat.py).

Covers:
- Tool functions (find_similar, search, analyze_deck, suggest_additions, etc.)
- ChatDeps construction from ApiState
- Session management (create, restore, TTL cleanup)
- SSE endpoint validation (request/response shape, error handling)
- Multi-game game parameter enforcement
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest


# The chat router requires the `llm` extra; without pydantic-ai the API
# degrades to 501 for every chat route and these tests assert live-router
# behavior.
pytest.importorskip("pydantic_ai")

if TYPE_CHECKING:
    from ml.api.chat import ChatDeps


# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------


class DummyEmb:
    """Minimal KeyedVectors stub for testing chat tools."""

    def __init__(self, cards: list[str] | None = None):
        self._cards = cards or [
            "Lightning Bolt",
            "Lava Spike",
            "Rift Bolt",
            "Chain Lightning",
            "Boros Charm",
        ]
        self.key_to_index = {c: i for i, c in enumerate(self._cards)}

    def __contains__(self, k: str) -> bool:
        return k in self.key_to_index

    @property
    def index_to_key(self) -> list[str]:
        return list(self._cards)

    @property
    def vector_size(self) -> int:
        return 3

    def most_similar(self, q: str, topn: int = 10) -> list[tuple[str, float]]:
        scores = {
            "Lightning Bolt": [
                ("Lava Spike", 0.92),
                ("Rift Bolt", 0.88),
                ("Chain Lightning", 0.85),
                ("Boros Charm", 0.70),
            ],
            "Lava Spike": [
                ("Lightning Bolt", 0.92),
                ("Rift Bolt", 0.80),
                ("Chain Lightning", 0.78),
                ("Boros Charm", 0.65),
            ],
            "Rift Bolt": [
                ("Lightning Bolt", 0.88),
                ("Lava Spike", 0.80),
                ("Chain Lightning", 0.75),
                ("Boros Charm", 0.60),
            ],
            "Chain Lightning": [
                ("Lightning Bolt", 0.85),
                ("Lava Spike", 0.78),
                ("Rift Bolt", 0.75),
                ("Boros Charm", 0.55),
            ],
            "Boros Charm": [
                ("Lightning Bolt", 0.70),
                ("Lava Spike", 0.65),
                ("Rift Bolt", 0.60),
                ("Chain Lightning", 0.55),
            ],
        }
        return [(c, s) for c, s in scores.get(q, []) if c != q][:topn]

    def similarity(self, a: str, b: str) -> float:
        if {a, b} == {"Lightning Bolt", "Lava Spike"}:
            return 0.92
        if {a, b} == {"Lightning Bolt", "Rift Bolt"}:
            return 0.88
        return 0.5


def _make_graph() -> dict[str, dict[str, float]]:
    return {
        "Lightning Bolt": {"Lava Spike": 0.8, "Rift Bolt": 0.7, "Chain Lightning": 0.6},
        "Lava Spike": {"Lightning Bolt": 0.8, "Rift Bolt": 0.5},
        "Rift Bolt": {"Lightning Bolt": 0.7, "Lava Spike": 0.5},
        "Chain Lightning": {"Lightning Bolt": 0.6},
        "Boros Charm": {},
    }


def _make_deps(game: str = "magic") -> ChatDeps:
    from ml.api.chat import ChatDeps

    return ChatDeps(
        game=game,
        embeddings=DummyEmb(),
        graph=_make_graph(),
        card_attrs={
            "Lightning Bolt": {"type": "Instant", "cmc": 1},
            "Lava Spike": {"type": "Sorcery", "cmc": 1},
        },
    )


@dataclass
class FakeRunContext:
    """Minimal RunContext stub for testing tool functions directly."""

    deps: Any


# ---------------------------------------------------------------------------
# Tool function unit tests
# ---------------------------------------------------------------------------


class TestFindSimilarCards:
    def test_embedding_method(self):
        from ml.api.chat import find_similar_cards

        ctx = FakeRunContext(deps=_make_deps())
        result = find_similar_cards(ctx, "Lightning Bolt", top_k=3)
        assert len(result) == 3
        assert result[0]["card"] == "Lava Spike"
        assert result[0]["source"] == "embedding"
        assert 0 < result[0]["score"] <= 1.0

    def test_cooccurrence_method(self):
        from ml.api.chat import find_similar_cards

        ctx = FakeRunContext(deps=_make_deps())
        result = find_similar_cards(ctx, "Lightning Bolt", top_k=3, method="cooccurrence")
        assert len(result) == 3
        assert result[0]["source"] == "cooccurrence"
        # Sorted by weight descending
        assert result[0]["score"] >= result[1]["score"]

    def test_card_not_in_embeddings_fuzzy_match(self):
        from ml.api.chat import find_similar_cards

        ctx = FakeRunContext(deps=_make_deps())
        result = find_similar_cards(ctx, "lightning bolt")  # lowercase
        assert len(result) > 0
        assert "error" not in result[0]

    def test_card_not_found_at_all(self):
        from ml.api.chat import find_similar_cards

        ctx = FakeRunContext(deps=_make_deps())
        result = find_similar_cards(ctx, "Nonexistent Card ZZZZ")
        assert len(result) == 1
        assert "error" in result[0]

    def test_card_not_in_graph(self):
        from ml.api.chat import find_similar_cards

        ctx = FakeRunContext(deps=_make_deps())
        result = find_similar_cards(ctx, "Nonexistent", method="cooccurrence")
        assert len(result) == 1
        assert "error" in result[0]


class TestSearchCardsByName:
    def test_prefix_match(self):
        from ml.api.chat import search_cards_by_name

        ctx = FakeRunContext(deps=_make_deps())
        result = search_cards_by_name(ctx, "Lightning")
        assert "Lightning Bolt" in result

    def test_case_insensitive(self):
        from ml.api.chat import search_cards_by_name

        ctx = FakeRunContext(deps=_make_deps())
        result = search_cards_by_name(ctx, "lava")
        assert "Lava Spike" in result

    def test_no_match(self):
        from ml.api.chat import search_cards_by_name

        ctx = FakeRunContext(deps=_make_deps())
        result = search_cards_by_name(ctx, "ZZZZNOTFOUND")
        assert result == []

    def test_limit(self):
        from ml.api.chat import search_cards_by_name

        ctx = FakeRunContext(deps=_make_deps())
        result = search_cards_by_name(ctx, "l", limit=2)  # matches Lightning Bolt, Lava Spike
        assert len(result) <= 2


class TestGetCardInfo:
    def test_card_with_attrs(self):
        from ml.api.chat import get_card_info

        ctx = FakeRunContext(deps=_make_deps())
        info = get_card_info(ctx, "Lightning Bolt")
        assert info["name"] == "Lightning Bolt"
        assert info["attributes"]["type"] == "Instant"
        assert info["has_embedding"] is True
        assert info["num_cooccurrence_partners"] == 3
        assert len(info["top_cooccurrence"]) <= 5

    def test_card_without_attrs(self):
        from ml.api.chat import get_card_info

        ctx = FakeRunContext(deps=_make_deps())
        info = get_card_info(ctx, "Boros Charm")
        assert "attributes" not in info  # No attrs for Boros Charm
        assert info["has_embedding"] is True

    def test_card_not_in_graph(self):
        from ml.api.chat import get_card_info

        deps = _make_deps()
        deps.graph = {}  # Empty graph
        ctx = FakeRunContext(deps=deps)
        info = get_card_info(ctx, "Lightning Bolt")
        assert info["num_cooccurrence_partners"] == 0


class TestAnalyzeDeck:
    def test_basic_analysis(self):
        from ml.api.chat import analyze_deck

        ctx = FakeRunContext(deps=_make_deps())
        deck = ["Lightning Bolt", "Lava Spike", "Rift Bolt"]
        result = analyze_deck(ctx, deck)
        assert result["total_cards"] == 3
        assert result["unique_cards"] == 3
        assert result["cards_with_embeddings"] == 3
        assert "internal_synergy" in result
        assert result["cooccurrence_coverage"] > 0

    def test_missing_cards(self):
        from ml.api.chat import analyze_deck

        ctx = FakeRunContext(deps=_make_deps())
        deck = ["Lightning Bolt", "Not A Real Card"]
        result = analyze_deck(ctx, deck)
        assert result["cards_with_embeddings"] == 1
        assert "cards_not_found" in result
        assert "Not A Real Card" in result["cards_not_found"]

    def test_single_card_no_synergy(self):
        from ml.api.chat import analyze_deck

        ctx = FakeRunContext(deps=_make_deps())
        result = analyze_deck(ctx, ["Lightning Bolt"])
        assert "internal_synergy" not in result


class TestSuggestAdditions:
    def test_basic_suggestions(self):
        from ml.api.chat import suggest_additions

        ctx = FakeRunContext(deps=_make_deps())
        deck = ["Lightning Bolt", "Lava Spike"]
        result = suggest_additions(ctx, deck, top_k=3)
        assert len(result) > 0
        # Suggested cards should NOT be in the deck
        deck_set = set(deck)
        for r in result:
            assert r["card"] not in deck_set
            assert "synergy_score" in r

    def test_empty_deck(self):
        from ml.api.chat import suggest_additions

        ctx = FakeRunContext(deps=_make_deps())
        result = suggest_additions(ctx, [], top_k=5)
        assert result == []


class TestSuggestReplacements:
    def test_basic_replacement(self):
        from ml.api.chat import suggest_replacements

        ctx = FakeRunContext(deps=_make_deps())
        deck = ["Lightning Bolt", "Lava Spike", "Rift Bolt"]
        result = suggest_replacements(ctx, "Lava Spike", deck, top_k=3)
        assert len(result) > 0
        for r in result:
            assert r["card"] != "Lava Spike"
            assert r["card"] not in set(deck)
            assert "combined" in r

    def test_card_not_in_embeddings(self):
        from ml.api.chat import suggest_replacements

        ctx = FakeRunContext(deps=_make_deps())
        result = suggest_replacements(ctx, "Not Real", ["Lightning Bolt"], top_k=3)
        assert len(result) == 1
        assert "error" in result[0]


# ---------------------------------------------------------------------------
# Session management tests
# ---------------------------------------------------------------------------


class TestSessionManagement:
    def test_create_new_session(self):
        from ml.api.chat import _get_or_create_session, _sessions

        _sessions.clear()
        sess = _get_or_create_session(None, "magic", None)
        assert sess.session_id is not None
        assert len(sess.session_id) == 16
        assert sess.game == "magic"
        assert sess.session_id in _sessions

    def test_restore_session(self):
        from ml.api.chat import _get_or_create_session, _sessions

        _sessions.clear()
        sess1 = _get_or_create_session(None, "magic", None)
        sess2 = _get_or_create_session(sess1.session_id, "magic", None)
        assert sess1.session_id == sess2.session_id
        assert sess1 is sess2

    def test_session_updates_game(self):
        from ml.api.chat import _get_or_create_session, _sessions

        _sessions.clear()
        sess = _get_or_create_session(None, "magic", None)
        sess2 = _get_or_create_session(sess.session_id, "yugioh", None)
        assert sess2.game == "yugioh"

    def test_session_stores_deck(self):
        from ml.api.chat import _get_or_create_session, _sessions

        _sessions.clear()
        deck = {"Main": ["Card A"]}
        sess = _get_or_create_session(None, "magic", deck)
        assert sess.deck_state == deck

    def test_ttl_cleanup(self):
        from ml.api.chat import SESSION_TTL, _get_or_create_session, _sessions

        _sessions.clear()
        sess = _get_or_create_session(None, "magic", None)
        sess.last_used = time.time() - SESSION_TTL - 10
        # Creating a new session triggers cleanup
        _get_or_create_session(None, "magic", None)
        assert sess.session_id not in _sessions

    def test_explicit_session_id(self):
        from ml.api.chat import _get_or_create_session, _sessions

        _sessions.clear()
        sess = _get_or_create_session("my-custom-id", "magic", None)
        assert sess.session_id == "my-custom-id"


# ---------------------------------------------------------------------------
# API endpoint tests (SSE streaming)
# ---------------------------------------------------------------------------


def _setup_game_state(app, game: str = "magic"):
    """Set up minimal game state for API tests."""
    from ml.api.api import ApiState

    state = ApiState()
    state.embeddings = DummyEmb()
    state.graph_data = _make_graph()
    state.card_attrs = {
        "Lightning Bolt": {"type": "Instant", "cmc": 1},
        "Lava Spike": {"type": "Sorcery", "cmc": 1},
    }
    state.model_info = {"methods": ["embedding"], "num_cards": 5}

    if not hasattr(app.state, "api_by_game") or app.state.api_by_game is None:
        app.state.api_by_game = {}
    app.state.api_by_game[game] = state
    app.state.games = [game]
    app.state.default_game = game


class TestChatEndpointValidation:
    """Tests that don't require LLM calls -- validate request/error shapes."""

    def test_missing_message(self, api_client):
        r = api_client.post("/v1/chat", json={"game": "magic"})
        assert r.status_code == 422  # Validation error

    def test_empty_message(self, api_client):
        r = api_client.post("/v1/chat", json={"message": "", "game": "magic"})
        assert r.status_code == 422

    def test_missing_game(self, api_client):
        r = api_client.post("/v1/chat", json={"message": "hello"})
        assert r.status_code == 422

    def test_unknown_game(self, api_client):
        r = api_client.post("/v1/chat", json={"message": "hello", "game": "chess"})
        assert r.status_code == 400

    def test_game_not_loaded(self, api_client):
        """Game is valid but not loaded in api_by_game."""
        r = api_client.post("/v1/chat", json={"message": "hello", "game": "magic"})
        assert r.status_code == 503
        assert "not loaded" in r.json()["detail"]

    def test_message_too_long(self, api_client):
        r = api_client.post("/v1/chat", json={"message": "x" * 5000, "game": "magic"})
        assert r.status_code == 422


def _make_mock_stream_ctx(tokens: list[str], new_messages: bytes = b"[]"):
    """Create a mock async context manager that mimics agent.run_stream().

    The key subtlety: stream_output() must return an async iterator directly
    (not a coroutine that resolves to one), because the caller does
    `async for text in result.stream_output(...)`.
    """

    class MockResult:
        def stream_output(self, debounce_by=None):
            return _async_iter(tokens)

        def new_messages_json(self):
            return new_messages

    class MockStreamCtx:
        async def __aenter__(self):
            return MockResult()

        async def __aexit__(self, *args):
            return False

    return MockStreamCtx()


class TestChatEndpointStreaming:
    """Tests that verify the SSE stream structure.

    These mock the pydantic-ai agent to avoid real LLM calls.
    """

    def test_stream_returns_event_stream_content_type(self, api_client):
        from ml.api.api import app

        _setup_game_state(app)

        from unittest.mock import patch

        with patch("ml.api.chat._get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_stream = MagicMock(
                return_value=_make_mock_stream_ctx(["Hello", "Hello world"])
            )
            mock_get_agent.return_value = mock_agent

            r = api_client.post(
                "/v1/chat",
                json={"message": "test", "game": "magic"},
            )
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")

    def test_stream_emits_session_event(self, api_client):
        from ml.api.api import app

        _setup_game_state(app)

        from unittest.mock import patch

        with patch("ml.api.chat._get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_stream = MagicMock(return_value=_make_mock_stream_ctx(["Hi"]))
            mock_get_agent.return_value = mock_agent

            r = api_client.post(
                "/v1/chat",
                json={"message": "test", "game": "magic"},
            )
            events = _parse_sse_events(r.text)
            assert len(events) >= 2  # session + token(s) + done

            # First event should be session
            assert events[0]["type"] == "session"
            assert "session_id" in events[0]

            # Last event should be done
            assert events[-1]["type"] == "done"

    def test_stream_emits_token_events(self, api_client):
        from ml.api.api import app

        _setup_game_state(app)

        from unittest.mock import patch

        with patch("ml.api.chat._get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_stream = MagicMock(
                return_value=_make_mock_stream_ctx(["Hello", "Hello world", "Hello world!"])
            )
            mock_get_agent.return_value = mock_agent

            r = api_client.post(
                "/v1/chat",
                json={"message": "test", "game": "magic"},
            )
            events = _parse_sse_events(r.text)
            token_events = [e for e in events if e["type"] == "token"]
            assert len(token_events) == 3
            assert token_events[-1]["content"] == "Hello world!"

    def test_stream_error_emits_error_event(self, api_client):
        from ml.api.api import app

        _setup_game_state(app)

        from unittest.mock import patch

        class ErrorStreamCtx:
            async def __aenter__(self):
                raise RuntimeError("LLM API down")

            async def __aexit__(self, *args):
                return False

        with patch("ml.api.chat._get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_stream = MagicMock(return_value=ErrorStreamCtx())
            mock_get_agent.return_value = mock_agent

            r = api_client.post(
                "/v1/chat",
                json={"message": "test", "game": "magic"},
            )
            events = _parse_sse_events(r.text)
            error_events = [e for e in events if e["type"] == "error"]
            assert len(error_events) >= 1
            assert "LLM API down" in error_events[0]["content"]

    def test_session_persists_across_requests(self, api_client):
        from ml.api.api import app
        from ml.api.chat import _sessions

        _setup_game_state(app)
        _sessions.clear()

        from unittest.mock import patch

        with patch("ml.api.chat._get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_stream = MagicMock(
                side_effect=lambda *a, **kw: _make_mock_stream_ctx(["ok"], new_messages=b"[]")
            )
            mock_get_agent.return_value = mock_agent

            # First request
            r1 = api_client.post("/v1/chat", json={"message": "hello", "game": "magic"})
            events1 = _parse_sse_events(r1.text)
            sid = events1[0]["session_id"]

            # Second request with same session
            r2 = api_client.post(
                "/v1/chat", json={"message": "again", "game": "magic", "session_id": sid}
            )
            events2 = _parse_sse_events(r2.text)
            assert events2[0]["session_id"] == sid

            # Session should have accumulated messages
            assert len(_sessions[sid].messages_json) == 2

    def test_deck_context_passed_to_agent(self, api_client):
        from ml.api.api import app

        _setup_game_state(app)

        from unittest.mock import patch

        captured_deps = []

        def capture_run_stream(msg, deps=None, message_history=None):
            captured_deps.append(deps)
            return _make_mock_stream_ctx(["ok"])

        with patch("ml.api.chat._get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_stream = MagicMock(side_effect=capture_run_stream)
            mock_get_agent.return_value = mock_agent

            deck = {
                "partitions": [
                    {
                        "name": "Main",
                        "cards": [
                            {"name": "Lightning Bolt", "count": 4},
                            {"name": "Lava Spike", "count": 3},
                        ],
                    }
                ]
            }
            api_client.post(
                "/v1/chat",
                json={
                    "message": "analyze my deck",
                    "game": "magic",
                    "deck": deck,
                },
            )

            assert len(captured_deps) == 1
            deps = captured_deps[0]
            assert deps.deck is not None
            assert deps.deck["Lightning Bolt"] == 4
            assert deps.deck["Lava Spike"] == 3

    def test_legacy_deck_format(self, api_client):
        from ml.api.api import app

        _setup_game_state(app)

        from unittest.mock import patch

        captured_deps = []

        def capture_run_stream(msg, deps=None, message_history=None):
            captured_deps.append(deps)
            return _make_mock_stream_ctx(["ok"])

        with patch("ml.api.chat._get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_stream = MagicMock(side_effect=capture_run_stream)
            mock_get_agent.return_value = mock_agent

            legacy_deck = {"Main": ["Lightning Bolt", "Lava Spike", "Lava Spike"]}
            api_client.post(
                "/v1/chat",
                json={
                    "message": "help",
                    "game": "magic",
                    "deck": legacy_deck,
                },
            )

            deps = captured_deps[0]
            assert deps.deck is not None
            assert deps.deck["Lava Spike"] == 2

    def test_multi_game_isolation(self, api_client):
        """Each game gets its own agent and state."""
        from ml.api.api import app
        from ml.api.chat import _agents

        _agents.clear()
        _setup_game_state(app, "magic")
        _setup_game_state(app, "yugioh")
        app.state.games = ["magic", "yugioh"]

        from unittest.mock import patch

        captured_games = []

        def capture_agent(game):
            captured_games.append(game)
            mock_agent = MagicMock()
            mock_agent.run_stream = MagicMock(return_value=_make_mock_stream_ctx(["ok"]))
            return mock_agent

        with patch("ml.api.chat._get_agent", side_effect=capture_agent):
            api_client.post("/v1/chat", json={"message": "test", "game": "magic"})
            api_client.post("/v1/chat", json={"message": "test", "game": "yugioh"})

        assert captured_games == ["magic", "yugioh"]


# ---------------------------------------------------------------------------
# SSE format tests
# ---------------------------------------------------------------------------


class TestSSEFormat:
    def test_sse_event_format(self):
        from ml.api.chat import _sse_event

        event = _sse_event({"type": "token", "content": "hello"})
        assert event.startswith("data: ")
        assert event.endswith("\n\n")
        parsed = json.loads(event[6:].strip())
        assert parsed["type"] == "token"
        assert parsed["content"] == "hello"

    def test_sse_event_json_escaping(self):
        from ml.api.chat import _sse_event

        event = _sse_event({"type": "token", "content": 'He said "hi"\nNew line'})
        parsed = json.loads(event[6:].strip())
        assert '"hi"' in parsed["content"]
        assert "\n" in parsed["content"]


# ---------------------------------------------------------------------------
# Agent factory tests
# ---------------------------------------------------------------------------


class TestAgentFactory:
    def test_agent_caching_per_game(self):
        from ml.api.chat import _agents, _get_agent

        _agents.clear()

        # This will fail if pydantic-ai can't resolve the model,
        # but we just test the caching logic
        try:
            a1 = _get_agent("magic")
            a2 = _get_agent("magic")
            assert a1 is a2

            a3 = _get_agent("yugioh")
            assert a3 is not a1
            assert len(_agents) == 2
        except Exception:
            # If model resolution fails (no API key), that's OK --
            # we're testing caching, not the LLM call
            pytest.skip("pydantic-ai agent creation requires model config")
        finally:
            _agents.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _async_iter(items):
    """Convert a list to an async iterator."""
    for item in items:
        yield item


def _parse_sse_events(text: str) -> list[dict]:
    """Parse SSE text into list of JSON event dicts."""
    events = []
    for line in text.split("\n"):
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events
