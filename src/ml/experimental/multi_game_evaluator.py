#!/usr/bin/env python3
"""
Multi-Game Evaluator

Tracks performance across ALL games simultaneously.

Micro view: Best method per game
Macro view: Best method across games
Transfer: Do MTG learnings apply to YGO/Pokemon?
"""

import builtins
import contextlib
import json
from collections import defaultdict
from pathlib import Path


class MultiGameEvaluator:
    """Evaluate methods across all games"""

    def __init__(self):
        self.games = ["magic", "yugioh", "pokemon"]
        self.results = defaultdict(lambda: defaultdict(dict))

        # Load all game-specific test sets and bests
        self.test_sets = {}
        self.current_bests = {}

        for game in self.games:
            test_file = Path(f"../../experiments/test_set_canonical_{game}.json")
            best_file = Path(f"../../experiments/CURRENT_BEST_{game}.json")

            if test_file.exists():
                with open(test_file) as f:
                    self.test_sets[game] = json.load(f).get("queries", {})

            if best_file.exists():
                with open(best_file) as f:
                    self.current_bests[game] = json.load(f)
            else:
                self.current_bests[game] = {"method": "None", "p10": 0.0}

    def evaluate_method_all_games(self, method_name, method_fn_by_game):
        """
        Evaluate a method on ALL games.

        method_fn_by_game: {
            'magic': lambda query: predictions,
            'yugioh': lambda query: predictions,
            'pokemon': lambda query: predictions
        }
        """

        print(f"\n{'=' * 60}")
        print(f"Multi-Game Evaluation: {method_name}")
        print("=" * 60)

        game_results = {}

        for game in self.games:
            if game not in self.test_sets:
                print(f"\n{game}: No test set")
                continue

            if game not in method_fn_by_game:
                print(f"\n{game}: Method not implemented")
                continue

            # Evaluate
            test_set = self.test_sets[game]
            method_fn = method_fn_by_game[game]

            scores = []
            relevance_weights = {
                "highly_relevant": 1.0,
                "relevant": 0.75,
                "somewhat_relevant": 0.5,
                "marginally_relevant": 0.25,
                "irrelevant": 0.0,
            }

            for query, labels in test_set.items():
                preds = method_fn(query)
                if not preds:
                    continue

                score = 0.0
                for card, _ in preds[:10]:
                    for level, weight in relevance_weights.items():
                        if card in labels.get(level, []):
                            score += weight
                            break

                scores.append(score / 10.0)

            p10 = sum(scores) / len(scores) if scores else 0.0
            game_results[game] = {
                "p10": p10,
                "num_queries": len(scores),
                "vs_best": p10 - self.current_bests[game].get("p10", 0),
            }

            print(f"\n{game}:")
            print(f"  P@10: {p10:.4f}")
            print(f"  vs best: {game_results[game]['vs_best']:+.4f}")
            print(f"  Queries: {len(scores)}")

        # Macro: Average across games
        if game_results:
            macro_p10 = sum(r["p10"] for r in game_results.values()) / len(game_results)
            game_results["_macro"] = {
                "p10": macro_p10,
                "games_evaluated": list(game_results.keys()),
            }

            print(f"\n{'=' * 60}")
            print(f"Macro (Cross-Game Average): P@10 = {macro_p10:.4f}")
            print("=" * 60)

        return game_results

    def find_universal_winner(self):
        """Which method works best across ALL games?"""

        # Load all experiments, group by method
        experiments = []
        with open("../../experiments/EXPERIMENT_LOG.jsonl") as f:
            for line in f:
                if line.strip():
                    with contextlib.suppress(builtins.BaseException):
                        experiments.append(json.loads(line))

        # Group by method and game
        by_method_game = defaultdict(lambda: defaultdict(list))

        for exp in experiments:
            method = exp.get("method", "unknown")
            game = exp.get("game", "magic")  # Default to magic for old experiments
            p10 = exp.get("results", {}).get("p10")

            if p10 is not None:
                by_method_game[method][game].append(p10)

        # Compute averages
        method_scores = {}
        for method, games_dict in by_method_game.items():
            game_avgs = {g: sum(scores) / len(scores) for g, scores in games_dict.items()}
            macro_avg = sum(game_avgs.values()) / len(game_avgs) if game_avgs else 0

            method_scores[method] = {
                "macro_p10": macro_avg,
                "by_game": game_avgs,
                "games_tested": list(games_dict.keys()),
            }

        # Find winner
        if method_scores:
            winner = max(method_scores.items(), key=lambda x: x[1]["macro_p10"])
            return winner

        return None, None


def main():
    evaluator = MultiGameEvaluator()

    print(f"\n{'=' * 60}")
    print("Multi-Game Evaluation Framework")
    print("=" * 60)

    print(f"\nGames configured: {evaluator.games}")
    print(f"Test sets available: {list(evaluator.test_sets.keys())}")

    print("\nCurrent best per game:")
    for game, best in evaluator.current_bests.items():
        print(f"  {game}: {best.get('method', 'None')} (P@10: {best.get('p10', 0):.4f})")

    # Find universal winner
    print(f"\n{'=' * 60}")
    print("Cross-Game Analysis:")
    print("=" * 60)

    winner = evaluator.find_universal_winner()
    if winner and winner[0]:
        method, scores = winner
        print(f"\nBest across all games: {method}")
        print(f"  Macro P@10: {scores['macro_p10']:.4f}")
        print(f"  Tested on: {scores['games_tested']}")
        print("  Per-game:")
        for game, p10 in scores["by_game"].items():
            print(f"    {game}: {p10:.4f}")

    print(
        f"\nTotal experiments logged: {sum(1 for _ in open('../../experiments/EXPERIMENT_LOG.jsonl'))}"
    )


if __name__ == "__main__":
    main()
