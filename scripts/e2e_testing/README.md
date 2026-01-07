# E2E Testing Suite

End-to-end testing for DeckSage API, UI, and features.

## Quick Start

```bash
# Run all tests
./scripts/e2e_testing/run_all_tests.sh

# Individual test suites
python3 scripts/e2e_testing/test_api_endpoints_comprehensive.py
python3 scripts/e2e_testing/test_type_ahead_comprehensive.py
python3 scripts/e2e_testing/test_security.py
python3 scripts/e2e_testing/test_performance.py
python3 scripts/e2e_testing/test_browser_comprehensive.py
uv run python scripts/e2e_testing/e2e_test_suite.py --author "your_name"
```

## Setup

```bash
uv add python-dotenv playwright requests
playwright install chromium
```

## Test Coverage

1. API Endpoints (`test_api_endpoints_comprehensive.py`)
2. Type-Ahead (`test_type_ahead_comprehensive.py`)
3. Integration (`test_integration_deep.py`)
4. Accessibility (`test_accessibility_deep.py`)
5. Security (`test_security.py`)
6. Performance (`test_performance.py`)
7. Visual Testing (`test_visual_ai.py`)
8. Expert Experience (`test_expert_experience.py`)
9. Browser/UI (`test_browser_comprehensive.py`, `test_comprehensive_ui.py`)
10. Feedback Workflow (`e2e_test_suite.py`)

## Feedback Workflow

1. Submit feedback via API or UI → `data/annotations/user_feedback.jsonl`
2. Convert to annotations: `uv run python scripts/annotation/convert_feedback_to_annotations.py --min-rating 2`
3. Use in training as substitution pairs
