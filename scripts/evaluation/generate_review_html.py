#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0"]
# ///
"""
Generate static HTML review pages for embedding quality inspection.

For each query in a test set, shows the query card and top-K results from
one or more embedding models, side by side with card images. Designed for
visual QA of similarity models at checkpoints.

Supports image URLs from:
  - Scryfall (Magic): data/processed/card_attributes_enriched_image_urls.json
  - YGOProDeck (YGO): https://images.ygoprodeck.com/images/cards/{id}.jpg
  - pokemontcg.io (Pokemon): https://images.pokemontcg.io/{set}/{number}.png

Usage:
    # Single model
    python scripts/evaluation/generate_review_html.py \
        --test-set data/test_set_annotated_magic.json \
        --embeddings data/embeddings/magic_prone_propagated.wv \
        --image-urls data/processed/card_attributes_enriched_image_urls.json \
        --output experiments/review_magic_prone.html

    # Compare multiple models
    python scripts/evaluation/generate_review_html.py \
        --test-set data/test_set_annotated_pokemon.json \
        --embeddings data/embeddings/pokemon_prone_propagated.wv \
                     data/embeddings/pokemon_pecanpy_propagated.wv \
        --game pokemon \
        --output experiments/review_pokemon_compare.html

    # Limit queries
    python scripts/evaluation/generate_review_html.py \
        --test-set data/test_set_annotated_yugioh.json \
        --embeddings data/embeddings/yugioh_prone_propagated.wv \
        --game yugioh --max-queries 20 --top-k 10 \
        --output experiments/review_yugioh.html
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path

from gensim.models import KeyedVectors

GRADES = {
    "highly_relevant": 3,
    "relevant": 2,
    "somewhat_relevant": 1,
    "marginally_relevant": 0.5,
    "irrelevant": 0,
}

GRADE_COLORS = {
    "highly_relevant": "#4caf50",
    "relevant": "#8bc34a",
    "somewhat_relevant": "#ff9800",
    "marginally_relevant": "#ff5722",
    "irrelevant": "#666",
    "unknown": "#333",
}

# Image URL APIs by game
SCRYFALL_SEARCH = "https://api.scryfall.com/cards/named?fuzzy={name}"
YGOPRODECK_SEARCH = "https://db.ygoprodeck.com/api/v7/cardinfo.php?name={name}"
POKEMON_SEARCH = "https://api.pokemontcg.io/v2/cards?q=name:{name}"


def load_image_urls(path: Path | None) -> dict[str, str]:
    """Load card name -> image URL mapping from JSON file."""
    if not path or not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def load_image_urls_from_graph_db(db_path: Path) -> dict[str, str]:
    """Load card name -> image URL mapping from unified SQLite graph."""
    import sqlite3

    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    try:
        rows = conn.execute(
            "SELECT name, image_url FROM nodes WHERE image_url IS NOT NULL AND image_url != ''"
        ).fetchall()
        return {name: url for name, url in rows}
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def get_image_url(card_name: str, image_urls: dict[str, str], game: str) -> str:
    """Get image URL for a card, with fallback to API search."""
    if card_name in image_urls:
        return image_urls[card_name]

    # No fallback -- rely on pre-built image URL files to avoid API rate limits
    return ""


def get_grade(card_name: str, labels: dict) -> tuple[str, float]:
    """Get the relevance grade for a result card."""
    for grade, score in GRADES.items():
        if card_name in labels.get(grade, []):
            return grade, score
    return "unknown", 0.0


def dcg(scores: list[float], k: int) -> float:
    return sum(s / math.log2(i + 2) for i, s in enumerate(scores[:k]))


def ndcg(rels: list[float], k: int) -> float:
    d = dcg(rels, k)
    ideal = dcg(sorted(rels, reverse=True), k)
    return d / ideal if ideal > 0 else 0.0


def generate_html(
    test_data: dict,
    models: list[tuple[str, KeyedVectors]],
    image_urls: dict[str, str],
    game: str,
    top_k: int,
    max_queries: int | None,
) -> str:
    """Generate the complete HTML review page."""
    queries = test_data.get("queries", test_data)

    if max_queries:
        query_items = list(queries.items())[:max_queries]
    else:
        query_items = list(queries.items())

    # Compute per-model nDCG for each query
    model_results = []
    for model_name, kv in models:
        results_per_query = {}
        scores = []
        for q, labels in query_items:
            if q not in kv:
                results_per_query[q] = {"results": [], "ndcg": None, "in_vocab": False}
                continue
            try:
                neighbors = kv.most_similar(q, topn=top_k)
            except Exception:
                results_per_query[q] = {"results": [], "ndcg": None, "in_vocab": False}
                continue

            rels = []
            result_cards = []
            for card, sim in neighbors:
                grade, score = get_grade(card, labels)
                rels.append(score)
                result_cards.append({
                    "card": card,
                    "similarity": sim,
                    "grade": grade,
                    "grade_score": score,
                })

            q_ndcg = ndcg(rels, top_k)
            scores.append(q_ndcg)
            results_per_query[q] = {
                "results": result_cards,
                "ndcg": q_ndcg,
                "in_vocab": True,
            }

        mean_ndcg = sum(scores) / len(scores) if scores else 0.0
        coverage = len(scores)
        model_results.append({
            "name": model_name,
            "results": results_per_query,
            "mean_ndcg": mean_ndcg,
            "coverage": coverage,
            "total": len(query_items),
        })

    n_models = len(models)

    # Build HTML
    lines = []
    lines.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DeckSage Embedding Review</title>
<style>
:root {
    --bg: #0f0f0f;
    --bg2: #1a1a1a;
    --bg3: #252525;
    --border: #333;
    --text: #fff;
    --text2: #b0b0b0;
    --accent: #6b8eff;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: var(--bg); color: var(--text); padding: 20px; }
.header { max-width: 1800px; margin: 0 auto 24px; }
h1 { font-size: 24px; margin-bottom: 8px; }
.summary { color: var(--text2); font-size: 14px; margin-bottom: 16px; }
.summary span { color: var(--accent); font-weight: 600; }
.model-legend { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.model-tag { padding: 4px 12px; border-radius: 4px; font-size: 13px; font-weight: 500; }
.grade-legend { display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--text2); }
.grade-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }
.controls { margin-bottom: 16px; }
.controls input { padding: 8px 12px; background: var(--bg2); border: 1px solid var(--border);
                  color: var(--text); border-radius: 4px; font-size: 14px; width: 300px; }
.query-section { max-width: 1800px; margin: 0 auto 32px; border: 1px solid var(--border);
                 border-radius: 8px; overflow: hidden; }
.query-header { padding: 12px 16px; background: var(--bg2); border-bottom: 1px solid var(--border);
                display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
.query-header:hover { background: var(--bg3); }
.query-name { font-size: 16px; font-weight: 600; }
.query-meta { font-size: 12px; color: var(--text2); }
.query-body { display: none; padding: 16px; }
.query-body.open { display: block; }
.model-row { margin-bottom: 16px; }
.model-label { font-size: 13px; font-weight: 600; color: var(--accent); margin-bottom: 8px;
               display: flex; gap: 12px; align-items: center; }
.model-ndcg { font-size: 12px; color: var(--text2); font-weight: 400; }
.results-grid { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; }
.result-card { min-width: 130px; max-width: 150px; text-align: center; flex-shrink: 0; }
.result-card img { width: 120px; height: auto; border-radius: 4px;
                   border: 3px solid transparent; transition: border-color 0.2s; }
.result-card img.loading { opacity: 0.3; }
.result-card .card-name { font-size: 11px; margin-top: 4px; color: var(--text2);
                          overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px; }
.result-card .sim-score { font-size: 11px; color: var(--text2); font-weight: 500; }
.result-card .rank { font-size: 11px; font-weight: 600; color: var(--accent); }
.grade-highly_relevant img { border-color: #4caf50; }
.grade-relevant img { border-color: #8bc34a; }
.grade-somewhat_relevant img { border-color: #ff9800; }
.grade-marginally_relevant img { border-color: #ff5722; }
.grade-irrelevant img { border-color: #444; }
.grade-unknown img { border-color: transparent; }
.query-card { display: flex; gap: 16px; align-items: flex-start; margin-bottom: 16px;
              padding-bottom: 16px; border-bottom: 1px solid var(--border); }
.query-card img { width: 150px; border-radius: 6px; }
.query-card .info { font-size: 13px; color: var(--text2); }
.query-card .info .label-count { margin-top: 8px; }
.query-card .info .label-count span { margin-right: 8px; }
.placeholder-img { width: 120px; height: 168px; background: var(--bg3); border-radius: 4px;
                   display: flex; align-items: center; justify-content: center; font-size: 10px;
                   color: var(--text2); text-align: center; padding: 8px; }
.query-card .placeholder-img { width: 150px; height: 210px; }
</style>
</head>
<body>
""")

    # Header with model summaries
    lines.append(f'<div class="header">')
    lines.append(f'<h1>Embedding Review: {game.upper()}</h1>')
    lines.append(f'<div class="summary">')
    lines.append(f'{len(query_items)} queries, top-{top_k} results')
    for mr in model_results:
        lines.append(f' | <span>{mr["name"]}</span>: nDCG={mr["mean_ndcg"]:.3f} ({mr["coverage"]}/{mr["total"]})')
    lines.append('</div>')

    # Grade legend
    lines.append('<div class="grade-legend">')
    for grade, color in GRADE_COLORS.items():
        if grade == "unknown":
            continue
        lines.append(f'<span><span class="grade-dot" style="background:{color}"></span>{grade.replace("_"," ")}</span>')
    lines.append('</div>')

    # Filter + sort controls
    lines.append('''
<div class="controls" style="margin-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
  <input type="text" id="filter" placeholder="Filter queries..." oninput="filterQueries(this.value)">
  <select id="sortBy" onchange="sortQueries(this.value)" style="padding:8px;background:var(--bg2);border:1px solid var(--border);color:var(--text);border-radius:4px;font-size:14px">
    <option value="original">Sort: original order</option>
    <option value="ndcg-asc">Sort: worst nDCG first</option>
    <option value="ndcg-desc">Sort: best nDCG first</option>
    <option value="name">Sort: card name A-Z</option>
  </select>
  <button onclick="toggleAll(true)" style="padding:6px 12px;background:var(--bg2);border:1px solid var(--border);color:var(--text);border-radius:4px;cursor:pointer">Expand All</button>
  <button onclick="toggleAll(false)" style="padding:6px 12px;background:var(--bg2);border:1px solid var(--border);color:var(--text);border-radius:4px;cursor:pointer">Collapse All</button>
</div>
''')
    lines.append('</div>')  # header

    # Per-query sections
    for q_idx, (query, labels) in enumerate(query_items):
        # Count labels per grade
        label_counts = {g: len(labels.get(g, [])) for g in GRADES}
        total_relevant = sum(v for g, v in label_counts.items() if g != "irrelevant")

        # Best/worst nDCG across models
        ndcgs = [mr["results"].get(query, {}).get("ndcg") for mr in model_results]
        ndcg_strs = [f"{n:.3f}" if n is not None else "N/A" for n in ndcgs]

        query_escaped = html.escape(query)
        # Use first model's nDCG for sorting; fallback -1 for OOV
        primary_ndcg = ndcgs[0] if ndcgs and ndcgs[0] is not None else -1
        lines.append(f'<div class="query-section" data-query="{query_escaped.lower()}" data-ndcg="{primary_ndcg:.4f}" data-order="{q_idx}">')
        lines.append(f'<div class="query-header" onclick="toggleQuery(this)">')
        lines.append(f'<span class="query-name">#{q_idx+1} {query_escaped}</span>')
        lines.append(f'<span class="query-meta">{total_relevant} relevant | nDCG: {", ".join(ndcg_strs)}</span>')
        lines.append('</div>')
        lines.append(f'<div class="query-body" id="q{q_idx}">')

        # Query card with image
        q_img = get_image_url(query, image_urls, game)
        lines.append('<div class="query-card">')
        if q_img:
            lines.append(f'<img src="{html.escape(q_img)}" alt="{query_escaped}" loading="lazy"'
                         f' onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">')
            lines.append(f'<div class="placeholder-img" style="display:none">{query_escaped}</div>')
        else:
            lines.append(f'<div class="placeholder-img">{query_escaped}</div>')
        lines.append('<div class="info">')
        lines.append(f'<div><strong>{query_escaped}</strong></div>')
        lines.append('<div class="label-count">')
        for grade in GRADES:
            c = label_counts[grade]
            if c > 0:
                color = GRADE_COLORS[grade]
                lines.append(f'<span style="color:{color}">{grade.replace("_"," ")}: {c}</span>')
        lines.append('</div></div></div>')

        # Results per model
        for mr in model_results:
            qr = mr["results"].get(query, {"results": [], "ndcg": None, "in_vocab": False})
            lines.append('<div class="model-row">')
            ndcg_str = f"nDCG={qr['ndcg']:.3f}" if qr["ndcg"] is not None else "not in vocab"
            lines.append(f'<div class="model-label">{html.escape(mr["name"])} '
                         f'<span class="model-ndcg">{ndcg_str}</span></div>')
            lines.append('<div class="results-grid">')

            for rank, rc in enumerate(qr["results"]):
                card = rc["card"]
                sim = rc["similarity"]
                grade = rc["grade"]
                card_escaped = html.escape(card)
                img_url = get_image_url(card, image_urls, game)

                lines.append(f'<div class="result-card grade-{grade}">')
                lines.append(f'<div class="rank">#{rank+1}</div>')
                if img_url:
                    lines.append(f'<img src="{html.escape(img_url)}" alt="{card_escaped}" loading="lazy"'
                                 f' onerror="this.outerHTML=\'<div class=placeholder-img>{card_escaped}</div>\'">')
                else:
                    lines.append(f'<div class="placeholder-img">{card_escaped}</div>')
                lines.append(f'<div class="card-name" title="{card_escaped}">{card_escaped}</div>')
                lines.append(f'<div class="sim-score">{sim:.3f}</div>')
                lines.append('</div>')

            if not qr["results"]:
                lines.append('<span style="color:var(--text2);font-size:13px">No results (query not in vocabulary)</span>')

            lines.append('</div></div>')  # results-grid, model-row

        lines.append('</div></div>')  # query-body, query-section

    # JavaScript
    lines.append("""
<script>
function toggleQuery(el) {
    const body = el.nextElementSibling;
    body.classList.toggle('open');
}
function toggleAll(open) {
    document.querySelectorAll('.query-body').forEach(b => {
        if (open) b.classList.add('open');
        else b.classList.remove('open');
    });
}
function filterQueries(text) {
    const q = text.toLowerCase();
    document.querySelectorAll('.query-section').forEach(s => {
        const name = s.dataset.query;
        s.style.display = (!q || name.includes(q)) ? '' : 'none';
    });
}
function sortQueries(mode) {
    const container = document.querySelector('.query-section').parentElement;
    const sections = Array.from(document.querySelectorAll('.query-section'));
    sections.sort((a, b) => {
        if (mode === 'ndcg-asc') return parseFloat(a.dataset.ndcg) - parseFloat(b.dataset.ndcg);
        if (mode === 'ndcg-desc') return parseFloat(b.dataset.ndcg) - parseFloat(a.dataset.ndcg);
        if (mode === 'name') return a.dataset.query.localeCompare(b.dataset.query);
        return parseInt(a.dataset.order) - parseInt(b.dataset.order);
    });
    sections.forEach(s => container.appendChild(s));
}
// Auto-expand first 3 queries
document.querySelectorAll('.query-body').forEach((b, i) => {
    if (i < 3) b.classList.add('open');
});
</script>
</body>
</html>
""")

    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate HTML review page for embedding quality inspection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--test-set", type=Path, required=True,
                        help="Annotated test set JSON")
    parser.add_argument("--embeddings", type=Path, nargs="+", required=True,
                        help="One or more .wv embedding files to compare")
    parser.add_argument("--image-urls", type=Path, default=None,
                        help="JSON file mapping card name -> image URL")
    parser.add_argument("--graph-db", type=Path, default=None,
                        help="Unified SQLite graph .db file (reads image URLs from nodes table)")
    parser.add_argument("--game", default="magic",
                        choices=["magic", "yugioh", "pokemon"],
                        help="Game (for image URL fallback)")
    parser.add_argument("--output", type=Path, required=True,
                        help="Output HTML file")
    parser.add_argument("--top-k", type=int, default=10,
                        help="Results per query (default: 10)")
    parser.add_argument("--max-queries", type=int, default=None,
                        help="Limit number of queries (default: all)")
    args = parser.parse_args()

    if not args.test_set.exists():
        print(f"Error: Test set not found: {args.test_set}")
        return 1

    # Load test set
    print(f"Loading test set: {args.test_set}")
    with open(args.test_set) as f:
        test_data = json.load(f)
    queries = test_data.get("queries", test_data)
    print(f"  {len(queries)} queries")

    # Load image URLs (prefer graph DB, fall back to JSON file)
    image_urls = {}
    if args.graph_db:
        image_urls = load_image_urls_from_graph_db(args.graph_db)
        if image_urls:
            print(f"  {len(image_urls)} image URLs from graph DB")

    if not image_urls and args.image_urls:
        image_urls = load_image_urls(args.image_urls)
        if image_urls:
            print(f"  {len(image_urls)} image URLs from JSON")

    # If no image URLs from either source and game is magic, try default path
    if not image_urls and args.game == "magic":
        default_img = Path("data/processed/card_attributes_enriched_image_urls.json")
        if default_img.exists():
            image_urls = load_image_urls(default_img)
            print(f"  Auto-loaded {len(image_urls)} Magic image URLs")

    # Load embedding models
    models = []
    for emb_path in args.embeddings:
        if not emb_path.exists():
            print(f"  Warning: {emb_path} not found, skipping")
            continue
        print(f"Loading embeddings: {emb_path}")
        kv = KeyedVectors.load(str(emb_path))
        name = emb_path.stem
        print(f"  {len(kv)} vectors, dim={kv.vector_size}")
        models.append((name, kv))

    if not models:
        print("Error: No embedding files loaded")
        return 1

    # Generate HTML
    print(f"\nGenerating review HTML...")
    html_content = generate_html(test_data, models, image_urls, args.game, args.top_k, args.max_queries)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w') as f:
        f.write(html_content)

    size_kb = args.output.stat().st_size / 1024
    print(f"Written {size_kb:.0f}KB to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
