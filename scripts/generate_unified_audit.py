#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def scryfall_img(card: str) -> str:
    return f"https://api.scryfall.com/cards/named?exact={card}&format=image&version=normal"


def escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def section_similarity(game: str, test_path: Path) -> Tuple[str, int]:
    data = load_json(test_path)
    queries = data.get("queries", {})
    qcount = len(queries)

    # Build tiles per query
    blocks: List[str] = []
    for q, buckets in queries.items():
        q_safe = escape(q)
        q_img = scryfall_img(q)
        rows: List[str] = []
        for label in ("highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant", "irrelevant"):
            names: List[str] = buckets.get(label, []) or []
            if not names:
                continue
            cards = "".join(
                f"<div class=\"tile\"><img loading=\"lazy\" src=\"{scryfall_img(n)}\" alt=\"{escape(n)}\"/><div class=\"t\">{escape(n)}</div></div>"
                for n in names
            )
            header = label.replace("_", " ")
            rows.append(f"<div class=\"bucket\"><div class=\"bh\">{escape(header)}</div><div class=\"tiles\">{cards}</div></div>")

        buckets_html = "".join(rows)
        blocks.append(
            f"""
            <section class=\"query\">
              <div class=\"qh\"><img class=\"qi\" loading=\"lazy\" src=\"{q_img}\" alt=\"{q_safe}\"/><div class=\"qt\">{q_safe}</div></div>
              {buckets_html}
            </section>
            """
        )

    game_title = escape(game.capitalize())
    return (
        f"<section class=\"game game-{escape(game)}\">"
        f"<h2 class=\"gt\">{game_title} similarity</h2>"
        + "".join(blocks)
        + "</section>"
    ), qcount


def section_deck_completion_inline() -> str:
    # Build a small inline panel from the same logic as the standalone audit
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

    import sys
    ml_dir = ROOT / "src" / "ml"
    sys.path.insert(0, str(ml_dir))
    from deck_completion import CompletionConfig, greedy_complete  # type: ignore

    def dummy_candidate_fn(card: str, k: int):
        pool = [
            ("Lava Spike", 0.99),
            ("Rift Bolt", 0.98),
            ("Searing Blaze", 0.97),
            ("Skewer the Critics", 0.96),
            ("Boros Charm", 0.95),
        ]
        return pool[:k]

    cfg = CompletionConfig(game="magic", target_main_size=32, max_steps=4, budget_max=5.0, coverage_weight=0.2)
    out, steps = greedy_complete("magic", seed, dummy_candidate_fn, cfg, price_fn=lambda _: 0.5, tag_set_fn=lambda _: set())

    def deck_grid(title: str, deck: dict) -> str:
        main = next((p for p in deck.get("partitions", []) or [] if p.get("name") == "Main"), None)
        cards = main.get("cards", []) if main else []
        tiles = []
        for c in cards:
            name = str(c.get("name", ""))
            count = int(c.get("count", 0))
            tiles.append(
                f"<div class=\"tile\"><img loading=\"lazy\" src=\"{scryfall_img(name)}\" alt=\"{escape(name)}\"/><div class=\"t\">{escape(name)} ×{count}</div></div>"
            )
        return f"<div class=\"deck\"><div class=\"dt\">{escape(title)}</div><div class=\"tiles\">{''.join(tiles)}</div></div>"

    lis = []
    for s in steps:
        op = escape(str(s.get("op", "")))
        card = escape(str(s.get("card", "")))
        part = escape(str(s.get("partition", "")))
        cnt = escape(str(s.get("count", 1)))
        lis.append(f"<li><code>{op}</code> {card} ×{cnt} → {part}</li>")
    steps_html = f"<ol class=\"steps\">{''.join(lis)}</ol>" if lis else "<div class=\"note\">No steps</div>"

    return (
        "<section class=\"game game-magic\">"
        + "<h2 class=\"gt\">Deck completion</h2>"
        + "<div class=\"grid2\">"
        + f"<div class=\"panel\">{deck_grid('Before', seed)}</div>"
        + f"<div class=\"panel\">{deck_grid('After', out)}</div>"
        + "</div>"
        + f"<div class=\"panel\"><div class=\"dt\">Steps</div>{steps_html}</div>"
        + "</section>"
    )


