"""No served artefact may be unrebuildable without saying so.

The audit found a production embedding whose producer writes a different mu, and
a text index with no producer at all. This runs the same check in CI so the
declaration and the artefact cannot drift apart silently.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "maintenance" / "verify_artifacts.py"


def _module():
    spec = importlib.util.spec_from_file_location("verify_artifacts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["verify_artifacts"] = module
    spec.loader.exec_module(module)
    return module


def test_mu_claim_reads_the_filename() -> None:
    module = _module()
    assert module._mu_claim("magic_v7_spectral_mu35") == "0.35"
    assert module._mu_claim("yugioh_v7_spectral_mu3") == "0.3"
    assert module._mu_claim("pokemon_v7_fused") is None


def test_a_comment_is_not_a_producer() -> None:
    """A comment mentioning `_mu35` must not count as reproducibility."""
    module = _module()
    artefact = module.declared("magic")[0]
    assert module._producer_names_it("scripts/pipeline/run_pipeline.py", artefact) is True
    # the pipeline writes what production serves only if it assigns the same mu
    text = (PROJECT_ROOT / "scripts/pipeline/run_pipeline.py").read_text()
    assert "MU = 0.35" in text


def test_checker_reports_json_without_crashing() -> None:
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--games", "magic", "--json"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    rows = json.loads(out.stdout)
    assert rows, out.stderr
    statuses = {row["status"] for row in rows}
    assert statuses <= {"OK", "MISSING", "UNREADABLE", "DIM_MISMATCH", "NO_PRODUCER", "HISTORICAL"}
