#!/usr/bin/env bash
# Update all scripts to use unified test sets

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=" | tr -d '\n' | head -c 70 && echo
echo "UPDATING ALL TEST SET PATHS TO UNIFIED"
echo "=" | tr -d '\n' | head -c 70 && echo

# Find all Python scripts referencing old test sets
FILES=$(grep -r "test_set_canonical\|test_set_expanded" src/ml/scripts/*.py 2>/dev/null | cut -d: -f1 | sort -u)

UPDATED=0
for file in $FILES; do
    echo "Updating $file..."

    # Create backup
    cp "$file" "${file}.bak"

    # Replace canonical with unified
    sed -i '' 's|test_set_canonical_magic\.json|test_set_unified_magic.json|g' "$file"
    sed -i '' 's|test_set_canonical_pokemon\.json|test_set_unified_pokemon.json|g' "$file"
    sed -i '' 's|test_set_canonical_yugioh\.json|test_set_unified_yugioh.json|g' "$file"

    # Replace expanded with unified
    sed -i '' 's|test_set_expanded_magic\.json|test_set_unified_magic.json|g' "$file"
    sed -i '' 's|test_set_expanded_pokemon\.json|test_set_unified_pokemon.json|g' "$file"
    sed -i '' 's|test_set_expanded_yugioh\.json|test_set_unified_yugioh.json|g' "$file"

    # Check if changes were made
    if ! diff -q "$file" "${file}.bak" > /dev/null; then
        echo "  Updated"
        UPDATED=$((UPDATED + 1))
        rm "${file}.bak"
    else
        echo "  No changes needed"
        rm "${file}.bak"
    fi
done

echo ""
echo "Updated $UPDATED files"
echo "Done"