def compute_averages(test_sets: Dict[str, Path]) -> str:
    # Prefer cross_game_metrics.json if present; fallback to fusion file for magic only
    cross = ROOT / "experiments" / "cross_game_metrics.json"
    metrics: Dict[str, Dict] = {}
    if cross.exists():
        try:
            data = load_json(cross)
            metrics = data.get("games", {})
            weighted_p10 = data.get("weighted", {}).get("p@10")
        except Exception:
            metrics = {}
            weighted_p10 = None
    else:
        weighted_p10 = None

    # Build display rows
    rows = []
    total_q = 0
    for game, p in test_sets.items():
        qcount = len((load_json(p) or {}).get("queries", {}))
        total_q += qcount
        s = None
        if metrics.get(game):
            s = metrics[game].get("p@10")
        s_str = (f"{float(s):.3f}" if s is not None else "n/a")
        rows.append(f"<tr><td>{escape(game)}</td><td class=\"m\">{s_str}</td><td class=\"m\">{qcount}</td></tr>")

    overall = f"<tr><th>overall</th><th class=\"m\">{(f'{float(weighted_p10):.3f}' if weighted_p10 is not None else 'n/a')}</th><th class=\"m\">{total_q}</th></tr>"
    table = f"""
    <table>
      <thead><tr><th>game</th><th>P@10 (Jaccard)</th><th>#queries</th></tr></thead>
      <tbody>{overall}{''.join(rows)}</tbody>
    </table>
    """
    return table


def main() -> int:
    # Test sets
    tests = {
        "magic": ROOT / "experiments" / "test_set_canonical_magic.json",
        "yugioh": ROOT / "experiments" / "test_set_canonical_yugioh.json",
        "pokemon": ROOT / "experiments" / "test_set_canonical_pokemon.json",
    }
    present = {g: p for g, p in tests.items() if p.exists()}

    sections: List[str] = []
    # Header metrics
    sections.append("<h2>Averages</h2>" + compute_averages(present))

    # Per-game similarity sections
    for game, path in present.items():
        html, _ = section_similarity(game, path)
        sections.append(html)

    # Deck completion summary
    sections.append(section_deck_completion_inline())

    body = "".join(sections)

    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#0a0a0a; color:#e5e7eb; padding:24px; }
    h1 { font-size: 28px; margin: 0 0 8px; }
    h2 { font-size: 18px; margin: 16px 0 8px; color:#cbd5e1; }
    table { width:100%; border-collapse: collapse; margin: 8px 0 16px; }
    th, td { border:1px solid #1f2937; padding:6px 8px; text-align:left; }
    th { background:#0f172a; }
    .m { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace; }
    .query { background:#111827; border:1px solid #1f2937; border-radius:8px; padding:12px; margin: 8px 0; }
    .qh { display:flex; align-items:center; gap:10px; margin-bottom: 8px; }
    .qi { width:80px; height:auto; border-radius:6px; border:1px solid #374151; }
    .qt { font-weight:700; }
    .bucket { margin:8px 0; }
    .bh { background:#0f172a; border:1px solid #1f2937; border-radius:6px; padding:6px 10px; margin-bottom:6px; }
    .grid2 { display:grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .panel { background:#111827; border:1px solid #1f2937; border-radius:8px; padding:12px; }
    .dt { font-weight: 700; margin-bottom: 8px; }
    .tiles { display:grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap:10px; }
    .tile { background:#0f172a; border:1px solid #273043; border-radius:6px; padding:8px; }
    .tile img { width:100%; height:auto; border-radius:4px; display:block; }
    .tile .t { margin-top:6px; font-size: 13px; color:#cbd5e1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .note { color:#9ca3af; }
    @font-face { font-family: 'Matrix-Bold'; src: url('../assets/fonts/Matrix-Bold.woff') format('woff'); font-weight: normal; font-style: normal; }
    @font-face { font-family: 'Mplantin'; src: url('../assets/fonts/Mplantin.woff') format('woff'); font-weight: normal; font-style: normal; }
    /* Per-game typography accents */
    .game-magic .gt { font-family: 'Matrix-Bold', serif; letter-spacing: 0.02em; }
    .game-magic .qt { font-family: 'Matrix-Bold', serif; }
    .game-yugioh .gt { font-family: 'Times New Roman', Georgia, serif; letter-spacing: 0.015em; }
    .game-pokemon .gt { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; letter-spacing: 0.01em; }
    """

    html = f"""<!DOCTYPE html>
<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\"/>\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>\n<title>DeckSage Audit</title>\n<style>{css}</style>\n<link rel=\"preconnect\" href=\"https://api.scryfall.com\"/>\n</head>\n<body>\n<h1>DeckSage Audit</h1>\n{body}\n</body>\n</html>\n"""

    out = ROOT / "experiments" / "audit.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


