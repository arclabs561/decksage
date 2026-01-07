#!/usr/bin/env python3
"""
Browser-based annotation tool using MCP browser tools.

Allows annotating card similarities through browser interactions.
Can be used by Cursor agent or manually.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def create_browser_annotation_interface(
    query_card: str,
    candidates: list[str],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """
    Create a browser-based annotation interface.

    This function generates instructions for browser-based annotation
    that can be executed via MCP browser tools or manually.
    """
    # Generate HTML interface
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Card Similarity Annotation: {query_card}</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .query-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .query-card h1 {{
            margin: 0 0 10px 0;
            color: #333;
        }}
        .candidate {{
            background: white;
            padding: 15px;
            margin: 10px 0;
            border-radius: 6px;
            border: 2px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .candidate:hover {{
            border-color: #4CAF50;
        }}
        .candidate-name {{
            font-weight: 500;
            font-size: 16px;
        }}
        .rating-buttons {{
            display: flex;
            gap: 5px;
        }}
        .rating-btn {{
            padding: 8px 16px;
            border: 1px solid #ccc;
            background: white;
            cursor: pointer;
            border-radius: 4px;
            font-size: 14px;
        }}
        .rating-btn:hover {{
            background: #f0f0f0;
        }}
        .rating-btn.selected {{
            background: #4CAF50;
            color: white;
            border-color: #4CAF50;
        }}
        .notes-input {{
            width: 100%;
            padding: 8px;
            margin-top: 10px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-family: inherit;
        }}
        .submit-btn {{
            background: #2196F3;
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            cursor: pointer;
            margin-top: 20px;
        }}
        .submit-btn:hover {{
            background: #1976D2;
        }}
        .legend {{
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
        }}
        .legend h3 {{
            margin-top: 0;
        }}
        .legend ul {{
            margin: 0;
            padding-left: 20px;
        }}
    </style>
</head>
<body>
    <div class="query-card">
        <h1>Query Card: {query_card}</h1>
        <p>Rate the similarity of each candidate card to the query card.</p>
    </div>

    <div class="legend">
        <h3>Relevance Scale</h3>
        <ul>
            <li><strong>4</strong>: Extremely similar (near substitutes, same function)</li>
            <li><strong>3</strong>: Very similar (often seen together, similar role)</li>
            <li><strong>2</strong>: Somewhat similar (related function or archetype)</li>
            <li><strong>1</strong>: Marginally similar (loose connection)</li>
            <li><strong>0</strong>: Irrelevant (different function, color, or archetype)</li>
        </ul>
    </div>

    <form id="annotation-form">
        <div id="candidates-container">
"""

    for i, candidate in enumerate(candidates):
        html_content += f"""
            <div class="candidate" data-candidate="{candidate}">
                <div class="candidate-name">{candidate}</div>
                <div>
                    <div class="rating-buttons">
                        <button type="button" class="rating-btn" data-rating="4" onclick="selectRating(this, {i})">4</button>
                        <button type="button" class="rating-btn" data-rating="3" onclick="selectRating(this, {i})">3</button>
                        <button type="button" class="rating-btn" data-rating="2" onclick="selectRating(this, {i})">2</button>
                        <button type="button" class="rating-btn" data-rating="1" onclick="selectRating(this, {i})">1</button>
                        <button type="button" class="rating-btn" data-rating="0" onclick="selectRating(this, {i})">0</button>
                    </div>
                    <input type="text" class="notes-input" placeholder="Notes (optional)" id="notes-{i}" />
                    <input type="hidden" id="rating-{i}" name="rating-{i}" value="" />
                </div>
            </div>
"""

    html_content += """
        </div>
        <button type="submit" class="submit-btn">Submit Annotations</button>
    </form>

    <script>
        const ratings = {};
        const notes = {};

        function selectRating(btn, index) {
            // Remove selected class from all buttons in this group
            const container = btn.closest('.candidate');
            container.querySelectorAll('.rating-btn').forEach(b => b.classList.remove('selected'));
            
            // Add selected class to clicked button
            btn.classList.add('selected');
            
            // Store rating
            const rating = parseInt(btn.dataset.rating);
            ratings[index] = rating;
            document.getElementById(`rating-${index}`).value = rating;
        }

        document.getElementById('annotation-form').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const annotations = [];
            const candidates = document.querySelectorAll('.candidate');
            
            candidates.forEach((candidateEl, index) => {
                const candidate = candidateEl.dataset.candidate;
                const rating = ratings[index];
                const note = document.getElementById(`notes-${index}`).value;
                
                if (rating !== undefined) {
                    annotations.push({
                        candidate: candidate,
                        relevance: rating,
                        notes: note
                    });
                }
            });
            
            const result = {
                query: '""" + query_card + """',
                timestamp: new Date().toISOString(),
                annotations: annotations
            };
            
            // Download as JSON
            const blob = new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'annotations_' + Date.now() + '.json';
            a.click();
            URL.revokeObjectURL(url);
            
            alert('Annotations saved! Check your downloads folder.');
        });
    </script>
</body>
</html>
"""

    # Save HTML file
    if output_path is None:
        output_path = project_root / "annotations" / f"browser_annotation_{query_card.replace(' ', '_')}.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html_content)

    print(f"✓ Created browser annotation interface: {output_path}")
    print(f"  Query: {query_card}")
    print(f"  Candidates: {len(candidates)}")
    print(f"\nOpen {output_path} in a browser to annotate.")
    print("After annotation, the results will be downloaded as JSON.")

    return {
        "html_path": str(output_path),
        "query_card": query_card,
        "candidates": candidates,
    }


