#!/bin/bash
set -euo pipefail
# Promote versioned models to production
#
# This script:
# 1. Takes a versioned model path (e.g., gnn_graphsage_v2024-W52.json)
# 2. Creates symlink or copies to production path (e.g., gnn_graphsage.json)
# 3. Updates metadata
# 4. Optionally archives previous production model
#
# Usage:
# ./scripts/model_management/promote_to_production.sh \
# --gnn embeddings/gnn_graphsage_v2024-W52.json \
# --cooccurrence embeddings/production_v2024-W52.wv

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_ROOT"

# Defaults
GNN_VERSIONED="${GNN_VERSIONED:-}"
COOCCURRENCE_VERSIONED="${COOCCURRENCE_VERSIONED:-}"
ARCHIVE_PREVIOUS="${ARCHIVE_PREVIOUS:-true}"
USE_SYMLINK="${USE_SYMLINK:-true}" # Use symlink (faster) or copy (safer)
S3_BUCKET="${S3_BUCKET:-s3://games-collections}"

# Parse arguments
while [[ $# -gt 0 ]]; do
 case $1 in
 --gnn)
 GNN_VERSIONED="$2"
 shift 2
 ;;
 --cooccurrence)
 COOCCURRENCE_VERSIONED="$2"
 shift 2
 ;;
 --no-archive)
 ARCHIVE_PREVIOUS=false
 shift
 ;;
 --copy)
 USE_SYMLINK=false
 shift
 ;;
 --symlink)
 USE_SYMLINK=true
 shift
 ;;
 *)
 echo "Unknown option: $1"
 echo "Usage: $0 [--gnn PATH] [--cooccurrence PATH] [--no-archive] [--copy|--symlink]"
 exit 1
 ;;
 esac
done

echo "======================================================================"
echo "PROMOTING MODELS TO PRODUCTION"
echo "======================================================================"
echo ""

