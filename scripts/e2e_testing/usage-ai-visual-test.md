# Using @arclabs561/ai-visual-test

## Quick Start

### 1. Setup

```bash
# Install Node.js if needed: https://nodejs.org/

# Run setup script
./scripts/e2e_testing/setup_visual_tests.sh

# Or manually
cd scripts/e2e_testing
npm install
```

### 2. Set API Key

The tool needs a VLM API key. Set one of:

```bash
export GEMINI_API_KEY=your_key_here
# OR
export OPENAI_API_KEY=your_key_here
# OR
export ANTHROPIC_API_KEY=your_key_here
```

### 3. Run Tests

```bash
# Python wrapper (recommended)
python3 scripts/e2e_testing/test_visual_ai.py

# Or directly with Node.js
cd scripts/e2e_testing
node -e "
import('@arclabs561/ai-visual-test').then(async ({ validateScreenshot }) => {
  const result = await validateScreenshot(
    'screenshot.png',
    'Evaluate this search interface'
  );
  console.log(JSON.stringify(result, null, 2));
});
"
```

## How It Works

1. **Takes Screenshot**: Uses Playwright to capture UI state
2. **AI Validation**: Sends screenshot + prompt to VLM
3. **Semantic Analysis**: VLM understands visual meaning
4. **Score & Issues**: Returns 0-10 score + list of issues

## Example Output

```json
{
  "score": 8.5,
  "issues": [
    "Search button could be more prominent",
    "Advanced options toggle needs better visual indicator"
  ]
}
```

## Advantages

- **Semantic Understanding**: Understands visual meaning, not pixels
- **Natural Language**: Write tests in plain English
- **Flexible**: Adapts to minor non-breaking changes
- **Multi-Provider**: Works with Gemini, OpenAI, Claude

## Integration

Visual tests are integrated into the full test suite:

```bash
./scripts/e2e_testing/run_all_tests.sh
```

This runs all tests including visual validation.
