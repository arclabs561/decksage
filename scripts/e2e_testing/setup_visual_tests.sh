#!/bin/bash
# Setup AI visual testing tools

set -euo pipefail

echo "=========================================="
echo "Setting up AI Visual Testing"
echo "=========================================="
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed"
    echo "   Install from: https://nodejs.org/"
    exit 1
fi

echo "✅ Node.js version: $(node --version)"
echo "✅ npm version: $(npm --version)"
echo ""

# Install @arclabs561/ai-visual-test
echo "Installing @arclabs561/ai-visual-test..."
cd "$(dirname "$0")"

if [ -f "package.json" ]; then
    npm install
else
    npm install -g @arclabs561/ai-visual-test
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Run visual tests with:"
echo "  python3 scripts/e2e_testing/test_visual_ai.py"
echo ""
echo "Or directly:"
echo "  npx @arclabs561/ai-visual-test test --config scripts/e2e_testing/tests/visual/config.json"

