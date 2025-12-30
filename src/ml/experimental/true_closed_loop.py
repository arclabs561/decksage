#!/usr/bin/env python3
"""
True Closed-Loop Experiment System

Every experiment:
1. Loads previous results
2. Compares to best-so-far
3. Uses shared test set
4. Applies accumulated learnings
5. Updates best if improved
"""

import builtins
import contextlib
import json
from datetime import datetime
from pathlib import Path


class ClosedLoopExperiment:
    """Enforces true closed-loop learning"""

    def __init__(self, game="magic"):
        self.game = game
        self.log_file = Path("../../experiments/EXPERIMENT_LOG.jsonl")
        self.best_file = Path(f"../../experiments/CURRENT_BEST_{game}.json")
        self.test_set_file = Path(f"../../experiments/test_set_canonical_{game}.json")

        # Load history
        self.past_experiments = self.load_experiments()
        self.current_best = self.load_current_best()
        self.test_set = self.load_test_set()

        print("Context loaded:")
        print(f"  Past experiments: {len(self.past_experiments)}")
        print(
            f"  Current best: {self.current_best.get('method', 'None')} (P@10: {self.current_best.get('p10', 0):.4f})"
        )
        print(f"  Test queries: {len(self.test_set) if self.test_set else 0}")

    def load_experiments(self):
        """Load all previous experiments"""
        if not self.log_file.exists():
            return []

        experiments = []
        with open(self.log_file) as f:
            for line in f:
                if line.strip():
                    with contextlib.suppress(builtins.BaseException):
                        experiments.append(json.loads(line))
        return experiments

    def load_current_best(self):
        """Load current best method"""
        if not self.best_file.exists():
            return {"method": "None", "p10": 0.0}

        with open(self.best_file) as f:
            return json.load(f)

    def load_test_set(self):
        """Load canonical test set (same for all experiments)"""
        if not self.test_set_file.exists():
            print("  Warning: No canonical test set - experiments not comparable!")
            return None

        with open(self.test_set_file) as f:
            data = json.load(f)
            # Extract just the queries dict
            return data.get("queries", data)

    def run_with_context(self, experiment_fn, experiment_config):
        """
        Run experiment with full context.

        experiment_fn: Function that trains and evaluates
        experiment_config: {method, hypothesis, phase, etc.}
        """
        print(f"\n{'=' * 60}")
        print(f"Running: {experiment_config['method']}")
        print(f"{'=' * 60}")

        # Show what we're building on
        if self.past_experiments:
            recent = self.past_experiments[-3:]
            print("\nBuilding on:")
            for exp in recent:
                print(f"  - {exp.get('experiment_id')}: {exp.get('conclusion', exp.get('method'))}")

        # Show baseline to beat
        print("\nBaseline to beat:")
        print(f"  {self.current_best.get('method')}: P@10 = {self.current_best.get('p10', 0):.4f}")

        # Run experiment (must use self.test_set!)
        print(f"\nRunning on {len(self.test_set) if self.test_set else 0} canonical queries...")
        results = experiment_fn(self.test_set, experiment_config)

        # Compare
        new_p10 = results.get("p10", 0)
        baseline_p10 = self.current_best.get("p10", 0)

        is_improvement = new_p10 > baseline_p10
        improvement_pct = ((new_p10 / baseline_p10) - 1) * 100 if baseline_p10 > 0 else 0

        print("\nResults:")
        print(f"  New method: P@10 = {new_p10:.4f}")
        print(f"  Baseline:   P@10 = {baseline_p10:.4f}")
        print(f"  Change:     {improvement_pct:+.1f}%")
        print(f"  Improved:   {'YES ✓' if is_improvement else 'NO'}")

        # Update best if improved
        if is_improvement:
            self.current_best = {
                "method": experiment_config["method"],
                "experiment_id": experiment_config.get("experiment_id"),
                "p10": new_p10,
                "date": datetime.now().isoformat(),
            }

            with open(self.best_file, "w") as f:
                json.dump(self.current_best, f, indent=2)

            print("\n★ NEW BEST METHOD ★")

        # Log experiment
        experiment_record = {
            **experiment_config,
            "results": results,
            "baseline_comparison": {
                "baseline_method": self.current_best.get("method"),
                "baseline_p10": baseline_p10,
                "new_p10": new_p10,
                "improvement_pct": improvement_pct,
                "is_improvement": is_improvement,
            },
            "test_set": "canonical_test_set.json",
            "num_previous_experiments": len(self.past_experiments),
        }

        with open(self.log_file, "a") as f:
            f.write(json.dumps(experiment_record) + "\n")

        print(f"\n✓ Logged {experiment_config.get('experiment_id')}")

        return results


# Example usage
if __name__ == "__main__":
    loop = ClosedLoopExperiment()

    print(f"\n{'=' * 60}")
    print("CLOSED-LOOP STATUS")
    print("=" * 60)
    print("\nSystem is operational:")
    print(f"  • Loads {len(loop.past_experiments)} past experiments")
    print(f"  • Knows current best: {loop.current_best.get('method')}")
    print(f"  • Has canonical test set: {loop.test_set is not None}")
    print("  • Auto-compares to baseline")
    print("  • Updates best when improved")
    print("\nInformation truly flows through time!")
