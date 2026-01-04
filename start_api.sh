#!/bin/bash
# Start the DeckSage API with embeddings
# Usage: ./start_api.sh [embeddings_path]

set -e

# Default embeddings path
EMBEDDINGS_PATH="${1:-data/embeddings/magic_128d_test_pecanpy.wv}"

# Check if embeddings file exists
if [ ! -f "$EMBEDDINGS_PATH" ]; then
    echo "Error: Embeddings file not found: $EMBEDDINGS_PATH"
    echo ""
    echo "Available embeddings:"
    ls -lh data/embeddings/*.wv 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}' || echo "  (none found)"
    echo ""
    echo "Usage: $0 [path/to/embeddings.wv]"
    exit 1
fi

echo "Starting DeckSage API..."
echo "  Embeddings: $EMBEDDINGS_PATH"
echo "  Port: 8000"
echo "  URL: http://localhost:8000"
echo ""

# Check if API is already running
if curl -s http://localhost:8000/ready > /dev/null 2>&1; then
    echo "Warning: API is already running on port 8000"
    echo "  Stop it first or use a different port"
    exit 1
fi

# Start the API
export EMBEDDINGS_PATH="$EMBEDDINGS_PATH"
python3 -m src.ml.api.api --embeddings "$EMBEDDINGS_PATH" --port 8000

