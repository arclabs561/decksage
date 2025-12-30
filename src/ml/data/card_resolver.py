#!/usr/bin/env python3
"""
CardResolver: normalize card names to canonical identities.

Currently a thin wrapper that lowercases/strips and handles split-card spacing.
Future: integrate Scryfall IDs, aliases, localized names.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Optional


def normalize_split(name: str) -> str:
    if "//" in name:
        parts = [p.strip() for p in name.split("//")]
        return " // ".join(parts)
    return name


@dataclass
class CardResolver:
    scryfall_dir: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.scryfall_dir is None:
            # Default to backend Scryfall cards dir if present
            self.scryfall_dir = (
                Path(__file__).parent.parent / "backend" / "data-full" / "magic" / "scryfall" / "cards"
            )
        self._name_to_canonical: dict[str, str] = {}
        self._name_to_id: dict[str, str] = {}
        self._loaded = False

    def _safe_lower(self, s: str) -> str:
        return (s or "").strip().lower()

    def _load_index(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            if not self.scryfall_dir or not self.scryfall_dir.exists():
                return
            # Iterate a reasonable number of files; avoid heavy cost if huge
            files = list(self.scryfall_dir.glob("*.json"))
            for fp in files:
                try:
                    with open(fp) as fh:
                        data = json.load(fh)
                    name = data.get("name")
                    if not name:
                        continue
                    canonical = normalize_split(name)
                    oracle_id = data.get("oracle_id") or data.get("id")
                    self._name_to_canonical[self._safe_lower(name)] = canonical
                    if oracle_id:
                        self._name_to_id[self._safe_lower(name)] = str(oracle_id)
                    printed = data.get("printed_name")
                    if printed:
                        self._name_to_canonical[self._safe_lower(printed)] = canonical
                        if oracle_id:
                            self._name_to_id[self._safe_lower(printed)] = str(oracle_id)
                except Exception:
                    continue
        except Exception:
            # Swallow errors; resolver remains functional with normalization only
            return

    def canonical(self, name: str) -> str:
        self._load_index()
        n = normalize_split(name or "").strip()
        key = self._safe_lower(n)
        return self._name_to_canonical.get(key, n)

    def equals(self, a: str, b: str) -> bool:
        return self.canonical(a) == self.canonical(b)

    def card_id(self, name: str) -> Optional[str]:
        self._load_index()
        key = self._safe_lower(normalize_split(name))
        return self._name_to_id.get(key)


