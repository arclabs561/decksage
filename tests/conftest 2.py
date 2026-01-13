"""
Pytest configuration and fixtures.

Shared fixtures for all tests in the tests/ directory.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def test_data_dir():
    """Fixture for test data directory."""
    return Path(__file__).parent.parent / "experiments"


@pytest.fixture
def sample_test_set():
    """Fixture for sample test set."""
    return {
        "queries": {
            "Lightning Bolt": {
                "highly_relevant": ["Shock", "Bolt"],
                "relevant": ["Lightning Strike"],
                "somewhat_relevant": ["Lava Spike"],
                "marginally_relevant": [],
                "irrelevant": ["Counterspell"],
            }
        }
    }


@pytest.fixture
def mock_embeddings():
    """Create a mock embeddings object for testing."""

    class MockEmbeddings:
        def __init__(self):
            self.index_to_key = [
                "Lightning Bolt",
                "Shock",
                "Bolt",
                "Lightning Strike",
                "Lava Spike",
            ]
            self._set = set(self.index_to_key)
            self.vector_size = 128

        def __contains__(self, key: str) -> bool:
            return key in self._set

        def __len__(self) -> int:
            return len(self.index_to_key)

        def most_similar(self, query: str, topn: int = 10) -> list[tuple[str, float]]:
            """Return mock similarity results."""
            # Simple mock: return other cards with decreasing similarity
            results = []
            for i, card in enumerate(self.index_to_key):
                if card != query:
                    # Decreasing similarity score
                    score = 0.9 - (i * 0.1)
                    results.append((card, max(0.0, score)))
            return sorted(results, key=lambda x: x[1], reverse=True)[:topn]

        def similarity(self, card1: str, card2: str) -> float:
            """Return mock similarity between two cards."""
            if card1 == card2:
                return 1.0
            # Simple mock similarity
            if card1 in self._set and card2 in self._set:
                return 0.7
            return 0.0

    return MockEmbeddings()


@pytest.fixture
def temp_graph_db():
    """Create a temporary graph database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Create minimal test database
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE nodes (
            name TEXT PRIMARY KEY,
            game TEXT,
            first_seen TEXT,
            last_seen TEXT,
            total_decks INTEGER,
            attributes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE edges (
            card1 TEXT,
            card2 TEXT,
            weight REAL,
            game TEXT,
            metadata TEXT,
            FOREIGN KEY (card1) REFERENCES nodes(name),
            FOREIGN KEY (card2) REFERENCES nodes(name)
        )
    """)

    # Insert test data
    conn.execute(
        "INSERT INTO nodes VALUES ('Lightning Bolt', 'MTG', '2024-01-01', '2024-01-01', 100, NULL)"
    )
    conn.execute("INSERT INTO nodes VALUES ('Shock', 'MTG', '2024-01-01', '2024-01-01', 80, NULL)")
    conn.execute(
        "INSERT INTO nodes VALUES ('Counterspell', 'MTG', '2024-01-01', '2024-01-01', 90, NULL)"
    )
    conn.execute("INSERT INTO edges VALUES ('Lightning Bolt', 'Shock', 50.0, 'MTG', NULL)")

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def mock_graph_data():
    """Create mock graph data structure."""
    return {
        "adj": {
            "Lightning Bolt": {"Shock", "Bolt"},
            "Shock": {"Lightning Bolt"},
            "Bolt": {"Lightning Bolt"},
        },
        "weights": {
            ("Lightning Bolt", "Shock"): 50.0,
            ("Lightning Bolt", "Bolt"): 45.0,
        },
    }


@pytest.fixture
def mock_card_attrs():
    """Create mock card attributes."""
    return {
        "Lightning Bolt": {
            "cmc": 1,
            "types": {"Instant"},
            "colors": {"Red"},
        },
        "Shock": {
            "cmc": 1,
            "types": {"Instant"},
            "colors": {"Red"},
        },
        "Counterspell": {
            "cmc": 2,
            "types": {"Instant"},
            "colors": {"Blue"},
        },
    }
