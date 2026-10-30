"""Model identities, checked instead of remembered.

Every dead-model bug in this repo had the same shape: a string that looked like
a model id, written by hand, never checked. The fix is not care, it is a
checked-in catalogue plus one gate that reads it, so a stale pin fails a test
rather than a request at 2am.

The catalogue is a snapshot, not a live query: tests must run offline and be
deterministic. Refresh it with `scripts/maintenance/refresh_model_catalog.py`
and commit the diff; the diff is the review.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "model-catalog.json"

# Ids that are not served by an API catalogue: local engines and files, not pins.
NON_API_PREFIXES = ("local/", "file/")


class UnknownModelError(ValueError):
    """A model id that the checked-in catalogue does not know."""


@dataclass(frozen=True)
class ModelRef:
    """A model id together with the provider catalogue that must contain it."""

    provider: str
    model_id: str

    def is_known(self, catalog: dict[str, list[str]] | None = None) -> bool:
        if self.model_id.startswith(NON_API_PREFIXES):
            return True
        catalog = catalog if catalog is not None else load_catalog()
        return self.model_id in set(catalog.get(self.provider, []))


def load_catalog(path: Path | None = None) -> dict[str, list[str]]:
    """Provider -> ids. The file nests them under "providers"; callers get the map."""
    target = path or CATALOG_PATH
    if not target.exists():
        return {}
    data = json.loads(target.read_text())
    providers = data.get("providers", data)
    return {k: v for k, v in providers.items() if isinstance(v, list)}


def require_known(model_id: str, provider: str, catalog: dict[str, list[str]] | None = None) -> str:
    """Return the id, or raise with the provider and what to do about it."""
    ref = ModelRef(provider=provider, model_id=model_id)
    if not ref.is_known(catalog):
        raise UnknownModelError(
            f"{model_id!r} is not in the {provider} catalogue snapshot. "
            "Refresh it with scripts/maintenance/refresh_model_catalog.py and check the diff."
        )
    return model_id
