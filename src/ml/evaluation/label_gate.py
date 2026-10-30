"""Refuse to score or calibrate on labels that contradict themselves.

The rule engine lives in ``scripts/annotation/screen_contradictions.py``, which
is a standalone tool rather than an importable package. This gate loads it by
path so evaluation code can use the same rules without a second copy.

The gate is about *structural* contradictions only: a card judged against
itself, a creature judged against a Trainer/Energy/Spell/Trap as a substitute,
and different Pokemon evolution stages treated as substitutes. Those are
decidable from shipped metadata and are not credible judgments.

Differing energy types or Yu-Gi-Oh attributes, duplicate rounds, bucket
mismatches and evidence-poor records are reported by the same rules but are not
refusals: a cross-type card can be a genuine substitute for another deck, and the
rest need a human decision or are metadata coverage rather than label error.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCREEN_PATH = PROJECT_ROOT / "scripts" / "annotation" / "screen_contradictions.py"
METADATA_DIR = PROJECT_ROOT / "data" / "processed"

# Rules that make a metric untrustworthy rather than merely questionable.
# ``type_conflict`` is reported but not blocking: a same-role card in another
# energy type can still be a real substitute for a different deck, so the screen
# cannot decide it without a human. A gate that blocks on legitimate labels gets
# overridden until it means nothing.
BLOCKING_RULES: tuple[str, ...] = (
    "self_pair",
    "kind_conflict",
    "evolution_conflict",
)


@dataclass
class GateResult:
    """Outcome of screening one corpus."""

    path: Path
    examined: int = 0
    hits: list[Any] = field(default_factory=list)
    skipped: str | None = None

    @property
    def blocking(self) -> list[Any]:
        return [h for h in self.hits if h.rule_id in BLOCKING_RULES]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for hit in self.hits:
            out[hit.rule_id] = out.get(hit.rule_id, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def summary(self) -> str:
        if self.skipped:
            return f"{self.path.name}: gate not applied ({self.skipped})"
        counts = self.counts()
        if not counts:
            return f"{self.path.name}: no structural contradictions in {self.examined} records"
        rendered = ", ".join(f"{rule}={count}" for rule, count in counts.items())
        return f"{self.path.name}: {self.examined} records, {rendered}"


def _load_screen() -> ModuleType | None:
    """Import the screening tool by path, or None when it is unavailable."""
    if not SCREEN_PATH.exists():
        return None
    name = "decksage_screen_contradictions"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCREEN_PATH)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def screen_corpus(path: Path, *, metadata_dir: Path | None = None) -> GateResult:
    """Screen one annotation corpus, or skip when the tool or metadata is absent."""
    result = GateResult(path=path)
    module = _load_screen()
    if module is None:
        result.skipped = "screen_contradictions.py not found"
        return result
    if not path.exists():
        result.skipped = "corpus not found"
        return result
    lookup, _ledger = module.load_metadata(metadata_dir or METADATA_DIR)
    if not any(lookup.values()):
        result.skipped = "no card metadata under data/processed"
        return result
    records = [r for r in module.load_records(path) if not module.is_ineligible(r)]
    result.examined = len(records)
    result.hits = module.screen_records(records, lookup)
    return result


def gate_or_refuse(
    path: Path,
    *,
    allow: bool = False,
    metadata_dir: Path | None = None,
    blocked: list[GateResult] | None = None,
) -> GateResult:
    """Screen a corpus and raise when it carries blocking contradictions.

    ``allow`` records an explicit override; pass the same list as ``blocked``
    from the caller so the override can be logged with what it skipped.
    """
    refuse_if_superseded(path)
    result = screen_corpus(path, metadata_dir=metadata_dir)
    if result.blocking and not allow:
        rules = sorted({hit.rule_id for hit in result.blocking})
        examples = ", ".join(f"{h.card_a} vs {h.card_b}" for h in result.blocking[:3])
        raise ValueError(
            f"{path.name} carries {len(result.blocking)} structurally contradictory "
            f"judgments ({', '.join(rules)}); examples: {examples}. "
            "Repair the labels, or pass --allow-contradictions to score anyway."
        )
    if blocked is not None:
        blocked.append(result)
    return result


LEDGER_PATH = PROJECT_ROOT / "data" / "test_sets" / "REPAIR-LEDGER.json"


def superseded_hashes(ledger_path: Path | None = None) -> set[str]:
    """Hashes of files a repair replaced. Loading one means the repair was undone."""
    path = ledger_path or LEDGER_PATH
    if not path.exists():
        return set()
    try:
        ledger = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    hashes: set[str] = set()
    for game in ledger.get("games", []):
        # Only the replaced content is superseded. The repaired hash is what the
        # canonical file now *is*, so refusing it would refuse the fix.
        entry = game.get("original")
        if isinstance(entry, dict):
            value = entry.get("sha256")
            if isinstance(value, str) and len(value) == 64:
                hashes.add(value)
        for key in ("original_sha256", "source_sha256"):
            value = game.get(key)
            if isinstance(value, str) and len(value) == 64:
                hashes.add(value)
    return hashes


def refuse_if_superseded(path: Path, ledger_path: Path | None = None) -> None:
    """Refuse a file whose content is a set that a repair already replaced."""
    import hashlib

    superseded = superseded_hashes(ledger_path)
    if not superseded or not path.exists():
        return
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest in superseded:
        raise ValueError(
            f"{path.name} has the content of a set superseded on {LEDGER_PATH.name}. "
            "It carries judgments the gate removed; use the canonical file or quarantine this copy."
        )
