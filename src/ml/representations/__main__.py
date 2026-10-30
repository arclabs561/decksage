"""Print what every declared representation resolves to.

python -m ml.representations            # full table, hashes included
python -m ml.representations --no-hash  # skip content hashes (fast)
python -m ml.representations --json     # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys

from ml.representations.manifest import build_manifest
from ml.representations.registry import RepresentationRegistry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-hash", action="store_true", help="skip content hashes")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument("--game", help="only this game")
    args = parser.parse_args(argv)

    manifest = build_manifest()
    if args.game:
        manifest = type(manifest)(
            root=manifest.root,
            representations=tuple(r for r in manifest if r.game == args.game),
        )
    table = RepresentationRegistry(manifest).verify(include_hash=not args.no_hash)
    if args.json:
        json.dump(table.as_dicts(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(table.format())
    return 0 if table.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
