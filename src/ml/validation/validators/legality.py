"""
Deterministic legality checking (ban lists / copy restrictions).

Contract:
- This module is only used when legality enforcement is explicitly requested.
- It is **deterministic**: we do not silently "skip legality" if data is missing.
- Data is expected to be provided via local cached ban-list files (which can be
  generated/synced out-of-band, e.g. from object storage).

Cache layout (project-root relative):
  .cache/ban_lists/
    - mtg_legality.json
    - yugioh_banlist.json
    - pokemon_legality.json
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ...utils.paths import PATHS


logger = logging.getLogger(__name__)


def _cache_dir() -> Path:
    return Path(PATHS.project_root) / ".cache" / "ban_lists"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Ban list cache not found: {path}. Populate it under {path.parent}."
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Ban list cache must be a JSON object/dict: {path}")
    return data


def _warn_if_stale(path: Path, max_age_days: int = 7) -> None:
    try:
        age_s = time.time() - path.stat().st_mtime
        if age_s > max_age_days * 86400:
            logger.warning(
                "Ban list cache looks stale (%sd > %sd): %s",
                int(age_s / 86400),
                max_age_days,
                path,
            )
    except Exception:
        return


def _deck_card_counts(deck: Any) -> Counter[str]:
    """
    Aggregate card counts across partitions.

    Supports:
    - dict deck objects with {"partitions":[{"cards":[{"name","count"}]}]}
    - Pydantic models with `.partitions` and `.cards`
    """
    counts: Counter[str] = Counter()

    parts = getattr(deck, "partitions", None)
    if parts is None and isinstance(deck, dict):
        parts = deck.get("partitions", []) or []

    for p in parts or []:
        cards = getattr(p, "cards", None)
        if cards is None and isinstance(p, dict):
            cards = p.get("cards", []) or []
        for c in cards or []:
            name = getattr(c, "name", None)
            if name is None and isinstance(c, dict):
                name = c.get("name")
            if not name:
                continue
            n = getattr(c, "count", None)
            if n is None and isinstance(c, dict):
                n = c.get("count", 0)
            try:
                counts[str(name)] += int(n or 0)
            except Exception:
                continue

    return counts


def _get_deck_format(deck: Any) -> str | None:
    fmt = getattr(deck, "format", None)
    if fmt is None and isinstance(deck, dict):
        fmt = deck.get("format")
    if fmt is None:
        return None
    fmt_s = str(fmt).strip()
    return fmt_s or None


def _normalize_key(s: str) -> str:
    return str(s).strip().lower()


def _extract_mtg_rules(cache: dict[str, Any], fmt: str | None) -> tuple[set[str], set[str]]:
    """
    Return (banned, restricted) sets for MTG for the given format.

    Supported cache shapes:
    - {"formats": {"Modern": {"banned":[...], "restricted":[...]}, ...}}
    - {"Modern": {"banned":[...], "restricted":[...]}, ...}
    - {"banned":[...]} (formatless)
    """
    banned: Iterable[str] = []
    restricted: Iterable[str] = []

    formats_obj = cache.get("formats") if isinstance(cache.get("formats"), dict) else None
    fmt_obj = None
    if fmt and formats_obj:
        fmt_obj = (
            formats_obj.get(fmt) or formats_obj.get(fmt.title()) or formats_obj.get(fmt.upper())
        )
        if fmt_obj is None:
            # try case-insensitive match
            want = _normalize_key(fmt)
            for k, v in formats_obj.items():
                if _normalize_key(k) == want:
                    fmt_obj = v
                    break
    elif fmt and isinstance(cache, dict):
        fmt_obj = cache.get(fmt) or cache.get(fmt.title()) or cache.get(fmt.upper())
        if fmt_obj is None:
            want = _normalize_key(fmt)
            for k, v in cache.items():
                if _normalize_key(k) == want and isinstance(v, dict):
                    fmt_obj = v
                    break

    if isinstance(fmt_obj, dict):
        banned = fmt_obj.get("banned") or []
        restricted = fmt_obj.get("restricted") or []
    else:
        banned = cache.get("banned") or []
        restricted = cache.get("restricted") or []

    return set(map(str, banned)), set(map(str, restricted))


def _extract_ygo_rules(cache: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    """
    Return (forbidden, limited, semi_limited) sets for YGO.

    Supported cache shapes:
    - {"forbidden":[...], "limited":[...], "semi_limited":[...]}
    - {"forbidden":[...], "limited":[...], "semi-limited":[...]}
    """
    forbidden = set(map(str, cache.get("forbidden") or cache.get("forbidden_list") or []))
    limited = set(map(str, cache.get("limited") or cache.get("limited_list") or []))
    semi = set(
        map(
            str,
            cache.get("semi_limited")
            or cache.get("semi-limited")
            or cache.get("semi_limited_list")
            or [],
        )
    )
    return forbidden, limited, semi


def _extract_pokemon_rules(cache: dict[str, Any]) -> set[str]:
    """Return banned set for Pokémon."""
    banned = cache.get("banned") or cache.get("banned_cards") or []
    return set(map(str, banned))


def check_deck_legality(
    deck: Any, *, game: str | None = None, format: str | None = None
) -> list[str]:
    """
    Check deck legality for a given game/format.

    Returns:
        List of human-readable issues. Empty means "no issues found".

    Raises:
        FileNotFoundError / ValueError if legality data is not available/configured.
    """
    game_l = (
        (
            game
            or getattr(deck, "game", None)
            or (deck.get("game") if isinstance(deck, dict) else None)
            or ""
        )
        .strip()
        .lower()
    )  # type: ignore[union-attr]
    fmt = format or _get_deck_format(deck)

    if game_l not in {"magic", "pokemon", "yugioh"}:
        raise ValueError(f"Unsupported game for legality checking: {game_l or 'unknown'}")

    issues: list[str] = []
    counts = _deck_card_counts(deck)

    cache_dir = _cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    if game_l == "magic":
        path = cache_dir / "mtg_legality.json"
        _warn_if_stale(path)
        cache = _load_json(path)
        banned, restricted = _extract_mtg_rules(cache, fmt)

        for card, n in counts.items():
            if card in banned and n > 0:
                issues.append(f"{card} is banned in {fmt or 'this format'}")
            if card in restricted and n > 1:
                issues.append(f"{card} is restricted in {fmt or 'this format'} (has {n}, max 1)")

        return issues

    if game_l == "yugioh":
        path = cache_dir / "yugioh_banlist.json"
        _warn_if_stale(path)
        cache = _load_json(path)
        forbidden, limited, semi = _extract_ygo_rules(cache)

        for card, n in counts.items():
            if card in forbidden and n > 0:
                issues.append(f"{card} is Forbidden (has {n}, max 0)")
            if card in limited and n > 1:
                issues.append(f"{card} is Limited (has {n}, max 1)")
            if card in semi and n > 2:
                issues.append(f"{card} is Semi-Limited (has {n}, max 2)")

        return issues

    # pokemon
    path = cache_dir / "pokemon_legality.json"
    _warn_if_stale(path)
    cache = _load_json(path)
    banned = _extract_pokemon_rules(cache)

    for card, n in counts.items():
        if card in banned and n > 0:
            issues.append(f"{card} is banned in {fmt or 'this format'}")

    return issues


__all__ = ["check_deck_legality"]
