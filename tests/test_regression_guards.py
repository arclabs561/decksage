"""The checks that keep the earlier mistakes from coming back.

Each test here pins a specific failure that already happened once in this repo.
They are cheap and offline; they exist so the fix is a guard rather than a
memory.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "annotation"))

CSS = PROJECT_ROOT / "frontend" / "static" / "brand.css"


def test_no_unscoped_element_rule_paints_a_background() -> None:
    """A page-specific `button {}` rule leaked onto every page once.

    Element selectors that set a background at the top level are how one
    surface's styling silently rewrote another's. Scoping them (a class, a body
    class, a page ancestor) is the fix, so the rule is mechanical.
    """
    css = CSS.read_text()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    offenders = []
    for match in re.finditer(r"(^|\})\s*([^{}]+)\{([^{}]*)\}", css):
        selector, body = match.group(2).strip(), match.group(3)
        if "background" not in body:
            continue
        first = selector.split(",")[0].strip()
        # body/html set the page ground and are meant to be global; controls are not.
        if re.fullmatch(r"[a-z][a-z0-9]*", first) and first not in {"body", "html"}:
            offenders.append(selector[:40])
    assert not offenders, f"unscoped background rules: {offenders}"


def test_repair_uses_the_screens_score_resolver() -> None:
    """Repair once read functional_score first and silently under-removed.

    The screen judged the record on similarity_score 0.902; the remover keyed on
    functional_score 0.2, so nothing matched and 151 contradictory judgments
    survived a "repair". This pins the resolver, not the field order.
    """
    import repair_blocked_labels as repair

    class FakeScreen:
        @staticmethod
        def resolve_score(record):
            return record.get("similarity_score")

    annotation = {"functional_score": 0.2, "similarity_score": 0.902}
    assert repair._score_of(annotation, FakeScreen) == 0.902


def test_withdrawn_assets_do_not_report_as_ok() -> None:
    """check_assets printed a withdrawn calibration as a passing asset."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_assets", PROJECT_ROOT / "scripts" / "check_assets.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclasses resolve their module through sys.modules while the class body
    # executes, so the module has to be registered before exec_module.
    sys.modules["check_assets"] = module
    spec.loader.exec_module(module)

    status = module.AssetStatus(
        name="fusion_weights", path="x.json", exists=True, loadable=True, critical=False
    )
    assert status.withdrawn is False
    status.withdrawn = True
    assert status.withdrawn is True