def convert_relevance_to_similarity_score(relevance: int, scale: str = "0-4") -> float:
    """Convert relevance score (0-4) to similarity score (0-1)."""
    mapping = {4: 0.95, 3: 0.75, 2: 0.55, 1: 0.35, 0: 0.1}
    return mapping.get(relevance, 0.0)


def convert_browser_annotation_to_unified(
    annotation_json: dict[str, Any],
    output_path: Path | None = None,
) -> list[dict]:
    """Convert browser annotation JSON to unified annotation format."""

    query = annotation_json.get("query", "")
    annotations = annotation_json.get("annotations", [])

    unified = []
    for ann in annotations:
        candidate = ann.get("candidate", "")
        relevance = ann.get("relevance", 0)

        if not candidate or relevance is None:
            continue

        try:
            rel_int = int(relevance)
            if not (0 <= rel_int <= 4):
                continue
        except (ValueError, TypeError):
            continue

        similarity_score = convert_relevance_to_similarity_score(rel_int, scale="0-4")

        unified.append(
            {
                "card1": query,
                "card2": candidate,
                "similarity_score": similarity_score,
                "similarity_type": "substitute" if rel_int == 4 else "functional",
                "is_substitute": rel_int == 4,
                "source": "browser_annotation",
                "relevance": rel_int,
                "notes": ann.get("notes", ""),
                "metadata": {
                    "timestamp": annotation_json.get("timestamp", datetime.now().isoformat()),
                },
            }
        )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        try:
            with open(temp_path, "w") as f:
                for ann in unified:
                    f.write(json.dumps(ann, ensure_ascii=False) + "\n")
            temp_path.replace(output_path)
            print(f"✓ Converted {len(unified)} annotations to {output_path}")
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise

    return unified


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Browser-based annotation tool")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Create interface
    create_parser = subparsers.add_parser("create", help="Create browser annotation interface")
    create_parser.add_argument("--query", type=str, required=True, help="Query card name")
    create_parser.add_argument(
        "--candidates", nargs="+", required=True, help="Candidate card names"
    )
    create_parser.add_argument("--output", type=Path, help="Output HTML path")

    # Convert annotation
    convert_parser = subparsers.add_parser("convert", help="Convert browser annotation to unified format")
    convert_parser.add_argument("--input", type=Path, required=True, help="Browser annotation JSON file")
    convert_parser.add_argument(
        "--output",
        type=Path,
        help="Output unified annotation JSONL path",
    )

    args = parser.parse_args()

    if args.command == "create":
        create_browser_annotation_interface(args.query, args.candidates, args.output)
    elif args.command == "convert":
        with open(args.input) as f:
            data = json.load(f)
        convert_browser_annotation_to_unified(data, args.output)
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

