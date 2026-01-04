#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
# "pyyaml>=6.0",
# ]
# ///
"""
Retrofit existing annotations with downstream task fields.

Adds new fields to existing hand annotations:
- similarity_type
- is_substitute
- role_match
- archetype_context
- format_context
- substitution_quality

Uses heuristics and LLM inference to populate fields.
"""

from __future__ import annotations

import argparse
from pathlib import Path


try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("Install pyyaml: pip install pyyaml")

import sys


script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def infer_similarity_type(
    relevance: int, notes: str, query_context: dict, cand_context: dict
) -> str | None:
    """Infer similarity_type from relevance and context."""
    if relevance is None:
        return None

    rel_int = int(relevance) if isinstance(relevance, (int, str)) else 0

    # High relevance (3-4) likely functional
    if rel_int >= 3:
        notes_lower = notes.lower() if notes else ""
        if (
            "substitute" in notes_lower
            or "replace" in notes_lower
            or "same function" in notes_lower
        ):
            return "functional"
        elif "synergy" in notes_lower or "combo" in notes_lower or "work together" in notes_lower:
            return "synergy"
        elif "archetype" in notes_lower or "deck" in notes_lower:
            return "archetype"
        else:
            return "functional"  # Default for high relevance

    # Medium relevance (2) could be synergy or archetype
    elif rel_int == 2:
        notes_lower = notes.lower() if notes else ""
        if "synergy" in notes_lower or "combo" in notes_lower:
            return "synergy"
        elif "archetype" in notes_lower:
            return "archetype"
        else:
            return "archetype"  # Default for medium relevance

    # Low relevance (0-1) likely unrelated
    else:
        return "unrelated"


def infer_is_substitute(relevance: int, similarity_type: str | None, notes: str) -> bool | None:
    """Infer is_substitute from relevance and similarity_type."""
    if relevance is None:
        return None

    rel_int = int(relevance) if isinstance(relevance, (int, str)) else 0

    # High relevance (4) with functional type likely substitutable
    if rel_int == 4:
        if similarity_type == "functional":
            return True
        notes_lower = notes.lower() if notes else ""
        if "substitute" in notes_lower or "replace" in notes_lower:
            return True
        return None  # Uncertain

    # Lower relevance unlikely to be substitutable
    elif rel_int >= 3:
        notes_lower = notes.lower() if notes else ""
        if "substitute" in notes_lower or "replace" in notes_lower:
            return True
        return False

    else:
        return False


def infer_role_match(
    similarity_type: str | None, query_context: dict, cand_context: dict
) -> bool | None:
    """Infer role_match from similarity_type and card contexts."""
    if similarity_type == "functional":
        return True
    elif similarity_type == "synergy" or similarity_type == "unrelated":
        return False
    else:
        return None


def retrofit_annotation_batch(input_path: Path, output_path: Path | None = None) -> Path:
    """Retrofit existing annotation batch with downstream fields."""
    if not HAS_YAML:
        raise ImportError("PyYAML required")

    if not input_path.exists():
        raise FileNotFoundError(f"Annotation file not found: {input_path}")

    with open(input_path) as f:
        data = yaml.safe_load(f)

    tasks = data.get("tasks", [])
    retrofitted = 0

    for task in tasks:
        query_context = task.get("query_context", {})
        candidates = task.get("candidates", [])

        for cand in candidates:
            # Skip if already has all fields
            if all(
                cand.get(field) is not None
                for field in ["similarity_type", "is_substitute", "role_match"]
            ):
                continue

            relevance = cand.get("relevance")
            notes = cand.get("notes", "")
            cand_context = cand.get("context", {})

            # Infer fields
            if cand.get("similarity_type") is None:
                cand["similarity_type"] = infer_similarity_type(
                    relevance, notes, query_context, cand_context
                )
                retrofitted += 1

            if cand.get("is_substitute") is None:
                cand["is_substitute"] = infer_is_substitute(
                    relevance, cand.get("similarity_type"), notes
                )
                retrofitted += 1

            if cand.get("role_match") is None:
                cand["role_match"] = infer_role_match(
                    cand.get("similarity_type"), query_context, cand_context
                )
                retrofitted += 1

            # Set defaults for optional fields if not present
            if cand.get("archetype_context") is None:
                cand["archetype_context"] = None
            if cand.get("format_context") is None:
                cand["format_context"] = None
            if cand.get("substitution_quality") is None:
                cand["substitution_quality"] = None

    # Write retrofitted batch
    output_file = output_path or input_path.with_suffix(".retrofitted.yaml")
    with open(output_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    print(f"✓ Retrofitted {retrofitted} candidate fields")
    print(f" Saved to: {output_file}")

    return output_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrofit annotations with downstream fields")
    parser.add_argument("--input", type=str, required=True, help="Input annotation YAML file")
    parser.add_argument(
        "--output", type=str, help="Output YAML file (default: input.retrofitted.yaml)"
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else None

    try:
        retrofit_annotation_batch(input_path, output_path)
        return 0
    except Exception as e:
        print(f"Error: Error: {e}")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
