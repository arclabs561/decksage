#!/usr/bin/env python3
"""Refresh `data/model-catalog.json` from the providers the repo actually uses.

Run deliberately, then read the diff: ids that disappeared are pins that would
have failed in production, and ids that appeared are the replacements you can
move to. Tests read the snapshot, never the network.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG = PROJECT_ROOT / "data" / "model-catalog.json"
HF_MODELS = (
    "intfloat/e5-base-v2",
    "google/siglip-base-patch16-224",
    "google/siglip2-so400m-patch14-384",
)


DEFAULT_HEADERS = {
    "User-Agent": "decksage-model-catalog/1 (+https://github.com/arclabs561/decksage)"
}


def fetch_json(url: str, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(url, headers={**DEFAULT_HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def openrouter_ids() -> list[str]:
    data = fetch_json("https://openrouter.ai/api/v1/models")
    return sorted(m["id"] for m in data["data"])


def groq_ids(api_key: str) -> list[str]:
    if not api_key:
        return []
    data = fetch_json(
        "https://api.groq.com/openai/v1/models",
        {"Authorization": f"Bearer {api_key}"},
    )
    return sorted(m["id"] for m in data.get("data", []))


def hf_exists(model_id: str) -> bool:
    try:
        req = urllib.request.Request(
            f"https://huggingface.co/api/models/{model_id}", headers=DEFAULT_HEADERS
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> int:
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        env = PROJECT_ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("GROQ_API_KEY="):
                    groq_key = line.split("=", 1)[1].strip()

    catalog = {
        "generated_by": "scripts/maintenance/refresh_model_catalog.py",
        "providers": {
            "openrouter": openrouter_ids(),
            "groq": groq_ids(groq_key),
            "huggingface": [m for m in HF_MODELS if hf_exists(m)],
        },
    }
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps(catalog, indent=1) + "\n")
    counts = {k: len(v) for k, v in catalog["providers"].items()}
    print("wrote", CATALOG.relative_to(PROJECT_ROOT), counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
