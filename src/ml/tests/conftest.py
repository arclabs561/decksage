"""Pytest configuration and fixtures.

Centralizes environment loading and provides an API state isolation fixture.
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

try:
    # Load .env once for all tests (respects user's preference to use dotenv)
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
except Exception:
    # dotenv is optional for unit tests
    pass


@contextmanager
def _snapshot_api_state():
    """Capture and restore ml.api state to avoid cross-test leakage."""
    st = None
    snapshot = {}
    try:
        try:
            import api as api_mod
        except Exception:
            # API module not needed for all tests; skip snapshotting
            yield None
            return

        st = api_mod.get_state()
        snapshot = {
            "embeddings": getattr(st, "embeddings", None),
            "graph_data": getattr(st, "graph_data", None),
            "model_info": getattr(st, "model_info", None),
            "fusion_default_weights": getattr(st, "fusion_default_weights", None),
            "card_attrs": getattr(st, "card_attrs", None),
        }
        yield st
    finally:
        if st and snapshot:
            try:
                st.embeddings = snapshot.get("embeddings")
                st.graph_data = snapshot.get("graph_data")
                if "model_info" in snapshot:
                    st.model_info = snapshot["model_info"]
                if "fusion_default_weights" in snapshot:
                    st.fusion_default_weights = snapshot["fusion_default_weights"]
                if "card_attrs" in snapshot:
                    st.card_attrs = snapshot["card_attrs"]
            except Exception:
                # If state shape changed, ignore
                pass


@pytest.fixture()
def api_state_isolation(monkeypatch):
    """Isolate ml.api global state and clear env that flips readiness.

    - Clears envs that toggle startup behavior.
    - Restores ml.api state after each test.
    
    NOTE: Not autouse. Explicitly request this fixture in API tests that need isolation.
    Removed autouse=True because it was causing slow collection by importing api module
    for ALL tests, even those that don't use the API.
    """
    # Ensure startup loader does not try to load embeddings/graph from env
    monkeypatch.delenv("EMBEDDINGS_PATH", raising=False)
    monkeypatch.delenv("PAIRS_PATH", raising=False)

    with _snapshot_api_state():
        # Normalize CWD to repository root so top-level scripts resolve
        try:
            # Repo root is three levels up from src/ml/tests (→ decksage)
            repo_root = Path(__file__).resolve().parents[3]
            os.chdir(repo_root)
        except Exception:
            # Fallback to original behavior
            os.chdir(Path(__file__).parent)
        yield


@pytest.fixture()
def api_client():
    """Yield a FastAPI TestClient with isolated ml.api state."""
    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("fastapi not installed")

    # Initialize through the shim to ensure the router is mounted
    from ..api import api

    with _snapshot_api_state():
        # Ensure env-driven startup does not load embeddings/graph
        os.environ.pop("EMBEDDINGS_PATH", None)
        os.environ.pop("PAIRS_PATH", None)
        os.environ.pop("ATTRIBUTES_PATH", None)

        # Explicitly reset state before yielding the client for each test
        state = api.get_state()
        state.embeddings = None
        state.graph_data = None
        state.card_attrs = None
        state.fusion_default_weights = None
        state.model_info = {}

        # Also clear legacy module-level globals so adoption doesn't leak across tests
        try:
            api.embeddings = None
            api.graph_data = None
            api.model_info = {}
        except Exception:
            pass

        yield TestClient(api.app)
