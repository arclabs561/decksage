#!/bin/bash
set -euo pipefail
# Migrate incremental graph from JSON to SQLite format

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

JSON_GRAPH="${1:-data/graphs/incremental_graph.json}"
DB_GRAPH="${2:-data/graphs/incremental_graph.db}"

if [ ! -f "$JSON_GRAPH" ]; then
 echo "Error: JSON graph not found: $JSON_GRAPH"
 exit 1
fi

echo "Migrating graph from JSON to SQLite..."
echo " From: $JSON_GRAPH"
echo " To: $DB_GRAPH"
echo ""

# Run Python migration script
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('$PROJECT_ROOT/src').absolute()))

from ml.data.incremental_graph import IncrementalCardGraph

json_path = Path('$JSON_GRAPH')
db_path = Path('$DB_GRAPH')

print(f'Loading graph from {json_path}...')
graph = IncrementalCardGraph(graph_path=json_path, use_sqlite=False)

print(f'Loaded: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges')

if len(graph.nodes) == 0 and len(graph.edges) == 0:
 print('Warning: Graph is empty. Nothing to migrate.')
 sys.exit(0)

# Create new graph with SQLite backend
print(f'Saving to SQLite: {db_path}...')
db_path.parent.mkdir(parents=True, exist_ok=True)

# Save with SQLite
graph_sqlite = IncrementalCardGraph(graph_path=db_path, use_sqlite=True)
graph_sqlite.nodes = graph.nodes
graph_sqlite.edges = graph.edges
graph_sqlite.last_update = graph.last_update
graph_sqlite.total_decks_processed = graph.total_decks_processed
graph_sqlite.save()

print(f'✓ Migration complete: {db_path}')
print(f' Nodes: {len(graph_sqlite.nodes):,}')
print(f' Edges: {len(graph_sqlite.edges):,}')
"

echo ""
echo "✓ Migration complete!"
echo ""
echo "Next steps:"
echo " 1. Update scripts to use .db extension: data/graphs/incremental_graph.db"
echo " 2. Test graph loading with SQLite backend"
echo " 3. Remove JSON file after verification (optional): rm $JSON_GRAPH"

