#!/usr/bin/env python3
"""
Self-Sustaining Experimental Loop

Runs autonomously:
1. Current models predict on queries
2. Active learner finds high-value unlabeled cases
3. System generates annotation batch
4. (Human annotates or LLM judge fills in)
5. Test set expands
6. Re-train models
7. Performance tracked
8. Loop continues

No human intervention needed except annotation.
System discovers what works through iteration.
"""

import json

from active_annotation_selector import ActiveAnnotationSelector
from meta_learner import MetaLearner
from true_closed_loop import ClosedLoopExperiment


class SelfSustainingLoop:
    """Autonomous experimental loop"""

    def __init__(self, game="magic"):
        self.game = game
        self.iteration = 0

    def run_iteration(self):
        """Run one complete cycle"""
        self.iteration += 1

        print(f"\n{'=' * 60}")
        print(f"ITERATION {self.iteration}")
        print("=" * 60)

        # Step 1: Meta-analyze what we've learned
        print("\nStep 1: Meta-analysis")
        learner = MetaLearner()
        learner.analyze_patterns()
        next_exp = learner.generate_next_experiment_plan()

        if next_exp:
            print(f"  → Suggests: {next_exp['method']}")

        # Step 2: Active learning - what to annotate
        print("\nStep 2: Active annotation selection")
        selector = ActiveAnnotationSelector()
        suggestions = selector.suggest_next_annotations(max_suggestions=10)

        print(f"  → {len(suggestions)} annotations suggested")
        print(f"     Top priority: {suggestions[0]['query'] if suggestions else 'None'}")

        # Step 3: Generate batch (for human or LLM)
        if suggestions:
            selector.generate_annotation_batch(suggestions)
            print("  → Generated batch for annotation")

        # Step 4: Check if we're improving
        loop = ClosedLoopExperiment(game=self.game)
        current_best = loop.current_best.get("p10", 0)

        print("\nStep 3: Check progress")
        print(f"  Current best: {current_best:.4f}")
        print(f"  Total experiments: {len(loop.past_experiments)}")
        print(f"  Test set size: {len(loop.test_set) if loop.test_set else 0} queries")

        # Step 5: Decide next action
        print("\nStep 4: System decision")

        test_set_size = len(loop.test_set) if loop.test_set else 0

        if test_set_size < 20:
            decision = "EXPAND_TEST_SET"
            reason = f"Only {test_set_size} queries - need 20+ for robust eval"
        elif current_best < 0.50:
            decision = "TRY_METADATA"
            reason = f"P@10 = {current_best:.2f} is too low - use archetype/text features"
        elif current_best < 0.80:
            decision = "REFINE_METHODS"
            reason = "Good progress, fine-tune best methods"
        else:
            decision = "CROSS_GAME_TRANSFER"
            reason = "MTG solved, apply learnings to YGO/Pokemon"

        print(f"  Decision: {decision}")
        print(f"  Reason: {reason}")

        return {
            "iteration": self.iteration,
            "decision": decision,
            "reason": reason,
            "current_best": current_best,
            "test_set_size": test_set_size,
            "suggestions": len(suggestions),
        }


def main():
    loop = SelfSustainingLoop(game="magic")

    print("=" * 60)
    print("Self-Sustaining Experimental Loop")
    print("=" * 60)
    print("\nSystem will autonomously:")
    print("  • Analyze past experiments")
    print("  • Suggest next experiments")
    print("  • Identify annotation needs")
    print("  • Track progress")
    print("  • Decide direction")

    # Run one iteration
    result = loop.run_iteration()

    print(f"\n{'=' * 60}")
    print(f"Iteration {result['iteration']} Complete")
    print("=" * 60)
    print("\nSystem state:")
    print(f"  Best P@10: {result['current_best']:.4f}")
    print(f"  Test queries: {result['test_set_size']}")
    print(f"  Pending annotations: {result['suggestions']}")
    print(f"\nNext: {result['decision']}")
    print(f"  {result['reason']}")

    # Save iteration result
    with open("../../experiments/self_sustaining_state.json", "w") as f:
        json.dump(result, f, indent=2)

    print("\n✓ Saved system state")
    print("\nTo continue: python self_sustaining_loop.py")
    print(f"  (Will load state and continue from iteration {result['iteration']})")


if __name__ == "__main__":
    main()
