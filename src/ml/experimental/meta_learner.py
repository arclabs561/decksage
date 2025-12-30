#!/usr/bin/env python3
"""
Meta-Learner: Closes the loop

Reads ALL experiments, extracts patterns, generates next experiments.

Closed-loop cycle:
1. Read experiment_log.jsonl
2. Analyze what worked/failed
3. Identify patterns
4. Suggest next experiments
5. Update method implementations
"""

import json
from collections import defaultdict
from pathlib import Path


class MetaLearner:
    """Learns from all experiments to guide future ones"""

    def __init__(self, log_file="../../experiments/EXPERIMENT_LOG.jsonl", game="magic"):
        self.log_file = Path(log_file)
        self.game = game
        self.best_file = Path(f"../../experiments/CURRENT_BEST_{game}.json")
        self.experiments = []
        self.current_best = None
        self.load_all()
        self.load_best()

    def load_best(self):
        """Load current best to inform suggestions"""
        if self.best_file.exists():
            with open(self.best_file) as f:
                self.current_best = json.load(f)
                print(
                    f"  Current best: {self.current_best.get('method')} (P@10: {self.current_best.get('p10', 0):.4f})"
                )

    def load_all(self):
        """Load and parse all experiments"""
        if not self.log_file.exists():
            print("No experiment log found")
            return

        with open(self.log_file) as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    self.experiments.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"  Warning: Skipping malformed line {i}: {e}")
                    continue

        print(f"Loaded {len(self.experiments)} experiments")

    def analyze_patterns(self):
        """Extract meta-learnings from all experiments"""

        patterns = {
            "successful_methods": [],
            "failed_methods": [],
            "data_scaling_effects": [],
            "consistent_findings": [],
            "contradictions": [],
        }

        # Group by phase
        by_phase = defaultdict(list)
        for exp in self.experiments:
            phase = exp.get("phase", "unknown")
            by_phase[phase].append(exp)

        print("\nPatterns by Phase:")
        print("=" * 60)

        for phase, exps in sorted(by_phase.items()):
            print(f"\n{phase}: {len(exps)} experiments")

            # Extract learnings
            all_learnings = []
            for exp in exps:
                learnings = exp.get("learnings", [])
                if isinstance(learnings, list):
                    all_learnings.extend(learnings)
                elif isinstance(learnings, str):
                    all_learnings.append(learnings)

            if all_learnings:
                print("  Key learnings:")
                for learning in all_learnings[:3]:  # Top 3
                    print(f"    • {learning}")

        # Find consistent patterns
        print(f"\n{'=' * 60}")
        print("Consistent Findings Across Experiments:")
        print("=" * 60)

        learning_counts = defaultdict(int)
        for exp in self.experiments:
            for learning in exp.get("learnings", []):
                if isinstance(learning, str):
                    # Fuzzy matching (simple version)
                    if "jaccard" in learning.lower():
                        learning_counts["Jaccard works well"] += 1
                    if "land" in learning.lower() and "filter" in learning.lower():
                        learning_counts["Land filtering needed"] += 1
                    if "format" in learning.lower():
                        learning_counts["Format matters"] += 1
                    if "bias" in learning.lower():
                        learning_counts["Selection/evaluation bias"] += 1

        for pattern, count in sorted(learning_counts.items(), key=lambda x: x[1], reverse=True):
            if count >= 2:
                print(f"  {pattern}: mentioned in {count} experiments")

        return patterns

    def suggest_next_experiments(self):
        """Based on all learnings AND research, what should we try next?"""

        # Check what we've tried
        {exp.get("method", "") for exp in self.experiments}
        {exp.get("phase", "") for exp in self.experiments}

        # Check for research findings
        lit_review = [e for e in self.experiments if e.get("phase") == "literature_review"]

        suggestions = []

        # PRIORITY 1: Know what to beat
        current_p10 = self.current_best.get("p10", 0) if self.current_best else 0

        # PRIORITY 2: Research showed meta statistics alone = 42% (we're at ~12%)
        meta_stats_exps = [
            e
            for e in self.experiments
            if "pick rate" in str(e).lower() or "win rate" in str(e).lower()
        ]
        if not meta_stats_exps and lit_review and current_p10 < 0.40:
            suggestions.append(
                {
                    "priority": "CRITICAL",
                    "experiment": "Compute real meta statistics (card win rates from placement)",
                    "reason": f"Papers: 42%, We: {current_p10:.2f}. Meta stats are missing signal.",
                    "expected_impact": f"Target: 0.40+ (currently {current_p10:.2f})",
                    "baseline_to_beat": current_p10,
                    "from_research": True,
                }
            )

        # Check for archetype usage
        archetype_exps = [e for e in self.experiments if "archetype" in str(e).lower()]
        if not archetype_exps:
            suggestions.append(
                {
                    "priority": "HIGH",
                    "experiment": "Archetype-conditioned embeddings",
                    "reason": "MTGTop8 provides free archetype labels",
                    "expected_impact": "Format-specific similarity",
                }
            )

        # Check for win-rate usage
        placement_exps = [
            e for e in self.experiments if "placement" in str(e).lower() or "win" in str(e).lower()
        ]
        if not placement_exps:
            suggestions.append(
                {
                    "priority": "MEDIUM",
                    "experiment": "Win-rate weighted edges",
                    "reason": "Cards from winning decks should have higher weight",
                    "expected_impact": 'Learn "good cards" not just popular',
                }
            )

        return suggestions

    def generate_next_experiment_plan(self):
        """Automatically generate next experiment config"""
        suggestions = self.suggest_next_experiments()

        if not suggestions:
            return None

        # Take highest priority
        next_exp = suggestions[0]

        # Get next experiment ID
        max_id = 0
        for e in self.experiments:
            exp_id = e.get("experiment_id", "")
            if exp_id.startswith("exp_"):
                try:
                    # Handle both exp_001 and exp_008_revised
                    num_part = exp_id[4:].split("_")[0]
                    max_id = max(max_id, int(num_part))
                except:
                    pass
        next_id = max_id + 1

        plan = {
            "experiment_id": f"exp_{next_id:03d}",
            "generated_by": "meta_learner",
            "priority": next_exp["priority"],
            "hypothesis": next_exp["reason"],
            "expected_impact": next_exp["expected_impact"],
            "method": next_exp["experiment"],
            "status": "planned",
            "builds_on": [e["experiment_id"] for e in self.experiments[-3:]],  # Last 3
        }

        return plan


def main():
    learner = MetaLearner()

    print("\n" + "=" * 60)
    print("META-ANALYSIS: Learning from All Experiments")
    print("=" * 60)

    # Analyze
    learner.analyze_patterns()

    # Suggest next
    print(f"\n{'=' * 60}")
    print("Suggested Next Experiments:")
    print("=" * 60)

    suggestions = learner.suggest_next_experiments()
    for i, sug in enumerate(suggestions, 1):
        print(f"\n{i}. {sug['experiment']} [{sug['priority']}]")
        print(f"   Reason: {sug['reason']}")
        print(f"   Impact: {sug['expected_impact']}")

    # Generate plan
    next_plan = learner.generate_next_experiment_plan()
    if next_plan:
        print(f"\n{'=' * 60}")
        print(f"Auto-Generated Plan: {next_plan['experiment_id']}")
        print("=" * 60)
        print(json.dumps(next_plan, indent=2))

        # Save
        plan_file = Path(f"../../experiments/{next_plan['experiment_id']}_plan.json")
        with open(plan_file, "w") as f:
            json.dump(next_plan, f, indent=2)
        print(f"\n✓ Saved: {plan_file}")


if __name__ == "__main__":
    main()
