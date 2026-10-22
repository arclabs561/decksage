#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Render the experiment table in `data/experiments/SUMMARY.md` from the YAML records.

The table is derived, not hand-maintained: one row per `NNNN_*.yaml` record,
sorted by id. The generator owns only the table block (the header, the
separator, and the `| 0001 | ...` rows). Every other byte of SUMMARY.md --
title, intro sentence, `## Key Insights`, the `## CORRECTION` history --
is copied through untouched.

Cell sources, in priority order:

  1. `summary.title|data|metric|result` in the record (the record's own
     one-line projection; the display text is editorial and lives with the
     experiment, not in the index).
  2. Best-effort derivation from `title`/`data`/`results` when a record has no
     `summary` block, so a brand-new record still produces a usable row.

Markers are computed, never authored:

  * `[invalid]` is prefixed to the File cell (before the link) when
    `validity.status` is `invalid` or `superseded` -- the placement
    `data/experiments/README.md#validity` specifies.
  * `**[incomplete]**` is appended to the Result cell when `results.status` is
    `incomplete` (the schema check requires a `results.reason` alongside it).

Usage:
    scripts/validation/generate_experiment_summary.py --check
    scripts/validation/generate_experiment_summary.py --write
    scripts/validation/generate_experiment_summary.py --check --dir path/to/experiments

Exit status: 0 when in sync (or after a successful --write), 1 when --check
finds a difference or when the records are unusable, 2 on bad usage.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path
from typing import Any


try:
    import yaml
except ImportError:  # pragma: no cover - dependency is declared above
    sys.stderr.write("error: PyYAML is required (run via `uv run python` or install pyyaml)\n")
    raise SystemExit(2) from None


DEFAULT_DIR = Path("data/experiments")
SUMMARY_NAME = "SUMMARY.md"
HEADER = "| ID | Date | Title | Game | Data | Key Metric | Result | File |"
SEPARATOR = "|----|------|-------|------|------|------------|--------|------|"

INVALID_MARKER = "[invalid]"
INCOMPLETE_MARKER = "**[incomplete]**"
WITHDRAWN_STATUSES = {"invalid", "superseded"}
INCOMPLETE_STATUS = "incomplete"

GAME_ABBREVIATIONS = {"magic": "M", "pokemon": "P", "yugioh": "Y"}
GAME_KEYS = tuple(GAME_ABBREVIATIONS)
# The metric a per-game results map is summarised by, best first.
PRIMARY_METRICS = ("overall_ndcg", "sub_ndcg", "substitute_ndcg", "condensed_ndcg", "auc")
METRIC_LABELS = {
    "overall_ndcg": "overall nDCG",
    "sub_ndcg": "sub nDCG",
    "substitute_ndcg": "sub nDCG",
    "condensed_ndcg": "condensed nDCG",
    "auc": "AUC",
    "pearson": "Pearson",
    "hit_at_10": "hit@10",
}
# Words used to name the unit of a count when the description does not say.
COUNT_UNITS = ("pairs", "edges", "queries", "decks", "triples", "cards", "samples", "annotations")


class SummaryError(Exception):
    """A record or the summary file cannot be rendered."""


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


def load_records(directory: Path) -> list[dict[str, Any]]:
    """Load every `*.yaml` record in `directory`, sorted by id."""
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise SummaryError(f"{path}: parse error: {' '.join(str(exc).split())}") from None
        if not isinstance(document, dict):
            raise SummaryError(f"{path}: top-level YAML must be a mapping")
        record_id = document.get("id")
        if record_id is None or not str(record_id).strip():
            raise SummaryError(f"{path}: missing required `id`")
        document["_path"] = path
        document["_id"] = str(record_id).strip()
        records.append(document)

    records.sort(key=lambda record: record["_id"])
    seen: set[str] = set()
    for record in records:
        if record["_id"] in seen:
            raise SummaryError(f"{record['_path']}: duplicate id {record['_id']}")
        seen.add(record["_id"])
    return records


def summary_block(record: dict[str, Any]) -> dict[str, Any]:
    """Return the record's `summary` projection (empty when absent)."""
    block = record.get("summary")
    if block is None:
        return {}
    if not isinstance(block, dict):
        raise SummaryError(f"{record['_path']}: `summary` must be a mapping")
    return block


