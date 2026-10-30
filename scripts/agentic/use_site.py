#!/usr/bin/env python3
"""An agent walks the running site, takes dated notes, and leaves evidence.

This is the "agentic experience" loop: not a unit test and not a VLM critic, but
a scripted user that performs the journeys the product is for, records what the
browser actually did, and writes a session note a human or agent can act on.

Usage:
    uv run python scripts/agentic/use_site.py --base http://127.0.0.1:8000
    uv run python scripts/agentic/use_site.py --base ... --label after-nav-fix

Outputs (never overwrites a previous session):
    .agents/reports/agentic-sessions/<date>-<label>.md    notes, findings
    .agents/reports/agentic-sessions/<date>-<label>.json  machine record
    .agents/reports/agentic-sessions/<date>-<label>/      screenshots

Each finding carries a severity, the journey step, the evidence file and the
selector or visible text it came from, so a later session can mark it fixed
rather than re-derive it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = PROJECT_ROOT / ".agents" / "reports" / "agentic-sessions"
DEFAULT_CHROME = (
    "/Users/arc/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
)


@dataclass
class Finding:
    severity: str
    step: str
    what: str
    evidence: str
    fix: str = ""


@dataclass
class Session:
    base: str
    label: str
    steps: list[dict] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)

    def note(self, step: str, **data) -> None:
        self.steps.append({"step": step, "t_ms": int(time.time() * 1000), **data})


def audit_dom(page) -> dict:
    """Facts a person feels but would not measure."""
    return page.evaluate(
        """() => {
      const vis = el => {
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
      };
      const controls = Array.from(document.querySelectorAll('button, a, input, select, textarea')).filter(vis);
      const small = controls
        .map(el => ({ t: (el.textContent || el.getAttribute('aria-label') || el.tagName).trim().slice(0, 40),
                      w: Math.round(el.getBoundingClientRect().width),
                      h: Math.round(el.getBoundingClientRect().height) }))
        .filter(c => c.h < 44 || c.w < 44);
      const overflowX = document.documentElement.scrollWidth > window.innerWidth + 1;
      const navTabs = Array.from(document.querySelectorAll('.nav-tab'))
        .map(b => ({ label: b.textContent.trim(), selected: b.getAttribute('aria-selected'),
                     bg: getComputedStyle(b).backgroundColor }));
      const selectedGames = Array.from(document.querySelectorAll('.game-btn[aria-checked="true"]'))
        .map(b => b.textContent.trim());
      return {
        title: document.title,
        controls: controls.length,
        small_controls: small.slice(0, 8),
        small_control_count: small.length,
        overflow_x: overflowX,
        nav_tabs: navTabs,
        selected_games: selectedGames,
        h1: (document.querySelector('h1')?.textContent || '').trim(),
        body_chars: document.body.innerText.replace(/\\s+/g, ' ').trim().length,
      };
    }"""
    )


def run(base: str, label: str, chrome: str, headed: bool) -> Session:
    from playwright.sync_api import sync_playwright

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    out_dir = OUT_ROOT / f"{stamp}-{label}"
    shots = out_dir
    shots.mkdir(parents=True, exist_ok=True)
    session = Session(base=base, label=label)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome, headless=not headed)

        def new_page(mobile: bool):
            pg = browser.new_page(
                viewport={"width": 390, "height": 844}
                if mobile
                else {"width": 1440, "height": 900},
                is_mobile=mobile,
                has_touch=mobile,
                device_scale_factor=2 if mobile else 1,
            )
            pg.on(
                "console",
                lambda m: (
                    session.console_errors.append(m.text[:200]) if m.type == "error" else None
                ),
            )
            pg.on(
                "pageerror", lambda e: session.console_errors.append(f"pageerror: {str(e)[:200]}")
            )
            return pg

        def shot(pg, name: str) -> str:
            path = shots / f"{name}.png"
            pg.screenshot(path=str(path))
            return str(path.relative_to(PROJECT_ROOT))

        # ---- journey 1: land and search by name (phone)
        pg = new_page(True)
        t0 = time.time()
        pg.goto(base + "/", wait_until="domcontentloaded")
        pg.wait_for_timeout(900)
        session.note(
            "land-phone",
            load_ms=int((time.time() - t0) * 1000),
            dom=audit_dom(pg),
            shot=shot(pg, "01-land-phone"),
        )
        dom = session.steps[-1]["dom"]
        if dom["overflow_x"]:
            session.findings.append(
                Finding(
                    "high",
                    "land-phone",
                    "page scrolls horizontally",
                    session.steps[-1]["shot"],
                    "constrain width",
                )
            )
        if len(dom["selected_games"]) != 1:
            session.findings.append(
                Finding(
                    "blocker",
                    "land-phone",
                    f"{len(dom['selected_games'])} games read as selected: {dom['selected_games']}",
                    session.steps[-1]["shot"],
                    "one selected state",
                )
            )
        active = [t for t in dom["nav_tabs"] if t["selected"] == "true"]
        if len(active) != 1:
            session.findings.append(
                Finding(
                    "high",
                    "land-phone",
                    f"{len(active)} tabs read as active",
                    session.steps[-1]["shot"],
                    "clear previous selection",
                )
            )
        if dom["small_control_count"]:
            session.findings.append(
                Finding(
                    "medium",
                    "land-phone",
                    f"{dom['small_control_count']} controls under 44px",
                    session.steps[-1]["shot"],
                    "raise tap targets",
                )
            )

        t0 = time.time()
        pg.fill("#unifiedInput", "Lightning Bolt")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(3500)
        session.note(
            "search-name-phone",
            ms=int((time.time() - t0) * 1000),
            dom=audit_dom(pg),
            shot=shot(pg, "02-results-phone"),
        )
        text = pg.inner_text("#resultsContainer")
        if "timed out" in text.lower():
            session.findings.append(
                Finding(
                    "blocker",
                    "search-name-phone",
                    "error text shown after a good search",
                    session.steps[-1]["shot"],
                    "treat superseded aborts as cancellation",
                )
            )
        if "Lightning Bolt" not in text:
            session.findings.append(
                Finding(
                    "blocker",
                    "search-name-phone",
                    "results do not name the query card",
                    session.steps[-1]["shot"],
                    "render query context",
                )
            )

        # ---- journey 2: describe an effect, not a name
        pg2 = new_page(True)
        pg2.goto(base + "/", wait_until="domcontentloaded")
        pg2.wait_for_timeout(700)
        t0 = time.time()
        pg2.fill("#unifiedInput", "draw two cards")
        pg2.keyboard.press("Enter")
        pg2.wait_for_timeout(6000)
        body = pg2.inner_text("body")
        session.note(
            "search-description-phone",
            ms=int((time.time() - t0) * 1000),
            dom=audit_dom(pg2),
            shot=shot(pg2, "03-description-phone"),
        )
        if "no cards found" in body.lower():
            session.findings.append(
                Finding(
                    "high",
                    "search-description-phone",
                    "description query returns nothing",
                    session.steps[-1]["shot"],
                    "check the hybrid path",
                )
            )

        # ---- journey 3: deck building from a card you just searched
        pg.click("#deck-tab-btn")
        pg.wait_for_timeout(900)
        seeds = pg.query_selector_all("#deckQuickStart .ds-starter")
        session.note(
            "deck-tab-phone",
            seed_chips=len(seeds),
            dom=audit_dom(pg),
            shot=shot(pg, "04-deck-phone"),
        )
        if not seeds:
            session.findings.append(
                Finding(
                    "high",
                    "deck-tab-phone",
                    "no build-around seeds offered",
                    session.steps[-1]["shot"],
                    "seed from the last search",
                )
            )
        else:
            t0 = time.time()
            seeds[0].click()
            pg.wait_for_timeout(8000)
            built = pg.inner_text("#deckResultsContainer")
            session.note(
                "build-deck-phone",
                ms=int((time.time() - t0) * 1000),
                chars=len(built),
                shot=shot(pg, "05-deck-built-phone"),
            )
            if len(built.strip()) < 40:
                session.findings.append(
                    Finding(
                        "blocker",
                        "build-deck-phone",
                        "build-around produced no deck",
                        session.steps[-1]["shot"],
                        "check /v1/deck/complete",
                    )
                )

        # ---- journey 4: desktop review surface
        d = new_page(False)
        t0 = time.time()
        d.goto(base + "/review_similarities.html", wait_until="domcontentloaded")
        d.wait_for_timeout(1200)
        session.note(
            "review-desktop",
            ms=int((time.time() - t0) * 1000),
            dom=audit_dom(d),
            shot=shot(d, "06-review-desktop"),
        )
        if d.query_selector(".ds-review-empty") is None:
            session.findings.append(
                Finding(
                    "medium",
                    "review-desktop",
                    "no empty state explaining what to do",
                    session.steps[-1]["shot"],
                    "add guidance",
                )
            )

        browser.close()

    session.note("console", errors=session.console_errors[:10])
    write_notes(session, out_dir, stamp)
    return session


def write_notes(session: Session, out_dir: Path, stamp: str) -> None:
    json_path = out_dir.with_suffix(".json")
    md_path = out_dir.with_suffix(".md")
    json_path.write_text(
        json.dumps(
            {
                "base": session.base,
                "label": session.label,
                "steps": session.steps,
                "findings": [f.__dict__ for f in session.findings],
                "console_errors": session.console_errors,
            },
            indent=2,
        )
        + "\n"
    )

    lines = [
        f"# Agentic session: {stamp} ({session.label})",
        "",
        f"Base: `{session.base}`. Screenshots beside this file."
        if not session.steps
        else f"Base: `{session.base}`. Screenshots in `{out_dir.name}/`.",
        "",
        "## What the agent did",
        "",
    ]
    for step in session.steps:
        if step["step"] == "console":
            continue
        extras = []
        for key in ("load_ms", "ms", "seed_chips", "chars"):
            if key in step:
                extras.append(f"{key}={step[key]}")
        dom = step.get("dom") or {}
        if dom:
            extras.append(f"controls={dom.get('controls')}")
            if dom.get("small_control_count"):
                extras.append(f"small={dom['small_control_count']}")
            if dom.get("overflow_x"):
                extras.append("overflow_x")
        lines.append(f"- **{step['step']}** — {', '.join(extras)} — `{step.get('shot', '')}`")

    lines += ["", "## Findings", ""]
    if session.findings:
        lines += ["| severity | step | what | fix | evidence |", "|---|---|---|---|---|"]
        for f in session.findings:
            lines.append(f"| {f.severity} | {f.step} | {f.what} | {f.fix} | `{f.evidence}` |")
    else:
        lines.append("None. The journeys completed without a finding.")

    if session.console_errors:
        lines += ["", "## Console", ""]
        lines += [f"- {e}" for e in session.console_errors[:10]]

    lines += [
        "",
        "## Next",
        "",
        "Fix the blocker and high rows, then run this script again with a new label",
        "and mark each earlier finding as fixed or still open.",
        "",
    ]
    md_path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--label", default="run")
    parser.add_argument("--chrome", default=DEFAULT_CHROME)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    session = run(args.base, args.label, args.chrome, args.headed)
    blockers = [f for f in session.findings if f.severity == "blocker"]
    print(f"steps={len(session.steps)} findings={len(session.findings)} blockers={len(blockers)}")
    for f in session.findings:
        print(f"  [{f.severity}] {f.step}: {f.what}")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
