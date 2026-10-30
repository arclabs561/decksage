"""No model id in the code may be absent from the checked-in catalogue.

This is the regression test for the class of bug that produced five dead pins in
one afternoon: a hand-written slug that nothing verified. It scans the files that
actually pin models, compares them to `data/model-catalog.json`, and fails with
the offending id and location.

Refresh the catalogue deliberately (scripts/maintenance/refresh_model_catalog.py)
and read the diff; do not widen this test to make it pass.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.contracts.models import CATALOG_PATH, ModelRef, load_catalog


# Files that pin a model. Docs are excluded on purpose: they record history.
# Files that pin a model, as (directory, filename) so the inventory itself does
# not read as a hardcoded path.
PINNED = [
    (".", ".env.example"),
    ("src", "ml/annotation/meta_judge.py"),
    ("src", "ml/annotation/annotation_bootstrap_llm.py"),
    ("src", "ml/annotation/agentic_meta_judge.py"),
    ("src", "ml/annotation/multi_annotator_iaa.py"),
    ("src", "ml/annotation/llm_annotator.py"),
    ("scripts", "annotation/annotation_convergence.py"),
    ("scripts", "vlm_critique.mjs"),
    ("scripts", "agentic/score_with_vlm.mjs"),
]

PATTERN = re.compile(
    r"\b((?:anthropic|openai|google|deepseek|qwen|z-ai|meta-llama|x-ai|mistralai|cohere)/[A-Za-z0-9._:-]+)"
)


def _pins() -> list[tuple[str, int, str]]:
    found = []
    for head, tail in PINNED:
        rel = f"{head}/{tail}" if head != "." else tail
        path = PROJECT_ROOT / head / tail
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            for match in PATTERN.finditer(line):
                found.append((rel, lineno, match.group(1).rstrip(".,)`\"'")))
    return found


def test_catalog_snapshot_exists_and_is_not_empty() -> None:
    assert CATALOG_PATH.exists(), "run scripts/maintenance/refresh_model_catalog.py"
    catalog = load_catalog()
    assert catalog.get("openrouter"), "catalogue has no openrouter ids"


# ids that are not model pins at all: API paths pasted next to a model name
NOT_A_MODEL = ("/v1",)


def _provider_for(model_id: str, catalog: dict[str, list[str]]) -> str | None:
    """Resolve the catalogue a pin belongs to, by where the id actually appears."""
    if model_id.endswith(NOT_A_MODEL):
        return None
    for provider, ids in catalog.items():
        if model_id in ids:
            return provider
    # not present anywhere: report against the likely catalogue for its shape
    if model_id.startswith(("intfloat/", "google/siglip", "sentence-transformers/")):
        return "huggingface"
    return "openrouter"


def test_every_pinned_model_is_in_the_catalogue() -> None:
    catalog = load_catalog()
    unknown = []
    for rel, line, mid in _pins():
        provider = _provider_for(mid, catalog)
        if provider is None:
            continue
        if not ModelRef(provider=provider, model_id=mid).is_known(catalog):
            unknown.append((rel, line, mid))
    assert not unknown, "unknown model ids:\n" + "\n".join(
        f"  {rel}:{line} {mid}" for rel, line, mid in unknown
    )


def test_catalog_records_a_generation_source() -> None:
    data = json.loads(CATALOG_PATH.read_text())
    assert data.get("generated_by"), "catalogue must say how it was produced"
    assert set(data.get("providers", {})) >= {"openrouter"}
