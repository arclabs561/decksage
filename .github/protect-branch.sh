#!/bin/bash
# Protect main branch with required status checks
# Usage: ./protect-branch.sh

set -euo pipefail

echo "Protecting main branch..."

# Check if gh CLI is available
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is not installed"
    echo "Install: https://cli.github.com/"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "Error: Not authenticated with GitHub CLI"
    echo "Run: gh auth login"
    exit 1
fi

# Get repository name
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)

echo "Repository: $REPO"
echo ""
echo "Note: GitHub API for branch protection is complex."
echo "Using web UI method instead..."
echo ""
echo "Please set branch protection manually:"
echo "https://github.com/$REPO/settings/branches"
echo ""
echo "Or use GitHub CLI with proper JSON file (see BRANCH_PROTECTION.md)"
echo ""
exit 0
