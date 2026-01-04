#!/usr/bin/env bash
# Setup script for new developers
# Installs pre-commit hooks and verifies development environment

set -euo pipefail

echo "🔧 Setting up development environment..."
echo ""

# Check if pre-commit is available
if ! command -v pre-commit >/dev/null 2>&1; then
  echo "📦 Installing pre-commit..."
  if command -v uv >/dev/null 2>&1; then
    uv pip install --system pre-commit
  elif command -v pip >/dev/null 2>&1; then
    pip install pre-commit
  else
    echo "❌ Error: Neither uv nor pip found. Please install pre-commit manually."
    exit 1
  fi
fi

echo "✅ Pre-commit installed: $(pre-commit --version)"
echo ""

# Install git hooks
echo "🔗 Installing git hooks..."
pre-commit install
pre-commit install --hook-type pre-push

echo ""
echo "✅ Git hooks installed!"
echo ""

# Verify hook installation
if [ -f .git/hooks/pre-commit ]; then
  echo "✓ Pre-commit hook installed at .git/hooks/pre-commit"
else
  echo "⚠️  Warning: Pre-commit hook not found"
fi

if [ -f .git/hooks/pre-push ]; then
  echo "✓ Pre-push hook installed at .git/hooks/pre-push"
else
  echo "⚠️  Warning: Pre-push hook not found"
fi

echo ""
echo "🧪 Running pre-commit on all files to verify setup..."
pre-commit run --all-files || {
  echo ""
  echo "⚠️  Some hooks failed, but setup is complete."
  echo "   Hooks will run automatically on commit/push."
}

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "📝 Next steps:"
echo "   - Hooks will run automatically on 'git commit'"
echo "   - Hooks will run automatically on 'git push'"
echo "   - Run 'pre-commit run --all-files' to check all files"
echo "   - Run 'just pre-commit-run' for convenience"

