#!/usr/bin/env python3
"""
Multi-Game Embedding Comparison

Compare embedding quality across Magic, Yu-Gi-Oh!, and Pokemon using:
- Same Node2Vec hyperparameters
- Same evaluation metrics
- Cross-game transfer learning analysis
"""

import argparse

try:
    from gensim.models import KeyedVectors

    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False


def compare_all_games(
    magic_wv: str,
    yugioh_wv: str | None = None,
    pokemon_wv: str | None = None,
    output_html: str = "multi_game_comparison.html",
):
    """Compare embedding quality across all games"""
    from datetime import datetime

    games = []

    # Load each game's embeddings
    if magic_wv:
        wv_mtg = KeyedVectors.load(magic_wv)
        games.append(
            {
                "name": "Magic: The Gathering",
                "wv": wv_mtg,
                "num_cards": len(wv_mtg),
                "dim": wv_mtg.vector_size,
            }
        )

    if yugioh_wv:
        wv_ygo = KeyedVectors.load(yugioh_wv)
        games.append(
            {"name": "Yu-Gi-Oh!", "wv": wv_ygo, "num_cards": len(wv_ygo), "dim": wv_ygo.vector_size}
        )

    if pokemon_wv:
        wv_pkm = KeyedVectors.load(pokemon_wv)
        games.append(
            {"name": "Pokemon", "wv": wv_pkm, "num_cards": len(wv_pkm), "dim": wv_pkm.vector_size}
        )

    # Generate comparison HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light dark">
    <title>Multi-Game Embedding Comparison</title>
    <link rel="stylesheet" href="shared.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>Multi-Game Embedding Comparison</h1>
            <p class="timestamp">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </header>

        <h2>Graph Statistics</h2>
        <table>
            <thead>
                <tr>
                    <th>Game</th>
                    <th>Cards</th>
                    <th>Dimensions</th>
                    <th>Avg Degree</th>
                    <th>Clustering Coef</th>
                </tr>
            </thead>
            <tbody>
"""

    for game in games:
        html += f"""
                <tr>
                    <td><strong>{game["name"]}</strong></td>
                    <td class="metric">{game["num_cards"]:,}</td>
                    <td class="metric">{game["dim"]}</td>
                    <td class="metric">-</td>
                    <td class="metric">-</td>
                </tr>
"""

    html += """
            </tbody>
        </table>

        <h2>Research Questions</h2>
        <ul>
            <li>Do graph embeddings work equally well across different card games?</li>
            <li>Can we transfer learned similarity metrics between games?</li>
            <li>What game-specific properties affect embedding quality?</li>
        </ul>
    </div>
</body>
</html>
"""

    with open(output_html, "w") as f:
        f.write(html)

    print(f"📊 Multi-game comparison: {output_html}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--magic", type=str, help="Magic embeddings")
    parser.add_argument("--yugioh", type=str, help="Yu-Gi-Oh embeddings")
    parser.add_argument("--pokemon", type=str, help="Pokemon embeddings")
    parser.add_argument("--output", type=str, default="multi_game_comparison.html")

    args = parser.parse_args()
    compare_all_games(args.magic, args.yugioh, args.pokemon, args.output)
