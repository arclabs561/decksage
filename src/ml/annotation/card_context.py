"""Load complete card rules and relevant stats for annotation prompts."""

from __future__ import annotations

import csv
from pathlib import Path


def load_card_context(data_dir: Path, game: str) -> dict[str, str]:
    candidates = [data_dir / "processed" / f"card_attributes_{game}_enriched.csv"]
    if game == "magic":
        candidates.append(data_dir / "processed" / "card_attributes_enriched.csv")
    candidates.append(data_dir / "processed" / f"card_attributes_{game}.csv")
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        return {}
    context = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or "").strip()
            text = row.get("oracle_text") or row.get("text") or row.get("effect") or ""
            if not name or not text.strip() or text.strip().lower() == "nan":
                continue
            parts = [
                f"Name: {name}",
                f"Type: {row.get('type_line') or row.get('type') or 'unknown'}",
            ]
            if row.get("mana_cost"):
                parts.append(f"Mana cost: {row['mana_cost']}")
            if row.get("power") and row.get("toughness"):
                parts.append(f"Power/toughness: {row['power']}/{row['toughness']}")
            if row.get("hp"):
                parts.append(f"HP: {row['hp']}")
            if row.get("atk") and row.get("def_stat"):
                parts.append(f"ATK/DEF: {row['atk']}/{row['def_stat']}")
            parts.append(f"Text: {text}")
            context[name] = "\n".join(parts)
    return context
