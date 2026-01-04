#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def scryfall_img_url(card_name: str) -> str:
    return f"https://api.scryfall.com/cards/named?exact={card_name}&format=image&version=normal"


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_deck_grid(title: str, deck: dict) -> str:
    main = None
    for p in deck.get("partitions", []) or []:
        if p.get("name") == "Main":
            main = p
            break
    cards = main.get("cards", []) if main else []
    tiles = []
    for c in cards:
        name = str(c.get("name", ""))
        count = int(c.get("count", 0))
        img = scryfall_img_url(name)
        tiles.append(
            f'<div class="tile"><img loading="lazy" src="{img}" alt="{escape_html(name)}"/><div class="tile-name">{escape_html(name)} ×{count}</div></div>'
        )
    grid = "".join(tiles)
    return f"""
    <div class=\"deck\">
      <div class=\"deck-title\">{escape_html(title)}</div>
      <div class=\"tiles\">{grid}</div>
    </div>
    """


def build_steps_list(steps: list[dict]) -> str:
    if not steps:
        return '<div class="steps-empty">No steps applied</div>'
    lis = []
    for s in steps:
        op = escape_html(str(s.get("op", "")))
        card = escape_html(str(s.get("card", "")))
        part = escape_html(str(s.get("partition", "")))
        cnt = escape_html(str(s.get("count", 1)))
        lis.append(f"<li><code>{op}</code> {card} ×{cnt} → {part}</li>")
    return f'<ol class="steps">{"".join(lis)}</ol>'


def main() -> int:
    # Use the example partial deck from tests as seed
    seed = {
        "deck_id": "ex1",
        "format": "Modern",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Monastery Swiftspear", "count": 4},
                    {"name": "Goblin Guide", "count": 4},
                    {"name": "Mountain", "count": 20},
                ],
            }
        ],
    }

    # Import from src/ml
    ml_dir = ROOT / "src" / "ml"
    sys.path.insert(0, str(ml_dir))
    from deck_completion import CompletionConfig, greedy_complete  # type: ignore

    # Dummy candidate fn consistent with tests
    def dummy_candidate_fn(card: str, k: int):
        pool = [
            ("Lava Spike", 0.99),
            ("Rift Bolt", 0.98),
            ("Searing Blaze", 0.97),
            ("Skewer the Critics", 0.96),
            ("Boros Charm", 0.95),
        ]
        return pool[:k]

    cfg = CompletionConfig(
        game="magic", target_main_size=32, max_steps=4, budget_max=5.0, coverage_weight=0.2
    )
    out, steps = greedy_complete(
        "magic", seed, dummy_candidate_fn, cfg, price_fn=lambda _: 0.5, tag_set_fn=lambda _: set()
    )

    before_html = build_deck_grid("Before", seed)
    after_html = build_deck_grid("After", out)
    steps_html = build_steps_list(steps)

    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#0a0a0a; color:#e5e7eb; padding:24px; }
    h1 { font-size: 28px; margin: 0 0 8px; color:#60a5fa; }
    .grid { display:grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .deck-title { font-weight: 700; margin-bottom: 8px; }
    .tiles { display:grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }
    .tile { background:#0f172a; border:1px solid #273043; border-radius:6px; padding:8px; }
    .tile img { width:100%; height:auto; border-radius:4px; display:block; }
    .tile-name { margin-top:6px; font-size: 13px; color:#cbd5e1; }
    .steps { margin-top: 8px; }
    .panel { background:#111827; border:1px solid #1f2937; border-radius:8px; padding:12px; }
    code { background:#111827; border:1px solid #1f2937; padding:2px 4px; border-radius:4px; }
    """

    html = f"""<!DOCTYPE html>
<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\"/>\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>\n<title>DeckSage Deck Completion Audit</title>\n<style>{css}</style>\n<link rel=\"preconnect\" href=\"https://api.scryfall.com\"/>\n</head>\n<body>\n<h1>Deck Completion Audit</h1>\n<div class=\"grid\">\n  <div class=\"panel\">{before_html}</div>\n  <div class=\"panel\">{after_html}</div>\n</div>\n<div class=\"panel\">\n  <div class=\"deck-title\">Steps</div>\n  {steps_html}\n</div>\n<footer style=\"margin-top:24px; color:#9ca3af; font-size:12px;\">Images via Scryfall. For review only.</footer>\n</body>\n</html>\n"""

    out_path = ROOT / "experiments" / "audit_deck_completion.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
