"""SUMMARY.md is derived: markers come from status fields, prose is preserved."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


GENERATOR_PATH = (
    Path(__file__).resolve().parent.parent / "scripts/validation/generate_experiment_summary.py"
)

SUMMARY = """\
# Experiment Summary

Chronological log of all ML/DS experiments.

## Experiments

| ID | Date | Title | Game | Data | Key Metric | Result | File |
|----|------|-------|------|------|------------|--------|------|
| 9997 | 2026-01-01 | stale row | all | -- | -- | -- | [9997](9997_stale.yaml) |

## Key Insights (cross-cutting)

1. Hand-written prose that the generator must not touch.
"""

RECORD = """\
id: "{record_id}"
date: "2026-03-19"
title: "{title}"
game: magic
hypothesis: "placeholder"
method:
  type: embedding
data:
  training:
    source: data/graphs/magic_merged_all.edg
    description: "Enriched edgelist, 331,264 edges"
results:
  overall_ndcg: 0.095
{extra}
conclusion: "placeholder"
"""


@pytest.fixture(scope="module")
def generator() -> Any:
    spec = importlib.util.spec_from_file_location("generate_experiment_summary", GENERATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_record(directory: Path, record_id: str, title: str, extra: str = "") -> Path:
    path = directory / f"{record_id}_{record_id}.yaml"
    path.write_text(RECORD.format(record_id=record_id, title=title, extra=extra))
    return path


def build_fixture(directory: Path) -> None:
    """One withdrawn record, one incomplete record, one plain record."""
    directory.mkdir(parents=True, exist_ok=True)
    write_record(
        directory,
        "0001",
        "Withdrawn",
        extra='validity:\n  status: invalid\n  reason: "leaked annotations"\n',
    )
    write_record(
        directory,
        "0002",
        "Unfinished",
        extra='  status: incomplete\n  reason: "the run never evaluated"\n',
    )
    write_record(directory, "0003", "Plain")
    (directory / "SUMMARY.md").write_text(SUMMARY)


def row_for(text: str, record_id: str) -> str:
    rows = [line for line in text.splitlines() if line.startswith(f"| {record_id} |")]
    assert len(rows) == 1, rows
    return rows[0]


def test_markers_are_derived_from_status(tmp_path: Path, generator: Any) -> None:
    build_fixture(tmp_path)
    assert generator.main(["--write", "--dir", str(tmp_path)]) == 0
    text = (tmp_path / "SUMMARY.md").read_text()

    withdrawn = row_for(text, "0001")
    assert withdrawn.endswith("| [invalid] [0001](0001_0001.yaml) |")
    assert "[incomplete]" not in withdrawn

    unfinished = row_for(text, "0002")
    cells = [cell.strip() for cell in unfinished.split("|")[1:-1]]
    assert cells[6].endswith(generator.INCOMPLETE_MARKER), cells[6]
    assert "[invalid]" not in unfinished

    plain = row_for(text, "0003")
    assert "[invalid]" not in plain
    assert "[incomplete]" not in plain


def test_superseded_record_is_marked_invalid(tmp_path: Path, generator: Any) -> None:
    build_fixture(tmp_path)
    write_record(
        tmp_path,
        "0004",
        "Superseded",
        extra='validity:\n  status: superseded\n  reason: "replaced by 0003"\n',
    )
    assert generator.main(["--write", "--dir", str(tmp_path)]) == 0
    assert row_for((tmp_path / "SUMMARY.md").read_text(), "0004").startswith(
        "| 0004 | 2026-03-19 | Superseded | magic |"
    )
    assert "| [invalid] [0004](0004_0004.yaml) |" in (tmp_path / "SUMMARY.md").read_text()


def test_prose_outside_the_table_is_preserved(tmp_path: Path, generator: Any) -> None:
    build_fixture(tmp_path)
    assert generator.main(["--write", "--dir", str(tmp_path)]) == 0
    text = (tmp_path / "SUMMARY.md").read_text()

    head = SUMMARY.split("| ID | Date |", 1)[0]
    assert text.startswith(head)
    assert text.endswith(
        "\n\n## Key Insights (cross-cutting)\n\n"
        "1. Hand-written prose that the generator must not touch.\n"
    )
    assert "| 9997 |" not in text  # the stale row was replaced, not appended to


def test_check_detects_drift_without_writing(
    tmp_path: Path, generator: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    build_fixture(tmp_path)
    assert generator.main(["--write", "--dir", str(tmp_path)]) == 0
    assert generator.main(["--check", "--dir", str(tmp_path)]) == 0

    record = tmp_path / "0003_0003.yaml"
    record.write_text(record.read_text().replace('title: "Plain"', 'title: "Renamed"'))

    assert generator.main(["--check", "--dir", str(tmp_path)]) == 1
    assert "| 0003 | 2026-03-19 | Renamed |" in capsys.readouterr().out
    # --check reports the difference but leaves the file alone.
    assert "| 0003 | 2026-03-19 | Plain |" in (tmp_path / "SUMMARY.md").read_text()