def is_withdrawn(record: dict[str, Any]) -> bool:
    """True when `validity.status` withdraws the recorded numbers."""
    validity = record.get("validity")
    if not isinstance(validity, dict):
        return False
    return str(validity.get("status", "")).strip().lower() in WITHDRAWN_STATUSES


def is_incomplete(record: dict[str, Any]) -> bool:
    """True when `results.status` says the measurement never finished."""
    results = record.get("results")
    if not isinstance(results, dict):
        return False
    return str(results.get("status", "")).strip().lower() == INCOMPLETE_STATUS


# --------------------------------------------------------------------------- #
# Cell formatting
# --------------------------------------------------------------------------- #


def compact_number(value: Any) -> str:
    """Compact a count the way the table reads: 7111569 -> `7.1M`."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return str(value).strip()
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,}"
    number = int(value)
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if abs(number) >= 10_000:
        return f"{number / 1_000:.1f}K"
    return f"{number:,}"


def compact_value(value: Any) -> str:
    """Render a measured value verbatim, compacting only bare integers."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return f"{value:,}" if abs(value) >= 100_000 else str(value)
    return str(value).strip()


def is_game_map(mapping: Any) -> bool:
    """True when the mapping is keyed only by the known games."""
    return (
        isinstance(mapping, dict)
        and bool(mapping)
        and all(str(key).strip().lower() in GAME_ABBREVIATIONS for key in mapping)
    )


def format_game_map(mapping: dict[str, Any], formatter) -> str:
    """Render `{magic: x, pokemon: y, yugioh: z}` as `M:x P:y Y:z`."""
    parts = []
    for key in GAME_KEYS:
        for actual, value in mapping.items():
            if str(actual).strip().lower() == key:
                parts.append(f"{GAME_ABBREVIATIONS[key]}:{formatter(value)}")
    return " ".join(parts)


def unit_from(block: dict[str, Any]) -> str:
    """Guess the counted thing from a data block's description."""
    text = " ".join(str(block.get(key, "")) for key in ("description", "source")).lower()
    for unit in COUNT_UNITS:
        if unit in text:
            return unit
    return ""


def derive_data_cell(record: dict[str, Any]) -> str:
    """Best-effort Data cell from the record's `data` block."""
    data = record.get("data")
    if isinstance(data, str):
        return data.strip()
    if not isinstance(data, dict) or not data:
        return "--"

    for block in data.values():
        if not isinstance(block, dict) or "count" not in block:
            continue
        count = block["count"]
        unit = unit_from(block)
        if isinstance(count, dict):
            rendered = format_game_map(count, compact_number)
            if rendered:
                return f"{rendered} {unit}".strip()
            return ", ".join(f"{key} {compact_number(value)}" for key, value in count.items())
        if count is None or str(count).strip().lower() == "not recorded":
            continue
        text = f"{compact_number(count)} {unit}".strip()
        if "previous_count" in block:
            text += f" (from {compact_number(block['previous_count'])})"
        return text

    for block in data.values():
        if isinstance(block, dict):
            description = block.get("description")
            if description:
                return " ".join(str(description).split())
            source = block.get("source")
            if source:
                return str(source).strip()
        elif isinstance(block, str | int):
            return str(block).strip()
    return "--"


def derive_metric_cell(record: dict[str, Any]) -> str:
    """Best-effort Key Metric cell: the metric the results are summarised by."""
    results = record.get("results")
    if not isinstance(results, dict):
        return "--"
    for metric in PRIMARY_METRICS:
        if metric in results:
            return METRIC_LABELS.get(metric, metric)
        for value in results.values():
            if isinstance(value, dict) and metric in value:
                return METRIC_LABELS.get(metric, metric)
    return "--"


def derive_result_cell(record: dict[str, Any]) -> str:
    """Best-effort Result cell from `results`, strings preserved verbatim."""
    results = record.get("results")
    if isinstance(results, str):
        return " ".join(results.split())
    if not isinstance(results, dict) or not results:
        return "--"

    if is_incomplete(record):
        reason = results.get("reason")
        if reason:
            return " ".join(str(reason).split())

    if is_game_map(results):
        for metric in PRIMARY_METRICS:
            if all(isinstance(value, dict) and metric in value for value in results.values()):
                return format_game_map(
                    results, lambda value, metric=metric: compact_value(value[metric])
                )

    flat = []
    for key, value in results.items():
        if key in {"status", "reason"}:
            continue
        if isinstance(value, dict | list):
            continue
        flat.append(f"{key} {compact_value(value)}")
    return "; ".join(flat) if flat else "--"


