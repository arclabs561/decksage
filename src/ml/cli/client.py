"""
DeckSage API Client for CLI

Supports two modes:
1. Direct mode: Import API code directly (faster, no HTTP overhead)
2. HTTP mode: Use httpx to call API (works with remote API)
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urljoin


try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    httpx = None  # type: ignore[assignment]
    HAS_HTTPX = False


class DeckSageClient:
    """Client for DeckSage API - supports both direct and HTTP modes."""

    def __init__(
        self,
        base_url: str | None = None,
        game: str | None = None,
        direct_mode: bool = False,
        timeout: float = 30.0,
    ):
        """
        Initialize client.

        Args:
            base_url: API base URL (default: http://localhost:8000)
            game: Game name (magic|pokemon|yugioh). In multi-game serving, this is required.
            direct_mode: If True, import API code directly (faster, local only)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or "http://localhost:8000"
        self.game = game
        self.direct_mode = direct_mode
        self.timeout = timeout
        self._api_state = None

        if direct_mode:
            # Try to import API state directly
            try:
                from ..api.api import app, get_state

                self._app = app
                self._get_state = get_state
                self._api_state = get_state(game)
            except Exception:
                # Fall back to HTTP mode if direct import fails
                self.direct_mode = False

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make request (direct or HTTP)."""
        if self.direct_mode and self._api_state:
            return self._request_direct(method, path, body)
        else:
            return self._request_http(method, path, body)

    def _request_direct(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make request using direct API imports (faster, no HTTP)."""
        # Import API functions directly
        from ..api.api import (
            SimilarityRequest,
            UseCaseEnum,
            _health_impl,
            _similar_impl,
        )
        from ..api.api import (
            ready as api_ready,
        )

        if path == "/v1/health":
            game = (body or {}).get("game") if isinstance(body, dict) else None
            health = _health_impl(game=game)
            return {
                "status": health.status,
                "game": health.game,
                "num_cards": health.num_cards,
                "embedding_dim": health.embedding_dim,
            }
        elif path == "/v1/similar" and method == "POST" and body:
            req = SimilarityRequest(**body)
            resp = _similar_impl(req)
            return {
                "query": resp.query,
                "results": [{"card": r.card, "similarity": r.similarity} for r in resp.results],
                "model_info": resp.model_info,
            }
        elif path.startswith("/v1/cards/") and path.endswith("/similar"):
            # Extract card name from path
            card_name = path.split("/v1/cards/")[1].split("/similar")[0]
            card_name = card_name.replace("%20", " ")
            # Parse query params from body or use defaults
            mode = body.get("mode", "substitute") if body else "substitute"
            k = body.get("k", 10) if body else 10
            game = body.get("game") if isinstance(body, dict) else None
            use_case = (
                UseCaseEnum(mode)
                if mode in ["substitute", "synergy", "meta"]
                else UseCaseEnum.substitute
            )
            req = SimilarityRequest(  # type: ignore[call-arg]
                game=game, query=card_name, top_k=k, use_case=use_case
            )
            resp = _similar_impl(req)
            return {
                "query": resp.query,
                "results": [{"card": r.card, "similarity": r.similarity} for r in resp.results],
                "model_info": resp.model_info,
            }
        elif path == "/ready":
            # ready() returns a dict directly
            ready_resp = api_ready()
            return ready_resp if isinstance(ready_resp, dict) else {"status": "ready"}
        elif path == "/live":
            return {"status": "live"}
        else:
            # Fall back to HTTP for unsupported paths
            return self._request_http(method, path, body)

    def _request_http(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make HTTP request."""
        if not HAS_HTTPX:
            raise RuntimeError("httpx not available. Install with: uv pip install httpx")

        url = urljoin(self.base_url, path)
        with httpx.Client(timeout=self.timeout) as client:
            if method == "GET":
                response = client.get(url)
            elif method == "POST":
                response = client.post(url, json=body)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            return response.json()

    def health(self) -> dict[str, Any]:
        """Check API health."""
        game = self.game
        if self.direct_mode:
            body = {"game": game} if game else None
            return self._request("GET", "/v1/health", body)
        q = f"?game={quote(game)}" if game else ""
        return self._request("GET", f"/v1/health{q}")

    def ready(self) -> dict[str, Any]:
        """Check API readiness."""
        return self._request("GET", "/ready")

    def live(self) -> dict[str, Any]:
        """Check API liveness."""
        return self._request("GET", "/live")

    def find_similar(
        self,
        card_name: str,
        k: int = 10,
        mode: str = "substitute",
        use_case: str | None = None,
    ) -> dict[str, Any]:
        """Find similar cards."""
        if use_case is None:
            use_case = mode if mode in ["substitute", "synergy", "meta"] else "substitute"

        game = self.game
        if self.direct_mode:
            # Use direct mode
            body = {"k": k, "mode": mode, "game": game} if game else {"k": k, "mode": mode}
            path = f"/v1/cards/{card_name.replace(' ', '%20')}/similar"
            return self._request("GET", path, body)
        else:
            # Use HTTP POST
            body = {
                "game": game,
                "query": card_name,
                "top_k": k,
                "use_case": use_case,
                "mode": mode if mode in ["embedding", "jaccard", "fusion"] else None,
            }
            return self._request("POST", "/v1/similar", body)

    def search(
        self,
        query: str,
        limit: int = 10,
        text_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> dict[str, Any]:
        """Search cards."""
        game = self.game
        body = {
            "game": game,
            "query": query,
            "limit": limit,
            "text_weight": text_weight,
            "vector_weight": vector_weight,
        }
        return self._request("POST", "/v1/search", body)

    def list_cards(
        self,
        prefix: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List available cards."""
        game = self.game
        params = []
        if game:
            params.append(f"game={quote(game)}")
        if prefix:
            params.append(f"prefix={prefix}")
        if limit:
            params.append(f"limit={limit}")
        if offset:
            params.append(f"offset={offset}")
        query = "?" + "&".join(params) if params else ""
        return self._request("GET", f"/v1/cards{query}")
