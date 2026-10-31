#!/usr/bin/env python3
"""Host-native MPS embedding bridge for Linux containers.

Docker Desktop cannot pass Metal into a container. The supported pattern (the
one Docker Model Runner uses for vllm-metal) is a host-native service over TCP.
This exposes the E5 encoder on the host, where ``torch.backends.mps`` works,
and the container's cache builder calls it.

Run on the host:
    uv run --with fastapi --with uvicorn --with sentence-transformers --with torch \
        python scripts/ops/mps_bridge.py --port 8765
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


class EmbedRequest(BaseModel):
    texts: list[str]
    instruction_type: str = "substitution"


app = FastAPI(title="DeckSage MPS bridge")
embedder = None
device = None


@app.on_event("startup")
def load() -> None:
    global embedder, device
    import torch

    from ml.similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    embedder = InstructionTunedCardEmbedder(model_name="intfloat/e5-base-v2", device=device)
    print(f"mps bridge ready on {device}", flush=True)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "device": device, "model": "intfloat/e5-base-v2"}


@app.post("/embed")
def embed(request: EmbedRequest) -> dict:
    if embedder is None:
        return {"vectors": []}
    vectors = embedder.embed_cards_batch(
        request.texts, instruction_type=request.instruction_type, batch_size=64
    )
    return {"vectors": [vector.tolist() for vector in vectors]}


def main() -> int:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