def cell(record: dict[str, Any], field: str) -> str:
    """Return a cell: the record's `summary` projection, else a derived value."""
    override = summary_block(record).get(field)
    if override is not None and str(override).strip():
        return " ".join(str(override).split())
    derived = {
        "title": lambda r: str(r.get("title", "")).strip(),
        "data": derive_data_cell,
        "metric": derive_metric_cell,
        "result": derive_result_cell,
    }[field](record)
    return " ".join(derived.split())


def escape_cell(text: str) -> str:
    """Keep a value from breaking the table layout."""
    if "\n" in text:
        raise SummaryError(f"newline inside a table cell: {text!r}")
    return text.replace("|", "\\|")


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def render_row(record: dict[str, Any]) -> str:
    """Render one table row, markers computed from the record's status fields."""
    record_id = record["_id"]
    result = cell(record, "result")
    if is_incomplete(record) and INCOMPLETE_MARKER not in result:
        result = f"{result} {INCOMPLETE_MARKER}".strip()

    link = f"[{record_id}]({record['_path'].name})"
    file_cell = f"{INVALID_MARKER} {link}" if is_withdrawn(record) else link

    columns = [
        record_id,
        record.get("date"),
        cell(record, "title"),
        record.get("game"),
        cell(record, "data"),
        cell(record, "metric"),
        result,
        file_cell,
    ]
    rendered = [escape_cell("" if value is None else str(value).strip()) for value in columns]
    return "| " + " | ".join(rendered) + " |"


def table_bounds(lines: list[str]) -> tuple[int, int]:
    """Return [start, end) line indices of the existing table block."""
    start = None
    for index, line in enumerate(lines):
        if line.lstrip().startswith("| ID |"):
            start = index
            break
    if start is None:
        raise SummaryError("no table found (expected a `| ID | Date | Title | ...` row)")
    end = start
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    return start, end


def render_summary(text: str, records: list[dict[str, Any]]) -> str:
    """Return `text` with its experiment table replaced by the generated one."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    start, end = table_bounds(lines)

    table = [HEADER + newline, SEPARATOR + newline]
    table.extend(render_row(record) + newline for record in records)

    # Keep the blank line that separates the table from the prose below it.
    tail = lines[end:]
    if tail and not tail[0].strip():
        table.append(tail[0])
        tail = tail[1:]
    if tail and not table[-1].endswith(("\n", "\r\n")):
        table[-1] += newline
    return "".join(lines[:start] + table + tail)


def unified_diff(path: Path, current: str, generated: str) -> str:
    """Unified diff from what is on disk to what the records say it should be."""
    return "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            generated.splitlines(keepends=True),
            fromfile=f"{path} (on disk)",
            tofile=f"{path} (generated)",
        )
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the experiment table in data/experiments/SUMMARY.md from its YAML records.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="exit 1 (printing a unified diff) when SUMMARY.md differs from the records",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="rewrite the table in SUMMARY.md from the records",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help=f"experiment directory (default: {DEFAULT_DIR})",
    )
    options = parser.parse_args(argv)

    summary_path = options.dir / SUMMARY_NAME
    try:
        records = load_records(options.dir)
        if not records:
            raise SummaryError(f"no *.yaml records found in {options.dir}")
        current = summary_path.read_text(encoding="utf-8")
        generated = render_summary(current, records)
    except (SummaryError, OSError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    if options.write:
        if generated != current:
            summary_path.write_text(generated, encoding="utf-8")
            print(f"OK: rewrote {summary_path} from {len(records)} record(s)")
        else:
            print(f"OK: {summary_path} already current ({len(records)} record(s))")
        return 0

    if generated != current:
        sys.stdout.write(unified_diff(summary_path, current, generated))
        sys.stderr.write(
            f"FAIL: {summary_path} is out of date with {len(records)} record(s); "
            "run `scripts/validation/generate_experiment_summary.py --write`\n"
        )
        return 1

    print(f"OK: {summary_path} matches {len(records)} record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
