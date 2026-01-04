import os

import pytest

try:
    from fastapi.testclient import TestClient
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    TestClient = None

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")

try:
    # Import through repository shim for consistency
    from ..api.api import app
except ImportError:
    app = None


# env cleanup handled by global fixture in conftest.py


@pytest.fixture
def api_client():
    """Create a test client for the API."""
    if not HAS_FASTAPI or app is None:
        pytest.skip("FastAPI or app not available")
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_live_endpoint(api_client):
    client = api_client
    resp = client.get("/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "live"


def test_ready_without_embeddings_returns_503(api_client):
    client = api_client
    resp = client.get("/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"].startswith("not ready")


