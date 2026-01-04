#!/usr/bin/env bash
# Setup script for new developers
# Installs pre-commit hooks and verifies development environment

set -euo pipefail

echo "🔧 Setting up development environment..."
echo ""

# Check if pre-commit is available
export PATH="$HOME/.local/bin:$PATH"
if ! command -v pre-commit >/dev/null 2>&1 && ! python3 -m pre_commit --version >/dev/null 2>&1; then
  echo "📦 Installing pre-commit..."
  if command -v uv >/dev/null 2>&1; then
    uv pip install --system pre-commit || python3 -m pip install --user pre-commit
  elif command -v pip >/dev/null 2>&1; then
    pip install --user pre-commit || python3 -m pip install --user pre-commit
  else
    python3 -m pip install --user pre-commit
  fi
  export PATH="$HOME/.local/bin:$PATH"
fi

# Verify installation
if command -v pre-commit >/dev/null 2>&1; then
  echo "✅ Pre-commit installed: $(pre-commit --version)"
elif python3 -m pre_commit --version >/dev/null 2>&1; then
  echo "✅ Pre-commit installed: $(python3 -m pre_commit --version)"
  export PATH="$HOME/.local/bin:$PATH"
else
  echo "❌ Pre-commit installation failed"
  exit 1
fi
echo ""

# Install git hooks
echo "🔗 Installing git hooks..."
if command -v pre-commit >/dev/null 2>&1; then
  pre-commit install
  pre-commit install --hook-type pre-push
elif python3 -m pre_commit --version >/dev/null 2>&1; then
  python3 -m pre_commit install
  python3 -m pre_commit install --hook-type pre-push
else
  echo "❌ Cannot install hooks - pre-commit not found"
  exit 1
fi

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
if command -v pre-commit >/dev/null 2>&1; then
  pre-commit run --all-files || {
elif python3 -m pre_commit --version >/dev/null 2>&1; then
  python3 -m pre_commit run --all-files || {
else
  echo "⚠️  Cannot run pre-commit - not in PATH"
  echo "   Add to your shell: export PATH=\"\$HOME/.local/bin:\$PATH\""
  {
fi
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