# Function to promote a model
promote_model() {
 local versioned_path="$1"
 local production_path="$2"
 local model_type="$3"

 if [[ -z "$versioned_path" ]]; then
 echo "Warning: Skipping $model_type (no versioned path provided)"
 return 0
 fi

 # Resolve paths (handle S3 or local)
 if [[ "$versioned_path" == s3://* ]]; then
 # S3 path - download first
 echo "Downloading $model_type from S3: $versioned_path"
  local temp_path
  temp_path="/tmp/$(basename "$versioned_path")"
 s5cmd cp "$versioned_path" "$temp_path" 2>&1 | grep -v "^$" || {
 echo "Error: Failed to download from S3"
 return 1
 }
 versioned_path="$temp_path"
 fi

 # Check if versioned model exists
 if [[ "$versioned_path" != s3://* ]]; then
 if [[ ! -f "$versioned_path" ]]; then
 echo "Error: Versioned model not found: $versioned_path"
 echo " Please verify the path is correct and the model exists"
 return 1
 fi
 # Validate it's a real file (not empty, readable)
 if [[ ! -s "$versioned_path" ]]; then
 echo "Error: Versioned model file is empty: $versioned_path"
 return 1
 fi
 else
 # For S3 paths, validate by checking if file exists
 if ! s5cmd ls "$versioned_path" >/dev/null 2>&1; then
 echo "Error: Versioned model not found in S3: $versioned_path"
 echo " Please verify the S3 path is correct"
 return 1
 fi
 fi

 # Determine production path
 if [[ "$production_path" == s3://* ]]; then
 # S3 production path
 echo "Promoting $model_type to S3: $production_path"
 if [[ "$versioned_path" == s3://* ]]; then
 # Both S3 - copy
 s5cmd cp "$versioned_path" "$production_path" 2>&1 | grep -v "^$" || {
 echo "Error: Failed to copy to S3 production path"
 return 1
 }
 else
 # Local to S3 - upload
 s5cmd cp "$versioned_path" "$production_path" 2>&1 | grep -v "^$" || {
 echo "Error: Failed to upload to S3 production path"
 return 1
 }
 fi
 echo "✓ Promoted $model_type to S3 production"
 else
 # Local production path
 production_path="$PROJECT_ROOT/$production_path"
 production_path="${production_path#./}" # Remove leading ./

 # Archive previous production model if it exists
 if [[ "$ARCHIVE_PREVIOUS" == "true" ]] && [[ -f "$production_path" ]]; then
 archive_dir="$(dirname "$production_path")/archive"
 mkdir -p "$archive_dir"
 archive_name="$(basename "$production_path").$(date +%Y%m%d_%H%M%S)"
 echo "Archiving previous production model: $archive_name"
 cp "$production_path" "$archive_dir/$archive_name"
 echo "✓ Archived to $archive_dir/$archive_name"
 fi

 # Create parent directory
 mkdir -p "$(dirname "$production_path")"

 # Promote (symlink or copy)
 if [[ "$USE_SYMLINK" == "true" ]]; then
 # Use symlink (faster, but requires versioned file to remain)
 if [[ -L "$production_path" ]]; then
 rm "$production_path"
 fi
 ln -sf "$(realpath "$versioned_path")" "$production_path"
 echo "✓ Created symlink: $production_path -> $versioned_path"
 else
 # Copy (safer, independent of versioned file)
 cp "$versioned_path" "$production_path"
 echo "✓ Copied to production: $production_path"
 fi
 fi

 # Update metadata
 local metadata_path="${production_path%.*}_metadata.json"
 if [[ "$production_path" == s3://* ]]; then
 metadata_path="s3://${S3_BUCKET#s3://}/models/metadata/$(basename "${production_path%.*}")_metadata.json"
 fi

 local version_tag=""
 if [[ "$versioned_path" =~ _v([^./]+) ]]; then
 version_tag="${BASH_REMATCH[1]}"
 fi

 metadata=$(cat <<EOF
{
 "model_path": "$production_path",
 "versioned_path": "$versioned_path",
 "version": "$version_tag",
 "promoted_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
 "promoted_by": "$(whoami)",
 "model_type": "$model_type"
}
EOF
)

 if [[ "$metadata_path" == s3://* ]]; then
 echo "$metadata" | s5cmd cp - "$metadata_path" 2>&1 | grep -v "^$" || echo "Warning: Failed to save metadata to S3"
 else
 echo "$metadata" > "$metadata_path"
 echo "✓ Saved metadata: $metadata_path"
 fi
}

# Promote GNN model
if [[ -n "$GNN_VERSIONED" ]]; then
 echo "Step 1: Promoting GNN model..."
 GNN_PRODUCTION="embeddings/gnn_graphsage.json"
 promote_model "$GNN_VERSIONED" "$GNN_PRODUCTION" "gnn"
 echo ""
fi

# Promote co-occurrence model
if [[ -n "$COOCCURRENCE_VERSIONED" ]]; then
 echo "Step 2: Promoting co-occurrence model..."
 COOCCURRENCE_PRODUCTION="embeddings/production.wv"
 promote_model "$COOCCURRENCE_VERSIONED" "$COOCCURRENCE_PRODUCTION" "cooccurrence"
 echo ""
fi

echo "======================================================================"
echo "PRODUCTION PROMOTION COMPLETE"
echo "======================================================================"
echo ""
echo "Promoted models:"
if [[ -n "$GNN_VERSIONED" ]]; then
 echo " GNN: $GNN_VERSIONED -> embeddings/gnn_graphsage.json"
fi
if [[ -n "$COOCCURRENCE_VERSIONED" ]]; then
 echo " Co-occurrence: $COOCCURRENCE_VERSIONED -> embeddings/production.wv"
fi
echo ""
echo "Next steps:"
echo " 1. Verify models work: ./scripts/evaluation/eval_hybrid_with_runctl.sh local"
echo " 2. Sync to S3: s5cmd sync embeddings/ s3://games-collections/embeddings/"
