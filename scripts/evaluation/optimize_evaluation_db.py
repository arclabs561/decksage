#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Optimize evaluation database for performance.

Features:
- VACUUM (reclaim space)
- REINDEX (rebuild indexes)
- ANALYZE (update statistics)
- Query optimization suggestions
"""

import sqlite3
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()


def optimize_database(db_path: Path, vacuum: bool = True, reindex: bool = True, analyze: bool = True) -> dict[str, Any]:
    """
    Optimize SQLite database.
    
    Args:
        db_path: Path to database
        vacuum: Run VACUUM
        reindex: Run REINDEX
        analyze: Run ANALYZE
    
    Returns:
        Optimization results
    """
    if not db_path.exists():
        return {"status": "missing", "error": "Database not found"}
    
    results = {
        "status": "ok",
        "operations": [],
        "size_before": db_path.stat().st_size,
    }
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        if vacuum:
            cursor.execute("VACUUM")
            results["operations"].append("VACUUM")
        
        if reindex:
            cursor.execute("REINDEX")
            results["operations"].append("REINDEX")
        
        if analyze:
            cursor.execute("ANALYZE")
            results["operations"].append("ANALYZE")
        
        conn.commit()
    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
    finally:
        conn.close()
    
    results["size_after"] = db_path.stat().st_size
    results["size_reduction"] = results["size_before"] - results["size_after"]
    
    return results


def analyze_query_performance(db_path: Path) -> dict[str, Any]:
    """Analyze query performance and suggest optimizations."""
    if not db_path.exists():
        return {"status": "missing"}
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    suggestions = []
    
    # Check index usage
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND name NOT LIKE 'sqlite_%'
    """)
    indexes = [row[0] for row in cursor.fetchall()]
    
    # Check table size
    cursor.execute("SELECT COUNT(*) FROM evaluation_runs")
    row_count = cursor.fetchone()[0]
    
    # Suggest indexes for common queries
    if row_count > 1000:
        if "idx_timestamp" not in indexes:
            suggestions.append("Consider adding index on timestamp for time-based queries")
        if "idx_evaluation_type" not in indexes:
            suggestions.append("Consider adding index on evaluation_type for filtering")
    
    conn.close()
    
    return {
        "row_count": row_count,
        "indexes": indexes,
        "suggestions": suggestions,
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Optimize evaluation database")
    parser.add_argument("--db-path", type=Path, default=Path("experiments/evaluation_logs/evaluation_runs.db"))
    parser.add_argument("--no-vacuum", dest="vacuum", action="store_false", default=True)
    parser.add_argument("--no-reindex", dest="reindex", action="store_false", default=True)
    parser.add_argument("--no-analyze", dest="analyze", action="store_false", default=True)
    parser.add_argument("--analyze-queries", action="store_true", help="Analyze query performance")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Database Optimization")
    print("=" * 80)
    print("")
    
    # Optimize
    print("🔧 Optimizing database...")
    results = optimize_database(
        db_path=args.db_path,
        vacuum=args.vacuum,
        reindex=args.reindex,
        analyze=args.analyze,
    )
    
    if results["status"] == "ok":
        print(f"  ✅ Operations: {', '.join(results['operations'])}")
        print(f"  Size before: {results['size_before']:,} bytes")
        print(f"  Size after: {results['size_after']:,} bytes")
        if results["size_reduction"] > 0:
            print(f"  Space reclaimed: {results['size_reduction']:,} bytes")
    else:
        print(f"  ❌ Error: {results.get('error', 'Unknown')}")
        return 1
    
    print("")
    
    # Analyze queries
    if args.analyze_queries:
        print("📊 Analyzing query performance...")
        analysis = analyze_query_performance(args.db_path)
        
        print(f"  Rows: {analysis['row_count']:,}")
        print(f"  Indexes: {len(analysis['indexes'])}")
        
        if analysis["suggestions"]:
            print("  Suggestions:")
            for suggestion in analysis["suggestions"]:
                print(f"    - {suggestion}")
    
    print("")
    print("✅ Optimization complete")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

