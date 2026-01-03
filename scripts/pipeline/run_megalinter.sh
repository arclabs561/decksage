#!/usr/bin/env bash
# Run MegaLinter locally using Docker
# Usage: ./scripts/run_megalinter.sh [quick|full|fix]

set -euo pipefail

MODE="${1:-quick}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
  echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $*"
}

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
  log_error "Docker is not running. Please start Docker and try again."
  exit 1
fi

cd "$REPO_ROOT"

# Set environment variables based on mode
case "$MODE" in
  quick)
    log_info "Running MegaLinter in QUICK mode (modified files only)..."
    export VALIDATE_ALL_CODEBASE=false
    export GITHUB_ACTIONS=false
    ;;
  full)
    log_info "Running MegaLinter in FULL mode (all files)..."
    export VALIDATE_ALL_CODEBASE=true
    export GITHUB_ACTIONS=false
    ;;
  fix)
    log_info "Running MegaLinter in FIX mode (apply auto-fixes)..."
    export VALIDATE_ALL_CODEBASE=true
    export APPLY_FIXES=all
    export GITHUB_ACTIONS=false
    ;;
  *)
    log_error "Unknown mode: $MODE"
    echo "Usage: $0 [quick|full|fix]"
    exit 1
    ;;
esac

# Use optimized flavor for Go + Python
FLAVOR="cupcake"  # Smaller base image, we'll add what we need

log_info "Pulling MegaLinter image..."
docker pull "oxsecurity/megalinter-${FLAVOR}:v9"  # Use v9 instead of latest for consistency

log_info "Running MegaLinter..."
docker run --rm \
  -e VALIDATE_ALL_CODEBASE="${VALIDATE_ALL_CODEBASE:-false}" \
  -e APPLY_FIXES="${APPLY_FIXES:-none}" \
  -e GITHUB_ACTIONS="${GITHUB_ACTIONS:-false}" \
  -e LOG_LEVEL=INFO \
  -v "$REPO_ROOT:/tmp/lint:rw" \
  "oxsecurity/megalinter-${FLAVOR}:latest"

# Check if megalinter-reports was created
if [ -d "$REPO_ROOT/megalinter-reports" ]; then
  log_info "MegaLinter reports generated in: megalinter-reports/"
  
  # Print summary if available
  if [ -f "$REPO_ROOT/megalinter-reports/megalinter-report.txt" ]; then
    echo ""
    log_info "=== SUMMARY ==="
    tail -n 30 "$REPO_ROOT/megalinter-reports/megalinter-report.txt"
  fi
else
  log_warn "No reports directory created. Check console output for errors."
fi

log_info "MegaLinter run complete!"
echo ""
echo "To view detailed results:"
echo "  - Text report: megalinter-reports/megalinter-report.txt"
echo "  - SARIF report: megalinter-reports/megalinter.sarif"
echo "  - Linter logs: megalinter-reports/linters_logs/"
