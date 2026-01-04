#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def scryfall_img_url(card_name: str) -> str:
    # Simple, robust img URL via named PNG endpoints
    # Fallback to search URL if needed client-side
    return f"https://api.scryfall.com/cards/named?exact={card_name}&format=image&version=normal"


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_section(query: str, buckets: dict[str, list[str]]) -> str:
    groups = [
        ("Highly relevant", buckets.get("highly_relevant", []), "#10b981"),
        ("Relevant", buckets.get("relevant", []), "#22c55e"),
        ("Somewhat", buckets.get("somewhat_relevant", []), "#eab308"),
        ("Marginal", buckets.get("marginally_relevant", []), "#f59e0b"),
        ("Irrelevant", buckets.get("irrelevant", []), "#ef4444"),
    ]

    def card_tile(name: str) -> str:
        safe = escape_html(name)
        img = scryfall_img_url(name)
        return (
            f'<div class="tile" data-name="{safe}">'
            f'  <img loading="lazy" src="{img}" alt="{safe}"/>'
            f'  <div class="tile-name">{safe}</div>'
            f"</div>"
        )

    tiles_html = []
    for label, names, color in groups:
        if not names:
            continue
        items = "".join(card_tile(n) for n in names)
        tiles_html.append(
            f"""
            <div class=\"bucket\">
              <div class=\"bucket-header\" style=\"border-left: 4px solid {color};\">{escape_html(label)}</div>
              <div class=\"tiles\">{items}</div>
            </div>
            """
        )

    tiles = "\n".join(tiles_html)
    q_safe = escape_html(query)
    q_img = scryfall_img_url(query)
    return f"""
    <section class=\"query\" id=\"{q_safe}\">
      <div class=\"query-header\">
        <img class=\"query-img\" loading=\"lazy\" src=\"{q_img}\" alt=\"{q_safe}\"/>
        <div class=\"query-title\">{q_safe}</div>
        <button class=\"btn export\" onclick=\"exportReview('{q_safe}')\">Export review</button>
      </div>
      {tiles}
    </section>
    """


def generate(test_set_path: Path, output_path: Path) -> None:
    data = load_json(test_set_path)
    queries: dict[str, dict[str, list[str]]] = data.get("queries", {})

    sections = []
    for q, buckets in queries.items():
        sections.append(build_section(q, buckets))

    body = "\n".join(sections)

    css = """
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#0a0a0a; color:#e0e0e0; padding:24px; }
    h1 { font-size: 28px; margin: 0 0 8px 0; color:#a78bfa; }
    .subtitle { color:#9ca3af; margin-bottom: 16px; }
    .query { background:#111; border:1px solid #222; border-radius:8px; margin:16px 0; padding:16px; }
    .query-header { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
    .query-img { width:80px; height:auto; border-radius:6px; border:1px solid #333; }
    .query-title { font-weight:700; font-size:18px; }
    .bucket { margin: 12px 0; }
    .bucket-header { padding:6px 10px; background:#151515; border:1px solid #222; border-radius:6px; color:#e5e7eb; font-weight:600; margin-bottom:8px; }
    .tiles { display:grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap:10px; }
    .tile { background:#0f172a; border:1px solid #273043; border-radius:6px; padding:8px; transition:transform .15s ease, border-color .15s ease; }
    .tile:hover { transform: translateY(-2px); border-color:#64748b; }
    .tile img { width:100%; height:auto; display:block; border-radius:4px; }
    .tile-name { margin-top:6px; font-size:13px; color:#cbd5e1; text-overflow:ellipsis; white-space:nowrap; overflow:hidden; }
    .btn { background:#1f2937; border:1px solid #374151; color:#e5e7eb; padding:6px 10px; border-radius:6px; cursor:pointer; }
    .btn:hover { background:#374151; }
    .controls { display:flex; gap:8px; margin: 8px 0 16px 0; }
    input[type='search'] { width: 280px; padding:8px 10px; border-radius:6px; border:1px solid #333; background:#0f172a; color:#e5e7eb; }
    a { color:#93c5fd; }
    """

    js = """
    function exportReview(query) {
      const section = document.getElementById(query);
      if (!section) return;
      const buckets = Array.from(section.querySelectorAll('.bucket'));
      const result = { query: query, reviewed_at: new Date().toISOString(), judgments: {} };
      buckets.forEach(b => {
        const label = b.querySelector('.bucket-header').innerText.trim();
        const names = Array.from(b.querySelectorAll('.tile')).map(t => t.getAttribute('data-name'));
        result.judgments[label] = names;
      });
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `review_${query.replace(/[^a-z0-9]+/gi,'_').toLowerCase()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    }

    function filterQueries() {
      const text = (document.getElementById('filterBox').value || '').toLowerCase();
      const sections = Array.from(document.querySelectorAll('section.query'));
      sections.forEach(s => {
        const id = s.id.toLowerCase();
        s.style.display = id.includes(text) ? '' : 'none';
      });
    }
    """

    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\"/>
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>
  <title>DeckSage Similarity Audit</title>
  <style>{css}</style>
  <link rel=\"preconnect\" href=\"https://api.scryfall.com\"/>
  <link rel=\"preconnect\" href=\"https://c1.scryfall.com\"/>
  <link rel=\"preconnect\" href=\"https://cards.scryfall.io\"/>
  <script>{js}</script>
  <script defer>
    document.addEventListener('DOMContentLoaded', () => {{
      const input = document.getElementById('filterBox');
      input.addEventListener('input', filterQueries);
    }});
  </script>
  <meta http-equiv=\"referrer\" content=\"no-referrer\"/>
  <meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self'; img-src https: data:; style-src 'unsafe-inline' 'self'; script-src 'unsafe-inline' 'self'\"/>
  <meta name=\"robots\" content=\"noindex\"/>
  <meta name=\"color-scheme\" content=\"dark light\"/>
  <base target=\"_blank\"/>
  <noscript><style>.btn, .controls{{display:none}}</style></noscript>
  <link rel=\"icon\" href=\"data:,\"/>
  </head>
<body>
  <h1>DeckSage Similarity Audit</h1>
  <div class=\"subtitle\">Current canonical test set with image previews for quick human audit</div>
  <div class=\"controls\">
    <input id=\"filterBox\" type=\"search\" placeholder=\"Filter queries (e.g., lightning)\"/>
    <a href=\"https://scryfall.com\">Scryfall</a>
  </div>
  {body}
  <footer style=\"margin-top:32px; color:#9ca3af; font-size:12px;\">Images via Scryfall. For review only.</footer>
  </body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write(html)


def main(argv: list[str]) -> int:
    # Defaults to canonical test set
    test_set = ROOT / "experiments" / "test_set_canonical_magic.json"
    out_path = ROOT / "experiments" / "audit_similarity.html"
    if not test_set.exists():
        print(f"Test set not found: {test_set}", file=sys.stderr)
        return 2
    generate(test_set, out_path)
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
