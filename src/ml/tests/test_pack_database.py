"""Tests for PackDatabase.

Verifies:
- get_pack_co_occurrences() returns correct pairs
- add_pack / add_pack_card / batch operations work correctly
- get_statistics() returns expected schema
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ..data.pack_database import PackDatabase


@pytest.fixture
def pack_db(tmp_path: Path) -> PackDatabase:
    """Create a PackDatabase backed by a temp SQLite file."""
    return PackDatabase(db_path=tmp_path / "test_packs.db")


@pytest.fixture
def populated_db(pack_db: PackDatabase) -> PackDatabase:
    """PackDatabase with sample packs and cards."""
    # Pack 1: two cards (Bolt + Counterspell)
    pack_db.add_pack(
        pack_id="set1-booster-001",
        game="magic",
        pack_name="Alpha Booster",
        pack_code="LEA",
        pack_type="booster",
        release_date="1993-08-05",
        card_count=15,
    )
    pack_db.add_pack_card("set1-booster-001", "Lightning Bolt", rarity="common")
    pack_db.add_pack_card("set1-booster-001", "Counterspell", rarity="uncommon")
    pack_db.add_pack_card("set1-booster-001", "Black Lotus", rarity="rare")

    # Pack 2: overlaps on Bolt only
    pack_db.add_pack(
        pack_id="set2-booster-001",
        game="magic",
        pack_name="Beta Booster",
        pack_code="LEB",
        pack_type="booster",
        release_date="1993-10-04",
        card_count=15,
    )
    pack_db.add_pack_card("set2-booster-001", "Lightning Bolt", rarity="common")
    pack_db.add_pack_card("set2-booster-001", "Dark Ritual", rarity="common")

    # Pack 3: YuGiOh pack (different game)
    pack_db.add_pack(
        pack_id="ygo-starter-001",
        game="yugioh",
        pack_name="Starter Deck Yugi",
        pack_code="SDY",
        pack_type="starter",
        release_date="2002-03-29",
        card_count=50,
    )
    pack_db.add_pack_card("ygo-starter-001", "Dark Magician", rarity="ultra_rare")
    pack_db.add_pack_card("ygo-starter-001", "Mystical Elf", rarity="common")

    return pack_db


class TestPackDatabaseInit:
    """Test database initialization."""

    def test_creates_db_file(self, tmp_path: Path):
        """Database file should be created on init."""
        db_path = tmp_path / "packs.db"
        PackDatabase(db_path=db_path)
        assert db_path.exists()

    def test_idempotent_init(self, tmp_path: Path):
        """Creating PackDatabase twice on same file should not fail."""
        db_path = tmp_path / "packs.db"
        PackDatabase(db_path=db_path)
        PackDatabase(db_path=db_path)  # should not raise


class TestAddAndRetrieve:
    """Test adding and retrieving packs/cards."""

    def test_add_pack_and_get_cards(self, pack_db: PackDatabase):
        pack_db.add_pack(pack_id="p1", game="magic", pack_name="Test Pack")
        pack_db.add_pack_card("p1", "Lightning Bolt", rarity="common")
        pack_db.add_pack_card("p1", "Counterspell", rarity="uncommon")

        cards = pack_db.get_pack_cards("p1")
        card_names = {c["card_name"] for c in cards}
        assert card_names == {"Lightning Bolt", "Counterspell"}

    def test_get_pack_cards_empty(self, pack_db: PackDatabase):
        """Querying non-existent pack should return empty list."""
        cards = pack_db.get_pack_cards("nonexistent")
        assert cards == []

    def test_add_pack_card_with_foil(self, pack_db: PackDatabase):
        pack_db.add_pack(pack_id="p1", game="magic", pack_name="Test Pack")
        pack_db.add_pack_card("p1", "Black Lotus", is_foil=True)

        cards = pack_db.get_pack_cards("p1")
        assert len(cards) == 1
        assert cards[0]["is_foil"] is True

    def test_add_pack_card_with_metadata(self, pack_db: PackDatabase):
        pack_db.add_pack(pack_id="p1", game="magic", pack_name="Test Pack")
        pack_db.add_pack_card("p1", "Sol Ring", metadata={"collector_number": "232"})

        cards = pack_db.get_pack_cards("p1")
        assert len(cards) == 1
        assert cards[0]["metadata"]["collector_number"] == "232"

    def test_batch_add_cards(self, pack_db: PackDatabase):
        pack_db.add_pack(pack_id="p1", game="magic", pack_name="Test Pack")
        batch = [
            {"pack_id": "p1", "card_name": "Card A"},
            {"pack_id": "p1", "card_name": "Card B", "rarity": "rare"},
            {"pack_id": "p1", "card_name": "Card C", "is_foil": True},
        ]
        count = pack_db.add_pack_cards_batch(batch)
        assert count == 3
        cards = pack_db.get_pack_cards("p1")
        assert len(cards) == 3

    def test_batch_add_empty(self, pack_db: PackDatabase):
        count = pack_db.add_pack_cards_batch([])
        assert count == 0

    def test_upsert_pack(self, pack_db: PackDatabase):
        """Adding same pack_id twice should update, not duplicate."""
        pack_db.add_pack(pack_id="p1", game="magic", pack_name="Original")
        pack_db.add_pack(pack_id="p1", game="magic", pack_name="Updated")
        stats = pack_db.get_statistics()
        assert stats["total_packs"] == 1


class TestGetCardPacks:
    """Test get_card_packs (reverse lookup)."""

    def test_card_in_multiple_packs(self, populated_db: PackDatabase):
        packs = populated_db.get_card_packs("Lightning Bolt")
        assert len(packs) == 2
        pack_codes = {p["pack_code"] for p in packs}
        assert pack_codes == {"LEA", "LEB"}

    def test_card_not_found(self, populated_db: PackDatabase):
        packs = populated_db.get_card_packs("Nonexistent Card")
        assert packs == []

    def test_filter_by_game(self, populated_db: PackDatabase):
        packs = populated_db.get_card_packs("Dark Magician", game="yugioh")
        assert len(packs) == 1
        assert packs[0]["pack_code"] == "SDY"

    def test_filter_by_wrong_game(self, populated_db: PackDatabase):
        packs = populated_db.get_card_packs("Lightning Bolt", game="yugioh")
        assert packs == []


class TestGetPackCoOccurrences:
    """Test get_pack_co_occurrences() returns correct pairs."""

    def test_co_occurring_cards(self, populated_db: PackDatabase):
        """Cards in the same pack should show up as co-occurring."""
        results = populated_db.get_pack_co_occurrences("Lightning Bolt", "Counterspell")
        assert len(results) == 1
        assert results[0]["pack_id"] == "set1-booster-001"

    def test_non_co_occurring_cards(self, populated_db: PackDatabase):
        """Cards that never share a pack should return empty."""
        results = populated_db.get_pack_co_occurrences("Counterspell", "Dark Ritual")
        assert results == []

    def test_co_occurrence_symmetric(self, populated_db: PackDatabase):
        """co_occurrences(A, B) == co_occurrences(B, A)."""
        ab = populated_db.get_pack_co_occurrences("Lightning Bolt", "Black Lotus")
        ba = populated_db.get_pack_co_occurrences("Black Lotus", "Lightning Bolt")
        assert len(ab) == len(ba) == 1
        assert ab[0]["pack_id"] == ba[0]["pack_id"]

    def test_co_occurrence_with_game_filter(self, populated_db: PackDatabase):
        results = populated_db.get_pack_co_occurrences(
            "Lightning Bolt", "Counterspell", game="magic"
        )
        assert len(results) == 1

    def test_co_occurrence_wrong_game_filter(self, populated_db: PackDatabase):
        results = populated_db.get_pack_co_occurrences(
            "Lightning Bolt", "Counterspell", game="yugioh"
        )
        assert results == []

    def test_co_occurrence_result_schema(self, populated_db: PackDatabase):
        """Each co-occurrence result should have the expected keys."""
        results = populated_db.get_pack_co_occurrences("Lightning Bolt", "Counterspell")
        assert len(results) >= 1
        result = results[0]
        expected_keys = {"pack_id", "pack_name", "pack_code", "pack_type", "release_date"}
        assert set(result.keys()) == expected_keys


class TestGetStatistics:
    """Test get_statistics() returns correct schema and values."""

    def test_empty_db_statistics(self, pack_db: PackDatabase):
        stats = pack_db.get_statistics()
        assert stats["total_packs"] == 0
        assert stats["total_pack_cards"] == 0
        assert stats["unique_cards"] == 0
        assert stats["packs_by_game"] == {}
        assert stats["packs_by_type"] == {}

    def test_populated_statistics(self, populated_db: PackDatabase):
        stats = populated_db.get_statistics()
        assert stats["total_packs"] == 3
        assert stats["packs_by_game"]["magic"] == 2
        assert stats["packs_by_game"]["yugioh"] == 1
        assert stats["packs_by_type"]["booster"] == 2
        assert stats["packs_by_type"]["starter"] == 1
        # 3 + 2 + 2 = 7 pack-card relationships
        assert stats["total_pack_cards"] == 7
        # 5 unique cards: Bolt, Counterspell, Black Lotus, Dark Ritual, Dark Magician, Mystical Elf
        assert stats["unique_cards"] == 6

    def test_statistics_schema(self, populated_db: PackDatabase):
        """Statistics dict should have exactly these top-level keys."""
        stats = populated_db.get_statistics()
        expected_keys = {
            "total_packs",
            "packs_by_game",
            "packs_by_type",
            "total_pack_cards",
            "unique_cards",
        }
        assert set(stats.keys()) == expected_keys
