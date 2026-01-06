#!/usr/bin/env bash
# Run all evaluation logging tests and validation

set -euo pipefail

echo "=================================================================================="
echo "Running Evaluation Logging Tests & Validation"
echo "=================================================================================="
echo ""

# Run pytest tests
echo "1. Running pytest tests..."
uv run python -m pytest src/ml/tests/test_evaluation_logger.py -v --tb=short
echo ""

# Run validation
echo "2. Validating data formats..."
uv run python scripts/evaluation/validate_evaluation_data.py --format all
echo ""

# Verify integrity
echo "3. Verifying data integrity..."
uv run python scripts/evaluation/verify_data_integrity.py
echo ""

# Check schema migration
echo "4. Checking schema migration..."
uv run python scripts/evaluation/migrate_schema.py --dry-run
echo ""

echo "=================================================================================="
echo "All tests and validation complete"
echo "=================================================================================="


