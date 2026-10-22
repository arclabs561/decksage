#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Validate experiment log YAML files against the documented schema.

Schema reference: data/experiments/README.md

Rules:
  1. Required top-level keys: id, date, title, game, hypothesis, method,
     data, results, conclusion. None may be empty.
  2. `data` must be a non-empty mapping (provenance is mandatory).
  3. `results` must be a mapping; the literal string "not recorded" is
     accepted for an experiment whose metrics were never recorded.
  4. `conclusion` must be non-empty (the "so what" is mandatory).
  5. `id` must match the filename prefix (`0007_foo.yaml` -> id "0007").
  6. An experiment marked `results.status: incomplete` must carry a
     non-empty `results.reason`, so gaps are explicit instead of implied.

Usage:
    scripts/validation/check_experiment_schema.py            # data/experiments/
    scripts/validation/check_experiment_schema.py path/*.yaml
    scripts/validation/check_experiment_schema.py --json     # machine readable

Exit status: 0 when clean, 1 when any violation is found.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


try:
    import yaml
except ImportError:  # pragma: no cover - dependency is declared above
    sys.stderr.write("error: PyYAML is required (run via `uv run python` or install pyyaml)\n")
    raise SystemExit(2) from None


DEFAULT_DIR = Path("data/experiments")
REQUIRED_KEYS = (
    "id",
    "date",
    "title",
    "game",
    "hypothesis",
    "method",
    "data",
    "results",
    "conclusion",
)
NOT_RECORDED = "not recorded"
INCOMPLETE = "incomplete"
FILENAME_PREFIX = re.compile(r"^(\d{4})_")


def is_empty(value: Any) -> bool:
    """Return True when a value is absent, blank, or an empty container."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, dict | list | tuple):
        return len(value) == 0
    return False


def prefix_from_path(path: Path) -> str | None:
    """Return the numeric filename prefix used as the experiment id."""
    match = FILENAME_PREFIX.match(path.name)
    return match.group(1) if match else None


def validate_document(data: Any, path: Path) -> list[tuple[str, str]]:
    """Return (field, problem) pairs for one parsed experiment file."""
    if not isinstance(data, dict):
        return [("document", "top-level YAML must be a mapping")]

    violations: list[tuple[str, str]] = []

    for key in REQUIRED_KEYS:
        if key not in data:
            violations.append((key, "missing required key"))
        elif key != "results" and is_empty(data[key]):
            violations.append((key, "must not be empty"))

    expected = prefix_from_path(path)
    actual_id = data.get("id")
    if actual_id is not None and not is_empty(actual_id):
        if expected is None:
            violations.append(("id", "filename has no NNNN_ prefix to match"))
        elif str(actual_id).strip() != expected:
            violations.append(("id", f"'{actual_id}' does not match filename prefix '{expected}'"))

    if "data" in data and not is_empty(data["data"]):
        if not isinstance(data["data"], dict):
            violations.append(("data", "must be a mapping, not a scalar or list"))

    results = data.get("results")
    if "results" in data and not is_empty(results):
        if isinstance(results, str):
            if results.strip().lower() != NOT_RECORDED:
                violations.append(("results", f"string form is only allowed as '{NOT_RECORDED}'"))
        elif not isinstance(results, dict):
            violations.append(("results", "must be a mapping"))
        else:
            status = results.get("status")
            if isinstance(status, str) and status.strip().lower() == INCOMPLETE:
                if is_empty(results.get("reason")):
                    violations.append(("results.reason", f"required when status is '{INCOMPLETE}'"))

    return violations


def validate_paths(paths: list[Path]) -> tuple[list[dict[str, str]], int]:
    """Validate every path; return (violations, files_checked)."""
    violations: list[dict[str, str]] = []
    checked = 0

    for path in paths:
        checked += 1
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problem = " ".join(str(exc).split())
            violations.append(
                {"file": str(path), "field": "yaml", "problem": f"parse error: {problem}"}
            )
            continue
        except OSError as exc:
            violations.append({"file": str(path), "field": "file", "problem": f"unreadable: {exc}"})
            continue

        for field, problem in validate_document(data, path):
            violations.append({"file": str(path), "field": field, "problem": problem})

    return violations, checked


def collect_paths(args: list[str]) -> list[Path]:
    """Resolve CLI arguments to experiment YAML files, sorted."""
    if not args:
        return sorted(DEFAULT_DIR.glob("*.yaml"))

    paths: list[Path] = []
    for raw in args:
        path = Path(raw)
        if path.is_dir():
            paths.extend(sorted(path.glob("*.yaml")))
        else:
            paths.append(path)
    return sorted(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate experiment log YAML files against the documented schema."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=f"YAML files or directories (default: {DEFAULT_DIR})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit machine-readable JSON instead of one line per violation",
    )
    options = parser.parse_args(argv)

    paths = collect_paths(options.paths)
    if not paths:
        sys.stderr.write(f"error: no YAML files found in {options.paths or DEFAULT_DIR}\n")
        return 2

    violations, checked = validate_paths(paths)

    if options.as_json:
        json.dump(
            {
                "files_checked": checked,
                "ok": not violations,
                "violation_count": len(violations),
                "violations": violations,
            },
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
    else:
        for item in violations:
            print(f"{item['file']}: {item['field']}: {item['problem']}")
        sys.stderr.write(
            f"{'FAIL' if violations else 'OK'}: {checked} file(s) checked, "
            f"{len(violations)} violation(s)\n"
        )

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
