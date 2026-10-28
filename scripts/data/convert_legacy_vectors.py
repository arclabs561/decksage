#!/usr/bin/env python3
"""Convert a trusted Gensim KeyedVectors file to a new NumPy artifact.

Gensim loading uses pickle: only use this converter on trusted local files.
The original and any Gensim sidecar arrays are left intact.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ml.similarity.named_vectors import NamedVectors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="trusted Gensim .wv file")
    parser.add_argument("output", type=Path, help="new .npz file")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve() or args.output.exists():
        parser.error("output must be a new file distinct from the source")
    from gensim.models import KeyedVectors

    legacy = KeyedVectors.load(str(args.source))
    vectors = NamedVectors(legacy.index_to_key, legacy.vectors)
    vectors.save(args.output)
    print(
        f"converted {len(vectors)} vectors; output sha256={hashlib.sha256(args.output.read_bytes()).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
