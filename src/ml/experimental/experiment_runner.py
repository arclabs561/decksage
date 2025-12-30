#!/usr/bin/env python3
"""
Unified Experiment Runner

Automatically:
- Runs experiment
- Logs to EXPERIMENT_LOG.jsonl
- Compares to baselines
- Saves artifacts
- Generates report
"""

import json
from datetime import datetime
from pathlib import Path


class ExperimentRunner:
    """Run and log experiments systematically"""

    def __init__(self, log_file="../../experiments/EXPERIMENT_LOG.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Load previous experiments
        self.experiments = []
        if self.log_file.exists():
            with open(self.log_file) as f:
                for line in f:
                    self.experiments.append(json.loads(line))

        print(f"Loaded {len(self.experiments)} previous experiments")

    def log_experiment(self, experiment: dict):
        """Append experiment to log"""
        # Auto-assign ID
        if "experiment_id" not in experiment:
            next_id = len(self.experiments) + 1
            experiment["experiment_id"] = f"exp_{next_id:03d}"

        # Auto-add timestamp
        if "date" not in experiment:
            experiment["date"] = datetime.now().strftime("%Y-%m-%d")

        # Append to file
        with open(self.log_file, "a") as f:
            f.write(json.dumps(experiment) + "\n")

        self.experiments.append(experiment)
        print(f"✓ Logged {experiment['experiment_id']}")

    def get_baseline_performance(self):
        """Get best baseline for comparison"""
        baselines = [e for e in self.experiments if e.get("phase") == "baseline"]
        if not baselines:
            return None

        # Find best P@10
        best = max(baselines, key=lambda x: x.get("results", {}).get("p10", 0))
        return best

    def run_experiment(self, config: dict):
        """
        Run experiment with config:
        {
            'hypothesis': str,
            'method': str,
            'phase': str,
            'data': str,
            'train_fn': callable,
            'eval_fn': callable
        }
        """
        print(f"\n{'=' * 60}")
        print(f"Running: {config['method']}")
        print(f"Hypothesis: {config['hypothesis']}")
        print("=" * 60)

        # Train
        print("\nTraining...")
        model = config["train_fn"]()

        # Evaluate
        print("\nEvaluating...")
        results = config["eval_fn"](model)

        # Compare to baseline
        baseline = self.get_baseline_performance()
        if baseline:
            baseline_p10 = baseline["results"].get("p10", 0)
            current_p10 = results.get("p10", 0)
            improvement = (current_p10 / baseline_p10 - 1) * 100 if baseline_p10 > 0 else 0

            print("\nComparison to best baseline:")
            print(f"  Baseline ({baseline['method']}): P@10 = {baseline_p10:.4f}")
            print(f"  Current ({config['method']}): P@10 = {current_p10:.4f}")
            print(f"  Improvement: {improvement:+.1f}%")

        # Log
        experiment = {
            "hypothesis": config["hypothesis"],
            "method": config["method"],
            "phase": config.get("phase", "unknown"),
            "data": config["data"],
            "results": results,
            "baseline_comparison": {
                "baseline": baseline["method"] if baseline else None,
                "improvement_pct": improvement if baseline else None,
            }
            if baseline
            else None,
        }

        self.log_experiment(experiment)

        return results


# Quick test
if __name__ == "__main__":
    runner = ExperimentRunner()

    # Example: Log today's experiments
    runner.log_experiment(
        {
            "phase": "baseline",
            "hypothesis": "Jaccard with land filtering beats unfiltered",
            "method": "Jaccard + land blacklist",
            "data": "500 MTG decks",
            "results": {"p10": 0.83, "accuracy": "83%"},
            "learnings": [
                "Land filtering critical for Jaccard",
                "Hardcoded filter works but brittle",
                "Need Scryfall types for proper solution",
            ],
            "next_steps": ["Fetch Scryfall metadata", "Type-aware filtering"],
        }
    )

    print(f"\nTotal experiments logged: {len(runner.experiments)}")
