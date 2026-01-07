#!/bin/bash
# Load VLM API keys from parent repos for visual testing

# Set script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../.." || exit 1

# Load from current .env first (highest priority)
if [ -f ".env" ]; then
    set -a
    source .env 2>/dev/null || true
    set +a
fi

# Load from ai-visual-test repo (if exists and key not already set)
if [ -z "$GEMINI_API_KEY" ] && [ -f "../ai-visual-test/.env" ]; then
    key=$(grep "^GEMINI_API_KEY=" ../ai-visual-test/.env 2>/dev/null | cut -d'=' -f2- | head -1 | tr -d '"' | tr -d "'")
    if [ -n "$key" ]; then
        export GEMINI_API_KEY="$key"
    fi
fi

# Load from developer repo (if exists and keys not already set)
if [ -f "../developer/.env" ]; then
    if [ -z "$OPENAI_API_KEY" ]; then
        key=$(grep "^OPENAI_API_KEY=" ../developer/.env 2>/dev/null | cut -d'=' -f2- | head -1 | tr -d '"' | tr -d "'")
        if [ -n "$key" ]; then
            export OPENAI_API_KEY="$key"
        fi
    fi
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        key=$(grep "^ANTHROPIC_API_KEY=" ../developer/.env 2>/dev/null | cut -d'=' -f2- | head -1 | tr -d '"' | tr -d "'")
        if [ -n "$key" ]; then
            export ANTHROPIC_API_KEY="$key"
        fi
    fi
fi

# Verify
if [ -n "$GEMINI_API_KEY" ] || [ -n "$OPENAI_API_KEY" ] || [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "✅ VLM API keys loaded"
    [ -n "$GEMINI_API_KEY" ] && echo "  - GEMINI_API_KEY: set"
    [ -n "$OPENAI_API_KEY" ] && echo "  - OPENAI_API_KEY: set"
    [ -n "$ANTHROPIC_API_KEY" ] && echo "  - ANTHROPIC_API_KEY: set"
else
    echo "⚠️  No VLM API keys found"
fi

