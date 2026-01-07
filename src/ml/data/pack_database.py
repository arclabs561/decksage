#!/usr/bin/env python3
"""
Pack Database: Scrape and store pack/booster/starter deck information.

Packs provide valuable co-occurrence signals for GNN training:
- Cards in the same pack naturally co-occur
- Pack release dates provide temporal information
- Pack types (starter vs booster) have different patterns
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class PackDatabase:
    """Database for storing pack/booster/starter deck information."""
    
    def __init__(self, db_path: Path | None = None):
        """Initialize pack database."""
        if db_path is None:
            from ..utils.paths import PATHS
            db_path = PATHS.packs_db
        
        self.db_path = Path(db_path)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Packs table: stores pack metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS packs (
                pack_id TEXT PRIMARY KEY,
                game TEXT NOT NULL,
                pack_name TEXT NOT NULL,
                pack_code TEXT,
                pack_type TEXT,  -- 'booster', 'starter', 'standard', 'premium', etc.
                release_date TEXT,
                card_count INTEGER,
                metadata TEXT,  -- JSON string for additional data
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Pack cards table: many-to-many relationship
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pack_cards (
                pack_id TEXT NOT NULL,
                card_name TEXT NOT NULL,
                rarity TEXT,
                card_number TEXT,
                is_foil INTEGER DEFAULT 0,
                metadata TEXT,  -- JSON string for additional data
                PRIMARY KEY (pack_id, card_name),
                FOREIGN KEY (pack_id) REFERENCES packs(pack_id)
            )
        """)
        
        # Indexes for fast lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_packs_game ON packs(game)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_packs_type ON packs(pack_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pack_cards_card ON pack_cards(card_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pack_cards_pack ON pack_cards(pack_id)
        """)
        
        conn.commit()
        conn.close()
    
    def add_pack(
        self,
        pack_id: str,
        game: str,
        pack_name: str,
        pack_code: str | None = None,
        pack_type: str | None = None,
        release_date: str | None = None,
        card_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add or update a pack."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO packs
            (pack_id, game, pack_name, pack_code, pack_type, release_date, 
             card_count, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 
                    COALESCE((SELECT created_at FROM packs WHERE pack_id = ?), ?),
                    ?)
        """, (
            pack_id, game, pack_name, pack_code, pack_type, release_date,
            card_count, json.dumps(metadata) if metadata else None,
            pack_id, now, now
        ))
        
        conn.commit()
        conn.close()
    
    def add_pack_card(
        self,
        pack_id: str,
        card_name: str,
        rarity: str | None = None,
        card_number: str | None = None,
        is_foil: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a card to a pack."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO pack_cards
            (pack_id, card_name, rarity, card_number, is_foil, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            pack_id, card_name, rarity, card_number,
            1 if is_foil else 0,
            json.dumps(metadata) if metadata else None
        ))
        
        conn.commit()
        conn.close()
    
    def add_pack_cards_batch(
        self,
        cards: list[dict[str, Any]],
    ) -> int:
        """
        Batch add multiple cards to packs.
        
        Args:
            cards: List of dicts with keys: pack_id, card_name, rarity, card_number, is_foil, metadata
        
        Returns:
            Number of cards added
        """
        if not cards:
            return 0
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        batch_data = []
        for card in cards:
            batch_data.append((
                card["pack_id"],
                card["card_name"],
                card.get("rarity"),
                card.get("card_number"),
                1 if card.get("is_foil", False) else 0,
                json.dumps(card.get("metadata")) if card.get("metadata") else None,
            ))
        
        cursor.executemany("""
            INSERT OR REPLACE INTO pack_cards
            (pack_id, card_name, rarity, card_number, is_foil, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, batch_data)
        
        conn.commit()
        conn.close()
        
        return len(cards)
    
    def get_pack_cards(self, pack_id: str) -> list[dict[str, Any]]:
        """Get all cards in a pack."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT card_name, rarity, card_number, is_foil, metadata
            FROM pack_cards
            WHERE pack_id = ?
            ORDER BY card_number, card_name
        """, (pack_id,))
        
        results = []
        for row in cursor.fetchall():
            result = {
                "card_name": row["card_name"],
                "rarity": row["rarity"],
                "card_number": row["card_number"],
                "is_foil": bool(row["is_foil"]),
            }
            if row["metadata"]:
                result["metadata"] = json.loads(row["metadata"])
            results.append(result)
        
        conn.close()
        return results
    
    def get_card_packs(self, card_name: str, game: str | None = None) -> list[dict[str, Any]]:
        """Get all packs containing a card."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if game:
            cursor.execute("""
                SELECT p.pack_id, p.pack_name, p.pack_code, p.pack_type, 
                       p.release_date, pc.rarity, pc.card_number, pc.is_foil
                FROM pack_cards pc
                JOIN packs p ON pc.pack_id = p.pack_id
                WHERE pc.card_name = ? AND p.game = ?
                ORDER BY p.release_date DESC
            """, (card_name, game))
        else:
            cursor.execute("""
                SELECT p.pack_id, p.pack_name, p.pack_code, p.pack_type, 
                       p.release_date, pc.rarity, pc.card_number, pc.is_foil
                FROM pack_cards pc
                JOIN packs p ON pc.pack_id = p.pack_id
                WHERE pc.card_name = ?
                ORDER BY p.release_date DESC
            """, (card_name,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "pack_id": row["pack_id"],
                "pack_name": row["pack_name"],
                "pack_code": row["pack_code"],
                "pack_type": row["pack_type"],
                "release_date": row["release_date"],
                "rarity": row["rarity"],
                "card_number": row["card_number"],
                "is_foil": bool(row["is_foil"]),
            })
        
        conn.close()
        return results
    
    def get_pack_co_occurrences(
        self,
        card1: str,
        card2: str,
        game: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get packs where both cards appear together."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if game:
            cursor.execute("""
                SELECT DISTINCT p.pack_id, p.pack_name, p.pack_code, 
                       p.pack_type, p.release_date
                FROM packs p
                JOIN pack_cards pc1 ON p.pack_id = pc1.pack_id
                JOIN pack_cards pc2 ON p.pack_id = pc2.pack_id
                WHERE pc1.card_name = ? AND pc2.card_name = ? AND p.game = ?
                ORDER BY p.release_date DESC
            """, (card1, card2, game))
        else:
            cursor.execute("""
                SELECT DISTINCT p.pack_id, p.pack_name, p.pack_code, 
                       p.pack_type, p.release_date
                FROM packs p
                JOIN pack_cards pc1 ON p.pack_id = pc1.pack_id
                JOIN pack_cards pc2 ON p.pack_id = pc2.pack_id
                WHERE pc1.card_name = ? AND pc2.card_name = ?
                ORDER BY p.release_date DESC
            """, (card1, card2))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "pack_id": row["pack_id"],
                "pack_name": row["pack_name"],
                "pack_code": row["pack_code"],
                "pack_type": row["pack_type"],
                "release_date": row["release_date"],
            })
        
        conn.close()
        return results
    
    def get_statistics(self) -> dict[str, Any]:
        """Get database statistics."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        stats = {}
        
        # Total packs
        cursor.execute("SELECT COUNT(*) FROM packs")
        stats["total_packs"] = cursor.fetchone()[0]
        
        # Packs by game
        cursor.execute("""
            SELECT game, COUNT(*) as count
            FROM packs
            GROUP BY game
        """)
        stats["packs_by_game"] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Packs by type
        cursor.execute("""
            SELECT pack_type, COUNT(*) as count
            FROM packs
            WHERE pack_type IS NOT NULL
            GROUP BY pack_type
        """)
        stats["packs_by_type"] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Total pack-card relationships
        cursor.execute("SELECT COUNT(*) FROM pack_cards")
        stats["total_pack_cards"] = cursor.fetchone()[0]
        
        # Unique cards in packs
        cursor.execute("SELECT COUNT(DISTINCT card_name) FROM pack_cards")
        stats["unique_cards"] = cursor.fetchone()[0]
        
        conn.close()
        return stats

