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
    with args.source.open("rb") as source, args.output.open("rb") as output:
        source_hash = hashlib.file_digest(source, "sha256").hexdigest()
        output_hash = hashlib.file_digest(output, "sha256").hexdigest()
    print(
        f"converted {len(vectors)} vectors; source sha256={source_hash} output sha256={output_hash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
