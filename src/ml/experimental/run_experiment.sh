#!/bin/bash
# End-to-end card similarity experiment

set -e

echo "=== DeckSage Card Similarity Experiment ==="
echo ""

# Step 1: Extract data (if needed)
echo "Step 1: Checking data..."
if [ ! -f "../backend/data-full/games/magic/mtgtop8" ]; then
    echo "No data found. Run extraction first:"
    echo "  cd ../backend"
    echo "  go run ./cmd/dataset extract mtgtop8 --limit=100 --bucket=file://./data-full"
    exit 1
fi

# Step 2: Build co-occurrence graph
echo "Step 2: Building co-occurrence graph..."
cd ../backend
if [ ! -f "pairs.csv" ]; then
    echo "Building card co-occurrence matrix..."
    # This would use the Go transform command
    # For now, we'll create a simple test script
    cat > build_graph.go << 'EOF'
package main

import (
    "context"
    "fmt"
    "collections/blob"
    "collections/games/magic/dataset/mtgtop8"
    "collections/logger"
    "collections/transform/cardco"
)

func main() {
    ctx := context.Background()
    log := logger.NewLogger()
    
    bucket, err := blob.NewBucket(ctx, "file://./data-full")
    if err != nil {
        panic(err)
    }
    
    ds := mtgtop8.NewDataset(log, bucket)
    
    tr, err := cardco.NewTransform(ctx, log)
    if err != nil {
        panic(err)
    }
    defer tr.Close()
    
    _, err = tr.Transform(ctx, []interface{}{ds})
    if err != nil {
        panic(err)
    }
    
    err = tr.ExportCSV(ctx, "pairs.csv")
    if err != nil {
        panic(err)
    }
    
    fmt.Println("✅ Graph exported to pairs.csv")
}
EOF
    go run build_graph.go
fi

# Step 3: Install Python dependencies
echo ""
echo "Step 3: Installing Python dependencies..."
cd ../ml
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt

# Step 4: Train embeddings
echo ""
echo "Step 4: Training Node2Vec embeddings..."
python card_embeddings.py \
    --input ../backend/pairs.csv \
    --game magic \
    --dim 128 \
    --epochs 50 \
    --visualize \
    --query "Lightning Bolt"

echo ""
echo "=== Experiment Complete! ==="
echo "Outputs:"
echo "  - ../backend/magic_embeddings.npy"
echo "  - ../backend/magic_card_index.json"
echo "  - ../backend/magic_tsne.png"
