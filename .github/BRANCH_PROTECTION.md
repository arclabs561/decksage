# Branch Protection Setup

## Current Status

The main branch is protected with required status checks and PR reviews.

## Recommended Protection Rules

### Required Status Checks

The following CI checks should be required before merging:

1. **pre-commit** - Pre-commit hooks
2. **Lint (Ruff)** - Python linting
3. **Lint (Go)** - Go linting
4. **Tests (Fast)** - Fast test suite
5. **Type Check** - Type checking

### Protection Settings

- Require pull request reviews: 1 approval
- Require branches to be up to date before merging: Yes
- Require status checks to pass before merging: Yes
- Require conversation resolution before merging: Yes
- Do not allow force pushes: Yes
- Do not allow deletions: Yes
- Include administrators: Yes

## Setup Methods

### Method 1: GitHub Web UI (Recommended)

The GitHub API for branch protection is complex. Use the web UI:

1. Go to: https://github.com/arclabs561/decksage/settings/branches
2. Click "Add rule" for branch pattern: `main`
3. Configure:
   - Branch name pattern: `main`
   - Require a pull request before merging: Yes
   - Require approvals: 1
   - Require status checks to pass: Yes
   - Select required checks:
     - pre-commit
     - Lint (Ruff)
     - Lint (Go)
     - Tests (Fast)
     - Type Check
   - Require branches to be up to date: Yes
   - Do not allow bypassing: Yes
   - Restrict who can push: (optional)
   - Do not allow force pushes: Yes
   - Do not allow deletions: Yes
4. Click "Create" or "Save changes"

### Method 2: GitHub CLI Script

```bash
cd .github
./protect-branch.sh
```

Note: The script provides instructions for manual setup via web UI.

## Verification

After setup, verify protection is active:

```bash
gh api repos/arclabs561/decksage/branches/main/protection
```

Or check in GitHub UI: Settings > Branches > main branch rule
