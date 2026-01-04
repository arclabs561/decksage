#!/usr/bin/env bash
# Setup script for new developers
# Installs prek (fast pre-commit alternative) and verifies development environment

set -euo pipefail

echo "🔧 Setting up development environment..."
echo ""

# Check if prek is available (preferred - faster, uses uv)
export PATH="$HOME/.local/bin:$PATH"
if ! command -v prek >/dev/null 2>&1; then
  echo "📦 Installing prek (fast pre-commit alternative)..."
  if command -v uv >/dev/null 2>&1; then
    echo "   Using uv (recommended for this project)..."
    uv tool install prek
  elif command -v brew >/dev/null 2>&1; then
    echo "   Using Homebrew..."
    brew install prek
  else
    echo "   Using standalone installer..."
    curl --proto '=https' --tlsv1.2 -LsSf https://github.com/j178/prek/releases/download/v0.2.25/prek-installer.sh | sh
  fi
  export PATH="$HOME/.local/bin:$PATH"
fi

# Verify installation
if command -v prek >/dev/null 2>&1; then
  echo "✅ Prek installed: $(prek --version)"
  echo "   (7x faster than pre-commit, drop-in replacement)"
else
  echo "⚠️  Prek not found, falling back to pre-commit..."
  # Fallback to pre-commit if prek installation failed
  if ! command -v pre-commit >/dev/null 2>&1 && ! python3 -m pre_commit --version >/dev/null 2>&1; then
    echo "📦 Installing pre-commit (fallback)..."
    if command -v uv >/dev/null 2>&1; then
      uv pip install --system pre-commit || python3 -m pip install --user pre-commit
    else
      python3 -m pip install --user pre-commit
    fi
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi
echo ""

# Install git hooks
echo "🔗 Installing git hooks..."
if command -v prek >/dev/null 2>&1; then
  echo "   Using prek..."
  prek install
  prek install --hook-type pre-push
elif command -v pre-commit >/dev/null 2>&1; then
  echo "   Using pre-commit (fallback)..."
  pre-commit install
  pre-commit install --hook-type pre-push
elif python3 -m pre_commit --version >/dev/null 2>&1; then
  echo "   Using pre-commit via python3 (fallback)..."
  python3 -m pre_commit install
  python3 -m pre_commit install --hook-type pre-push
else
  echo "❌ Cannot install hooks - neither prek nor pre-commit found"
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
echo "🧪 Running hooks on all files to verify setup..."
if command -v prek >/dev/null 2>&1; then
  if ! prek run --all-files; then
    echo ""
    echo "⚠️  Some hooks failed, but setup is complete."
    echo "   Hooks will run automatically on commit/push."
  fi
elif command -v pre-commit >/dev/null 2>&1; then
  if ! pre-commit run --all-files; then
    echo ""
    echo "⚠️  Some hooks failed, but setup is complete."
    echo "   Hooks will run automatically on commit/push."
  fi
elif python3 -m pre_commit --version >/dev/null 2>&1; then
  if ! python3 -m pre_commit run --all-files; then
    echo ""
    echo "⚠️  Some hooks failed, but setup is complete."
    echo "   Hooks will run automatically on commit/push."
  fi
else
  echo "⚠️  Cannot run hooks - not in PATH"
  echo "   Add to your shell: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "📝 Next steps:"
echo "   - Hooks will run automatically on 'git commit'"
echo "   - Hooks will run automatically on 'git push'"
if command -v prek >/dev/null 2>&1; then
  echo "   - Run 'prek run --all-files' to check all files"
  echo "   - Run 'just pre-commit-run' for convenience (uses prek)"
else
  echo "   - Run 'pre-commit run --all-files' to check all files"
  echo "   - Run 'just pre-commit-run' for convenience"
fi
