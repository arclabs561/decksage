#!/usr/bin/env python3
"""Extend the E5 text cache to the full card catalog.

The cache was built from the graph vocabulary (25,892 Magic cards), so 11,322
catalog cards had no text vector and could never surface in semantic search.
This appends the missing cards, batches the encoder, and leaves the previous
cache as a backup.

Run inside the API container (it has sentence-transformers and the mounted
model cache):
    docker cp scripts/training/extend_text_cache.py decksage-api:/app/extend_text_cache.py
    docker exec decksage-api python /app/extend_text_cache.py --game magic
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, "/app/src")


def catalog_text(game: str, data_dir: Path) -> dict[str, str]:
    path = data_dir / "processed" / f"card_attributes_{game}_enriched.csv"
    if not path.exists():
        path = data_dir / "processed" / f"card_attributes_{game}.csv"
    frame = pd.read_csv(path, low_memory=False)
    texts: dict[str, str] = {}
    for _, row in frame.iterrows():
        name = str(row.get("name") or "")
        if not name:
            continue
        oracle = row.get("oracle_text") or row.get("text") or ""
        if isinstance(oracle, float) and oracle != oracle:
            oracle = ""
        texts[name] = f"{name}: {str(oracle)[:200]}" if oracle else name
    return texts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", default="magic")
    parser.add_argument("--data-dir", type=Path, default=Path("/app/data"))
    parser.add_argument("--cache-dir", type=Path, default=Path("/app/data/cache"))
    parser.add_argument("--model", default="intfloat/e5-base-v2")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    from ml.similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder

    prefix = args.cache_dir / f"text_emb_cache_cards_{args.game}_intfloat-e5-base-v2"
    partial = Path(f"{prefix}.partial.npz")
    partial_names = Path(f"{prefix}.partial.names.json")
    if partial.exists() and partial_names.exists():
        # Resume: a container restart must not throw away the embeddings
        # already computed.
        matrix = np.load(partial)["matrix"].astype(np.float32)
        names = json.loads(partial_names.read_text())
        print(f"resuming from {len(names)} names", flush=True)
    elif Path(f"{prefix}.npz").exists():
        names = json.loads(Path(f"{prefix}.names.json").read_text())
        matrix = np.load(f"{prefix}.npz")["matrix"].astype(np.float32)
    else:
        # No cache yet (Pokemon, Yu-Gi-Oh!): build the whole catalog.
        names = []
        matrix = np.zeros((0, 768), dtype=np.float32)
        print("no cache yet; building from the full catalog", flush=True)
    texts = catalog_text(args.game, args.data_dir)
    missing = [name for name in texts if name not in set(names)]
    print(f"cache {len(names)} catalog {len(texts)} missing {len(missing)}", flush=True)
    if not missing:
        return 0

    embedder = InstructionTunedCardEmbedder(model_name=args.model)
    added = 0
    batch = 256
    for start in range(0, len(missing), batch):
        chunk = missing[start : start + batch]
        vectors = embedder.embed_cards_batch(
            [texts[name] for name in chunk],
            instruction_type="substitution",
            batch_size=args.batch_size,
        )
        matrix = np.vstack([matrix, np.asarray(vectors, dtype=np.float32)])
        names.extend(chunk)
        added += len(chunk)
        if added % 1024 < batch:
            # Checkpoint roughly every thousand rows; a killed container
            # resumes instead of re-embedding from zero.
            np.savez_compressed(partial, matrix=matrix, norms=np.linalg.norm(matrix, axis=1))
            partial_names.write_text(json.dumps(names))
        print(f"embedded {added}/{len(missing)}", flush=True)

    norms = np.linalg.norm(matrix, axis=1)
    if Path(f"{prefix}.npz").exists():
        shutil.copy(f"{prefix}.npz", f"{prefix}.npz.vocab-backup")
        shutil.copy(f"{prefix}.names.json", f"{prefix}.names.json.vocab-backup")
    np.savez_compressed(f"{prefix}.npz", matrix=matrix, norms=norms)
    Path(f"{prefix}.names.json").write_text(json.dumps(names))
    Path(f"{prefix}.meta.json").write_text(
        json.dumps({"encoder": args.model, "dim": int(matrix.shape[1])})
    )
    partial.unlink(missing_ok=True)
    partial_names.unlink(missing_ok=True)
    print(f"wrote {len(names)} names, matrix {matrix.shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
