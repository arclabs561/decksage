#!/usr/bin/env bash
# Start mlx-lm inference server for local annotation (Apple Silicon only).
#
# Usage:
#   ./scripts/start_mlx_server.sh                          # default: Qwen2.5-32B-Instruct-4bit
#   ./scripts/start_mlx_server.sh --model mlx-community/Qwen3.5-9B-MLX-4bit  # faster, smaller
#   MLX_PORT=8090 ./scripts/start_mlx_server.sh            # custom port
#
# The server exposes an OpenAI-compatible API at http://localhost:${MLX_PORT}/v1
# Point annotation scripts at it with:
#   export LLM_PROVIDER=openai
#   export OPENAI_BASE_URL=http://localhost:${MLX_PORT}/v1
#   export OPENAI_API_KEY=unused

set -euo pipefail

PORT="${MLX_PORT:-8085}"
MODEL="${1:---model}"

# Parse args: support both --model <name> and bare model name
if [[ "$MODEL" == "--model" ]]; then
    MODEL="${MLX_MODEL:-mlx-community/Qwen2.5-32B-Instruct-4bit}"
elif [[ "$MODEL" != --* ]]; then
    # Bare model name passed as $1
    true
fi

# Shift past any --model flag to get the actual model name
ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)
            MODEL="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done

echo "Starting mlx-lm server..."
echo "  Model: $MODEL"
echo "  Port: $PORT"
echo "  API: http://localhost:${PORT}/v1"
echo "  Concurrency: decode=4, prompt=4, cache=8"
echo ""
echo "To use with annotation scripts:"
echo "  export LLM_PROVIDER=openai"
echo "  export OPENAI_BASE_URL=http://localhost:${PORT}/v1"
echo "  export OPENAI_API_KEY=unused"
echo ""

exec uv run mlx_lm.server \
    --model "$MODEL" \
    --port "$PORT" \
    --host 0.0.0.0 \
    --temp 0.3 \
    --decode-concurrency 4 \
    --prompt-concurrency 4 \
    --prompt-cache-size 8 \
    "${ARGS[@]}"
