"""Tools for agentic quality assurance.

Provides tools that LLM agents can use to investigate and validate
graph data quality and pipeline/lineage integrity.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.paths import PATHS
from ..utils.lineage import check_dependencies, get_lineage_info, DATA_ORDERS
from ..utils.logging_config import get_logger, get_correlation_id, log_exception

logger = get_logger(__name__)


class GraphQATools:
    """Tools for graph quality assurance that agents can use."""
    
    def __init__(self, graph_db: Path | None = None):
        """Initialize QA tools."""
        self.graph_db = graph_db or PATHS.incremental_graph_db
        self._conn: sqlite3.Connection | None = None
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection."""
        if self._conn is None:
            if not self.graph_db.exists():
                raise FileNotFoundError(f"Graph database not found: {self.graph_db}")
            self._conn = sqlite3.connect(str(self.graph_db))
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    def check_node_exists(self, card_name: str) -> dict[str, Any]:
        """Check if a node exists and return its data."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM nodes WHERE name = ?",
            (card_name,),
        ).fetchone()
        
        if row:
            return {
                "exists": True,
                "game": row["game"],
                "total_decks": row["total_decks"],
                "has_attributes": bool(row["attributes"]),
            }
        
        # Provide helpful context when node doesn't exist
        similar = conn.execute(
            "SELECT name, game FROM nodes WHERE name LIKE ? LIMIT 5",
            (f"%{card_name}%",),
        ).fetchall()
        
        result = {"exists": False}
        if similar:
            result["similar_nodes"] = [
                {"name": row["name"], "game": row["game"]} for row in similar
            ]
            result["suggestion"] = f"Node not found. Found {len(similar)} similar nodes (check spelling/game label)"
        
        return result
    
    def check_edge_exists(self, card1: str, card2: str) -> dict[str, Any]:
        """Check if an edge exists and return its data."""
        conn = self._get_connection()
        row = conn.execute(
            """
            SELECT * FROM edges 
            WHERE (card1 = ? AND card2 = ?) OR (card1 = ? AND card2 = ?)
            """,
            (card1, card2, card2, card1),
        ).fetchone()
        
        if row:
            return {
                "exists": True,
                "weight": row["weight"],
                "game": row["game"],
                "has_metadata": bool(row["metadata"]),
            }
        return {"exists": False}
    
    def get_node_neighbors(self, card_name: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get neighbors of a node."""
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT DISTINCT
                CASE WHEN card1 = ? THEN card2 ELSE card1 END as neighbor,
                weight,
                game
            FROM edges
            WHERE card1 = ? OR card2 = ?
            ORDER BY weight DESC
            LIMIT ?
            """,
            (card_name, card_name, card_name, limit),
        ).fetchall()
        
        return [
            {
                "neighbor": row["neighbor"],
                "weight": row["weight"],
                "game": row["game"],
            }
            for row in rows
        ]
    
    def validate_game_label(self, card_name: str, expected_game: str | None = None) -> dict[str, Any]:
        """Validate game label for a card."""
        from ..data.card_database import get_card_database
        
        node_data = self.check_node_exists(card_name)
        if not node_data.get("exists"):
            return {"valid": False, "reason": "Node does not exist"}
        
        actual_game = node_data.get("game")
        
        # Check against card database
        card_db = get_card_database()
        card_db.load()
        detected_game = card_db.get_game(card_name, fuzzy=True)
        
        result = {
            "card_name": card_name,
            "graph_game": actual_game,
            "detected_game": detected_game,
            "valid": True,
        }
        
        if expected_game:
            result["expected_game"] = expected_game
            if actual_game != expected_game:
                result["valid"] = False
                result["reason"] = f"Game mismatch: expected {expected_game}, got {actual_game}"
        
        if detected_game and actual_game:
            # Normalize for comparison
            game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO"}
            detected_normalized = game_map.get(detected_game.lower(), detected_game.upper())
            if detected_normalized != actual_game:
                result["valid"] = False
                result["reason"] = f"Card database suggests {detected_normalized}, graph has {actual_game}"
        
        return result
    
    def sample_high_frequency_edges(self, limit: int = 10) -> list[dict[str, Any]]:
        """Sample high-frequency edges for validation."""
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT card1, card2, weight, game, metadata
            FROM edges
            WHERE weight >= 10
            ORDER BY weight DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        
        return [
            {
                "card1": row["card1"],
                "card2": row["card2"],
                "weight": row["weight"],
                "game": row["game"],
                "has_metadata": bool(row["metadata"]),
            }
            for row in rows
        ]
    
    def check_data_integrity(self) -> dict[str, Any]:
        """Check basic data integrity with detailed diagnostics."""
        corr_id = get_correlation_id() or "unknown"
        logger.debug(f"Checking data integrity [correlation_id={corr_id}]")
        
        import time
        start_time = time.time()
        
        conn = self._get_connection()
        
        # Check for orphaned edges (cards don't exist as nodes)
        logger.debug("Querying orphaned edges...")
        orphaned_count = conn.execute("""
            SELECT COUNT(*) 
            FROM edges e
            WHERE NOT EXISTS (SELECT 1 FROM nodes n WHERE n.name = e.card1)
               OR NOT EXISTS (SELECT 1 FROM nodes n WHERE n.name = e.card2)
        """).fetchone()[0]
        
        query_time = time.time() - start_time
        logger.debug(f"Found {orphaned_count} orphaned edges (query took {query_time:.2f}s)")
        
        # Get sample orphaned edges for diagnosis
        orphaned_samples = conn.execute("""
            SELECT e.card1, e.card2, e.weight, e.game
            FROM edges e
            WHERE NOT EXISTS (SELECT 1 FROM nodes n WHERE n.name = e.card1)
               OR NOT EXISTS (SELECT 1 FROM nodes n WHERE n.name = e.card2)
            LIMIT 10
        """).fetchall()
        
        # Check which card is missing for each orphaned edge
        orphaned_details = []
        for row in orphaned_samples:
            card1_exists = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE name = ?", (row["card1"],)
            ).fetchone()[0] > 0
            card2_exists = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE name = ?", (row["card2"],)
            ).fetchone()[0] > 0
            
            missing = []
            if not card1_exists:
                missing.append(row["card1"])
            if not card2_exists:
                missing.append(row["card2"])
            
            orphaned_details.append({
                "card1": row["card1"],
                "card2": row["card2"],
                "weight": row["weight"],
                "game": row["game"],
                "missing_cards": missing,
            })
        
        # Check for duplicate edges
        duplicates = conn.execute("""
            SELECT COUNT(*) - COUNT(DISTINCT card1 || '|' || card2)
            FROM edges
        """).fetchone()[0]
        
        # Check for invalid weights
        invalid_weights = conn.execute("""
            SELECT COUNT(*) 
            FROM edges 
            WHERE weight < 0 OR weight > 100000
        """).fetchone()[0]
        
        # Get sample invalid weights
        invalid_weight_samples = conn.execute("""
            SELECT card1, card2, weight, game
            FROM edges 
            WHERE weight < 0 OR weight > 100000
            LIMIT 5
        """).fetchall()
        
        total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        integrity_score = 1.0 - (orphaned_count / max(1, total_edges))
        
        # Log with structured format for monitoring
        log_level = logger.warning if (orphaned_count > 0 or duplicates > 0 or invalid_weights > 0) else logger.info
        log_level(
            f"Data integrity check complete [correlation_id={corr_id}, "
            f"orphaned={orphaned_count}/{total_edges}, "
            f"integrity_score={integrity_score:.2%}, "
            f"duplicates={duplicates}, invalid_weights={invalid_weights}]"
        )
        
        if orphaned_count > 0 or duplicates > 0 or invalid_weights > 0:
            logger.warning(
                f"Data integrity issues detected [correlation_id={corr_id}, "
                f"orphaned={orphaned_count}, duplicates={duplicates}, "
                f"invalid_weights={invalid_weights}]"
            )
        
        return {
            "orphaned_edges": orphaned_count,
            "orphaned_percentage": round((orphaned_count / max(1, total_edges)) * 100, 2),
            "orphaned_samples": orphaned_details,
            "integrity_score": integrity_score,
            "total_edges": total_edges,
            "duplicate_edges": duplicates,
            "invalid_weights": invalid_weights,
            "invalid_weight_samples": [
                {
                    "card1": row["card1"],
                    "card2": row["card2"],
                    "weight": row["weight"],
                    "game": row["game"],
                }
                for row in invalid_weight_samples
            ],
            "total_edges": total_edges,
            "integrity_score": 1.0 - min(1.0, (orphaned_count + duplicates + invalid_weights) / max(1, total_edges)),
            "diagnostics": {
                "most_common_missing_card": self._find_most_common_missing_card(orphaned_details) if orphaned_details else None,
            },
        }
    
    def _find_most_common_missing_card(self, orphaned_details: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Find the most common missing card in orphaned edges."""
        from collections import Counter
        missing_cards = []
        for detail in orphaned_details:
            missing_cards.extend(detail.get("missing_cards", []))
        
        if not missing_cards:
            return None
        
        counter = Counter(missing_cards)
        most_common = counter.most_common(1)[0]
        
        return {
            "card": most_common[0],
            "occurrences": most_common[1],
            "percentage_of_orphaned": round((most_common[1] / len(orphaned_details)) * 100, 1),
        }
    
    def investigate_unknown_nodes(self, limit: int = 20) -> list[dict[str, Any]]:
        """Investigate unknown nodes."""
        conn = self._get_connection()
        rows = conn.execute("""
            SELECT name, total_decks, attributes
            FROM nodes
            WHERE game IS NULL OR game = 'Unknown'
            ORDER BY total_decks DESC
            LIMIT ?
        """, (limit,)).fetchall()
        
        from ..data.card_database import get_card_database
        card_db = get_card_database()
        card_db.load()
        
        results = []
        for row in rows:
            detected_game = card_db.get_game(row["name"], fuzzy=True)
            results.append({
                "name": row["name"],
                "total_decks": row["total_decks"],
                "detected_game": detected_game,
                "has_attributes": bool(row["attributes"]),
            })
        
        return results
    
    def check_pipeline_dependencies(self, order: int) -> dict[str, Any]:
        """Check if pipeline dependencies for an order are satisfied."""
        all_satisfied, missing = check_dependencies(order)
        order_info = get_lineage_info(order)
        
        return {
            "order": order,
            "order_name": order_info.get("name", "Unknown"),
            "all_satisfied": all_satisfied,
            "missing_dependencies": missing,
            "depends_on": order_info.get("depends_on", []),
        }
    
    def validate_pipeline_order(self, order: int) -> dict[str, Any]:
        """Validate a specific pipeline order and its dependencies."""
        order_info = get_lineage_info(order)
        if not order_info:
            return {
                "valid": False,
                "error": f"Unknown order: {order}",
            }
        
        all_satisfied, missing = check_dependencies(order)
        
        # Check if locations exist
        locations = order_info.get("locations", [])
        existing_locations = []
        missing_locations = []
        
        for loc in locations:
            # Handle wildcards and S3 paths
            if loc.startswith("s3://"):
                # S3 paths - assume they exist (would need boto3 to check)
                existing_locations.append(loc)
            else:
                # Local paths - check existence
                check_path = Path(loc.replace("*", ""))
                if check_path.exists() or check_path.is_dir():
                    existing_locations.append(loc)
                else:
                    missing_locations.append(loc)
        
        return {
            "order": order,
            "order_name": order_info.get("name", "Unknown"),
            "immutable": order_info.get("immutable", False),
            "dependencies_satisfied": all_satisfied,
            "missing_dependencies": missing,
            "locations": locations,
            "existing_locations": existing_locations,
            "missing_locations": missing_locations,
            "valid": all_satisfied and len(existing_locations) > 0,
        }
    
    def get_pipeline_summary(self) -> dict[str, Any]:
        """Get summary of entire pipeline state."""
        summary = {
            "orders": {},
            "total_orders": len(DATA_ORDERS),
            "orders_with_data": 0,
            "orders_with_issues": 0,
        }
        
        for order in sorted(DATA_ORDERS.keys()):
            validation = self.validate_pipeline_order(order)
            summary["orders"][order] = validation
            
            if validation.get("valid"):
                summary["orders_with_data"] += 1
            else:
                summary["orders_with_issues"] += 1
        
        return summary
    
    def check_graph_statistics(self) -> dict[str, Any]:
        """Get comprehensive graph statistics."""
        conn = self._get_connection()
        
        # Node statistics
        node_stats = conn.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN game IS NULL OR game = 'Unknown' THEN 1 END) as unknown,
                COUNT(CASE WHEN game = 'MTG' THEN 1 END) as mtg,
                COUNT(CASE WHEN game = 'YGO' THEN 1 END) as ygo,
                COUNT(CASE WHEN game = 'PKM' THEN 1 END) as pkm,
                AVG(total_decks) as avg_decks,
                MAX(total_decks) as max_decks
            FROM nodes
        """).fetchone()
        
        # Edge statistics
        edge_stats = conn.execute("""
            SELECT 
                COUNT(*) as total,
                AVG(weight) as avg_weight,
                MIN(weight) as min_weight,
                MAX(weight) as max_weight,
                COUNT(CASE WHEN weight > 100000 THEN 1 END) as suspicious_weights
            FROM edges
        """).fetchone()
        
        # Game distribution
        game_dist = conn.execute("""
            SELECT game, COUNT(*) as count
            FROM nodes
            GROUP BY game
            ORDER BY count DESC
        """).fetchall()
        
        return {
            "nodes": {
                "total": node_stats[0],
                "unknown": node_stats[1],
                "by_game": {
                    "MTG": node_stats[2],
                    "YGO": node_stats[3],
                    "PKM": node_stats[4],
                },
                "avg_decks_per_node": node_stats[5],
                "max_decks_per_node": node_stats[6],
            },
            "edges": {
                "total": edge_stats[0],
                "avg_weight": edge_stats[1],
                "min_weight": edge_stats[2],
                "max_weight": edge_stats[3],
                "suspicious_weights": edge_stats[4],
            },
            "game_distribution": {game: count for game, count in game_dist},
        }
    
    def check_file_timestamp(self, path: str | Path) -> dict[str, Any]:
        """Check file modification timestamp and age."""
        path_obj = Path(path)
        if not path_obj.exists():
            return {"exists": False, "path": str(path_obj)}
        
        stat = path_obj.stat()
        mtime = stat.st_mtime
        age_days = (time.time() - mtime) / 86400
        
        return {
            "exists": True,
            "path": str(path_obj),
            "modified_time": datetime.fromtimestamp(mtime).isoformat(),
            "age_days": round(age_days, 2),
            "age_hours": round(age_days * 24, 1),
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
        }
    
    def check_data_freshness(self, order: int) -> dict[str, Any]:
        """Check if data for an order is fresher than dependencies."""
        corr_id = get_correlation_id() or "unknown"
        logger.debug(f"Checking data freshness for order {order} [correlation_id={corr_id}]")
        
        order_info = get_lineage_info(order)
        if not order_info:
            logger.warning(f"Unknown order: {order}")
            return {"error": f"Unknown order: {order}"}
        
        deps = order_info.get("depends_on", [])
        if not deps:
            return {"order": order, "has_dependencies": False, "is_fresh": True}
        
        # Get timestamps for order locations
        order_timestamps = {}
        for loc in order_info.get("locations", []):
            if loc.startswith("s3://"):
                continue  # Skip S3 for now
            # Handle wildcards - check directory or first matching file
            check_path = Path(loc.replace("*", ""))
            if check_path.exists():
                if check_path.is_dir():
                    # Get newest file in directory
                    files = list(check_path.glob("*"))
                    if files:
                        newest = max(files, key=lambda p: p.stat().st_mtime)
                        order_timestamps[loc] = newest.stat().st_mtime
                else:
                    order_timestamps[loc] = check_path.stat().st_mtime
        
        # Get timestamps for dependencies
        dep_timestamps = {}
        for dep_order in deps:
            dep_info = get_lineage_info(dep_order)
            for loc in dep_info.get("locations", []):
                if loc.startswith("s3://"):
                    continue
                check_path = Path(loc.replace("*", ""))
                if check_path.exists():
                    if check_path.is_dir():
                        files = list(check_path.glob("*"))
                        if files:
                            newest = max(files, key=lambda p: p.stat().st_mtime)
                            dep_timestamps[f"Order {dep_order} ({dep_info.get('name', 'Unknown')})"] = newest.stat().st_mtime
                    else:
                        dep_timestamps[f"Order {dep_order} ({dep_info.get('name', 'Unknown')})"] = check_path.stat().st_mtime
        
        # Compare: order should be newer than dependencies
        issues = []
        for order_loc, order_time in order_timestamps.items():
            for dep_name, dep_time in dep_timestamps.items():
                if order_time < dep_time:
                    age_diff = (dep_time - order_time) / 86400
                    logger.debug(
                        f"Order {order} stale: {order_loc} is {age_diff:.1f} days older than {dep_name}"
                    )
                    issues.append({
                        "order_location": order_loc,
                        "dependency": dep_name,
                        "order_age_days": round((time.time() - order_time) / 86400, 2),
                        "dep_age_days": round((time.time() - dep_time) / 86400, 2),
                        "stale_by_days": round(age_diff, 2),
                        "order_modified": datetime.fromtimestamp(order_time).isoformat(),
                        "dep_modified": datetime.fromtimestamp(dep_time).isoformat(),
                    })
        
        is_fresh = len(issues) == 0
        
        if not is_fresh:
            logger.warning(
                f"Order {order} ({order_info.get('name', 'Unknown')}) is stale "
                f"[correlation_id={corr_id}, stale_issues={len(issues)}]"
            )
        else:
            logger.debug(f"Order {order} is fresh [correlation_id={corr_id}]")
        
        return {
            "order": order,
            "order_name": order_info.get("name", "Unknown"),
            "is_fresh": is_fresh,
            "stale_issues": issues,
            "order_timestamps": {
                loc: datetime.fromtimestamp(ts).isoformat()
                for loc, ts in order_timestamps.items()
            },
            "dependency_timestamps": {
                dep: datetime.fromtimestamp(ts).isoformat()
                for dep, ts in dep_timestamps.items()
            },
        }
    
    def compare_file_timestamps(self, path1: str | Path, path2: str | Path) -> dict[str, Any]:
        """Compare timestamps of two files."""
        p1 = Path(path1)
        p2 = Path(path2)
        
        result = {
            "path1": str(p1),
            "path2": str(p2),
            "path1_exists": p1.exists(),
            "path2_exists": p2.exists(),
        }
        
        if not p1.exists() or not p2.exists():
            return result
        
        t1 = p1.stat().st_mtime
        t2 = p2.stat().st_mtime
        
        result.update({
            "path1_modified": datetime.fromtimestamp(t1).isoformat(),
            "path2_modified": datetime.fromtimestamp(t2).isoformat(),
            "path1_newer": t1 > t2,
            "path2_newer": t2 > t1,
            "age_difference_days": round(abs(t1 - t2) / 86400, 2),
        })
        
        return result
    
    def validate_nodes_against_decks(self, game: str | None = None) -> dict[str, Any]:
        """Check if graph nodes exist in deck data."""
        conn = self._get_connection()
        
        # Get graph nodes
        if game:
            graph_nodes = set(
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM nodes WHERE game = ?", (game,)
                ).fetchall()
            )
        else:
            graph_nodes = set(
                row["name"]
                for row in conn.execute("SELECT name FROM nodes").fetchall()
            )
        
        # Check deck files
        deck_files = list(PATHS.processed.glob("decks_*.jsonl"))
        if not deck_files:
            return {
                "valid": False,
                "error": "No deck files found",
                "graph_nodes_count": len(graph_nodes),
            }
        
        # Sample deck files to check coverage
        deck_cards = set()
        checked_files = 0
        max_files_to_check = 5  # Sample for performance
        
        for deck_file in deck_files[:max_files_to_check]:
            if game and game.lower() not in deck_file.name.lower():
                continue
            try:
                with open(deck_file) as f:
                    for line in f:
                        if not line.strip():
                            continue
                        deck = json.loads(line)
                        # Extract card names from deck
                        if "cards" in deck:
                            deck_cards.update(deck["cards"].keys())
                        elif "mainboard" in deck:
                            deck_cards.update(deck["mainboard"].keys())
                checked_files += 1
            except Exception:
                continue
        
        # Find nodes in graph but not in decks
        missing_in_decks = graph_nodes - deck_cards
        # Find cards in decks but not in graph
        missing_in_graph = deck_cards - graph_nodes
        
        return {
            "valid": len(missing_in_decks) == 0 and len(missing_in_graph) == 0,
            "graph_nodes_count": len(graph_nodes),
            "deck_cards_sampled": len(deck_cards),
            "deck_files_checked": checked_files,
            "nodes_missing_in_decks": len(missing_in_decks),
            "cards_missing_in_graph": len(missing_in_graph),
            "sample_missing_nodes": list(missing_in_decks)[:10],
            "sample_missing_cards": list(missing_in_graph)[:10],
            "coverage_pct": round((len(graph_nodes & deck_cards) / max(1, len(deck_cards))) * 100, 1) if deck_cards else 0,
        }
    
    def query_nodes_by_game(self, game: str, limit: int = 100) -> list[dict[str, Any]]:
        """Query nodes by game with optional filters."""
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT name, game, total_decks, attributes
            FROM nodes
            WHERE game = ?
            ORDER BY total_decks DESC
            LIMIT ?
            """,
            (game, limit),
        ).fetchall()
        
        return [
            {
                "name": row["name"],
                "game": row["game"],
                "total_decks": row["total_decks"],
                "has_attributes": bool(row["attributes"]),
            }
            for row in rows
        ]
    
    def query_edges_by_weight(
        self, min_weight: float = 0, max_weight: float | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Query edges by weight range."""
        conn = self._get_connection()
        
        if max_weight is None:
            rows = conn.execute(
                """
                SELECT card1, card2, weight, game
                FROM edges
                WHERE weight >= ?
                ORDER BY weight DESC
                LIMIT ?
                """,
                (min_weight, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT card1, card2, weight, game
                FROM edges
                WHERE weight >= ? AND weight <= ?
                ORDER BY weight DESC
                LIMIT ?
                """,
                (min_weight, max_weight, limit),
            ).fetchall()
        
        return [
            {
                "card1": row["card1"],
                "card2": row["card2"],
                "weight": row["weight"],
                "game": row["game"],
            }
            for row in rows
        ]
    
    def find_isolated_nodes(self, limit: int = 20) -> list[dict[str, Any]]:
        """Find nodes with no edges (isolated)."""
        conn = self._get_connection()
        rows = conn.execute("""
            SELECT n.name, n.game, n.total_decks
            FROM nodes n
            WHERE NOT EXISTS (
                SELECT 1 FROM edges e 
                WHERE e.card1 = n.name OR e.card2 = n.name
            )
            ORDER BY n.total_decks DESC
            LIMIT ?
        """, (limit,)).fetchall()
        
        return [
            {
                "name": row["name"],
                "game": row["game"],
                "total_decks": row["total_decks"],
            }
            for row in rows
        ]
    
    def check_annotation_format(self, file_path: Path) -> dict[str, Any]:
        """Validate annotation file format."""
        if not file_path.exists():
            return {"exists": False, "path": str(file_path)}
        
        issues = []
        valid_count = 0
        total_count = 0
        
        try:
            if file_path.suffix == ".jsonl":
                required_fields = ["card1", "card2", "similarity_score"]
                with open(file_path) as f:
                    for line_num, line in enumerate(f, 1):
                        if not line.strip():
                            continue
                        total_count += 1
                        try:
                            ann = json.loads(line)
                            if all(field in ann for field in required_fields):
                                valid_count += 1
                            else:
                                missing = [f for f in required_fields if f not in ann]
                                issues.append(f"Line {line_num}: Missing fields {missing}")
                        except json.JSONDecodeError as e:
                            issues.append(f"Line {line_num}: Invalid JSON - {e}")
            
            elif file_path.suffix in [".yaml", ".yml"]:
                try:
                    import yaml
                    with open(file_path) as f:
                        data = yaml.safe_load(f)
                    if isinstance(data, dict) and "queries" in data:
                        valid_count = len(data.get("queries", {}))
                        total_count = valid_count
                    else:
                        issues.append("Invalid YAML structure - expected 'queries' key")
                except ImportError:
                    issues.append("YAML parser not available")
                except Exception as e:
                    issues.append(f"YAML parse error: {e}")
            else:
                return {"valid": False, "error": f"Unsupported format: {file_path.suffix}"}
            
            return {
                "exists": True,
                "path": str(file_path),
                "format": file_path.suffix,
                "valid": len(issues) == 0,
                "total_entries": total_count,
                "valid_entries": valid_count,
                "issues": issues[:10],  # Limit issues
            }
        except Exception as e:
            return {"exists": True, "valid": False, "error": str(e)}
    
    def check_embedding_exists(self, component: str, version: str | None = None) -> dict[str, Any]:
        """Check if embeddings exist for a component."""
        embeddings_dir = PATHS.embeddings
        
        if not embeddings_dir.exists():
            return {"exists": False, "error": "Embeddings directory not found"}
        
        # Look for embedding files
        patterns = {
            "cooccurrence": "*.wv",
            "instruction": "*.wv",
            "gnn": "*.json",
        }
        
        pattern = patterns.get(component.lower(), "*")
        files = list(embeddings_dir.glob(pattern))
        
        if version:
            files = [f for f in files if version in f.name]
        
        if not files:
            return {
                "exists": False,
                "component": component,
                "version": version,
                "searched_pattern": pattern,
            }
        
        # Get newest file
        newest = max(files, key=lambda p: p.stat().st_mtime)
        stat = newest.stat()
        
        return {
            "exists": True,
            "component": component,
            "version": version,
            "files_found": len(files),
            "newest_file": str(newest),
            "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "age_days": round((time.time() - stat.st_mtime) / 86400, 2),
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
        }
    
    def validate_test_set_exists(self, game: str) -> dict[str, Any]:
        """Check if test set exists for a game."""
        test_set_path = PATHS.experiments / f"test_set_unified_{game}.json"
        
        if not test_set_path.exists():
            return {
                "exists": False,
                "game": game,
                "expected_path": str(test_set_path),
            }
        
        try:
            with open(test_set_path) as f:
                data = json.load(f)
            
            queries = data.get("queries", {})
            stat = test_set_path.stat()
            
            return {
                "exists": True,
                "game": game,
                "path": str(test_set_path),
                "query_count": len(queries),
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "age_days": round((time.time() - stat.st_mtime) / 86400, 2),
            }
        except Exception as e:
            return {
                "exists": True,
                "valid": False,
                "error": str(e),
            }
    
    def validate_embedding_vocabulary(self, component: str = "cooccurrence") -> dict[str, Any]:
        """Validate embedding vocabulary matches graph nodes."""
        # Get graph nodes
        conn = self._get_connection()
        graph_nodes = set(
            row["name"]
            for row in conn.execute("SELECT name FROM nodes").fetchall()
        )
        
        # Try to load embedding
        embeddings_dir = PATHS.embeddings
        if not embeddings_dir.exists():
            return {
                "valid": False,
                "error": "Embeddings directory not found",
            }
        
        # Find embedding file
        if component == "cooccurrence":
            emb_files = list(embeddings_dir.glob("*.wv"))
        elif component == "gnn":
            emb_files = list(embeddings_dir.glob("*.json"))
        else:
            emb_files = list(embeddings_dir.glob("*"))
        
        if not emb_files:
            return {
                "valid": False,
                "error": f"No {component} embedding files found",
            }
        
        # Load newest embedding
        newest_emb = max(emb_files, key=lambda p: p.stat().st_mtime)
        
        try:
            if newest_emb.suffix == ".wv":
                try:
                    from gensim.models import KeyedVectors
                    emb = KeyedVectors.load(str(newest_emb))
                    emb_vocab = set(emb.key_to_index.keys())
                except ImportError:
                    return {
                        "valid": False,
                        "error": "gensim not available to load .wv files",
                    }
            elif newest_emb.suffix == ".json":
                with open(newest_emb) as f:
                    emb_data = json.load(f)
                if isinstance(emb_data, dict) and "vocab" in emb_data:
                    emb_vocab = set(emb_data["vocab"].keys())
                elif isinstance(emb_data, list):
                    emb_vocab = set(emb_data)
                else:
                    return {
                        "valid": False,
                        "error": "Unknown JSON embedding format",
                    }
            else:
                return {
                    "valid": False,
                    "error": f"Unknown embedding format: {newest_emb.suffix}",
                }
            
            # Compare vocabularies
            in_graph_not_emb = graph_nodes - emb_vocab
            in_emb_not_graph = emb_vocab - graph_nodes
            in_both = graph_nodes & emb_vocab
            
            coverage = len(in_both) / len(graph_nodes) if graph_nodes else 0.0
            
            return {
                "valid": coverage > 0.9,  # 90% coverage threshold
                "component": component,
                "embedding_file": str(newest_emb),
                "graph_nodes": len(graph_nodes),
                "embedding_vocab": len(emb_vocab),
                "in_both": len(in_both),
                "coverage_pct": round(coverage * 100, 2),
                "in_graph_not_emb": len(in_graph_not_emb),
                "in_emb_not_graph": len(in_emb_not_graph),
                "sample_missing_in_emb": list(in_graph_not_emb)[:10],
                "sample_missing_in_graph": list(in_emb_not_graph)[:10],
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
            }
    
    def check_test_set_coverage(self, game: str) -> dict[str, Any]:
        """Check test set query coverage against graph and embeddings."""
        test_set_path = PATHS.experiments / f"test_set_unified_{game}.json"
        
        if not test_set_path.exists():
            return {
                "exists": False,
                "game": game,
            }
        
        try:
            with open(test_set_path) as f:
                data = json.load(f)
            queries = data.get("queries", {})
        except Exception as e:
            return {
                "exists": True,
                "valid": False,
                "error": str(e),
            }
        
        # Check against graph
        conn = self._get_connection()
        graph_nodes = set(
            row["name"]
            for row in conn.execute("SELECT name FROM nodes").fetchall()
        )
        
        queries_in_graph = [q for q in queries.keys() if q in graph_nodes]
        queries_not_in_graph = [q for q in queries.keys() if q not in graph_nodes]
        
        graph_coverage = len(queries_in_graph) / len(queries) if queries else 0.0
        
        # Check against embeddings if available
        emb_coverage = None
        queries_in_emb = None
        embeddings_dir = PATHS.embeddings
        if embeddings_dir.exists():
            emb_files = list(embeddings_dir.glob("*.wv"))
            if emb_files:
                try:
                    from gensim.models import KeyedVectors
                    newest_emb = max(emb_files, key=lambda p: p.stat().st_mtime)
                    emb = KeyedVectors.load(str(newest_emb))
                    emb_vocab = set(emb.key_to_index.keys())
                    queries_in_emb = [q for q in queries.keys() if q in emb_vocab]
                    emb_coverage = len(queries_in_emb) / len(queries) if queries else 0.0
                except Exception:
                    pass
        
        return {
            "exists": True,
            "game": game,
            "total_queries": len(queries),
            "queries_in_graph": len(queries_in_graph),
            "queries_not_in_graph": len(queries_not_in_graph),
            "graph_coverage_pct": round(graph_coverage * 100, 2),
            "sample_missing_in_graph": queries_not_in_graph[:10],
            "emb_coverage_pct": round(emb_coverage * 100, 2) if emb_coverage is not None else None,
            "queries_in_emb": len(queries_in_emb) if queries_in_emb else None,
        }
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


