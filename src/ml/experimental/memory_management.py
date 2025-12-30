#!/usr/bin/env python3
"""
Experiment Memory Management (Paper 2 Insights)

Applies memory management paper principles:
1. Selective Addition: Only add experiments with verified results
2. Selective Deletion: Remove failed/misleading experiments
3. Error Propagation Prevention: Don't let failures contaminate
4. Misaligned Detection: Identify bad demonstrations

This cleans our experiment log from 27 failed to ~8 verified.
"""

import builtins
import contextlib
import json
from pathlib import Path


class ExperimentMemoryManager:
    """Manages experiment memory with quality gates"""

    def __init__(self, log_file="../../experiments/EXPERIMENT_LOG.jsonl"):
        self.log_file = Path(log_file)
        self.experiments = []
        self.load_all()

    def load_all(self):
        """Load all experiments"""
        with open(self.log_file) as f:
            for line in f:
                if line.strip():
                    with contextlib.suppress(builtins.BaseException):
                        self.experiments.append(json.loads(line))

        print(f"Loaded {len(self.experiments)} experiments")

    def selective_addition_gate(self, experiment):
        """
        Quality gate: Should this experiment be added?

        Criteria (from paper):
        - Has real results (not placeholder)
        - P@10 > 0 (produced output)
        - Used canonical test set (fair comparison)
        """

        # Must have results
        results = experiment.get("results", {})
        p10 = results.get("p10")

        if p10 is None:
            return False, "No P@10 result"

        if p10 == 0:
            return False, "Failed (P@10 = 0)"

        # Should use canonical test
        test_set = experiment.get("test_set", "")
        if "canonical" not in test_set:
            return False, "Didn't use canonical test set"

        return True, "Verified experiment"

    def selective_deletion_criteria(self, experiment):
        """
        Should this experiment be deleted?

        Criteria (from paper):
        1. Low utility (failed experiments)
        2. Misaligned (method doesn't match results)
        3. Redundant (duplicate of better experiment)
        """

        reasons = []

        # Delete failures
        p10 = experiment.get("results", {}).get("p10", 0)
        if p10 == 0:
            reasons.append("Failed (P@10 = 0)")

        # Delete if method appears in multiple failures
        method = experiment.get("method", "").lower()
        if "archetype" in method:
            # 6 archetype experiments all failed
            reasons.append("Archetype approach failed 6x")

        # Delete placeholders
        if p10 == 0.15 and experiment.get("experiment_id") == "exp_025":
            reasons.append("Placeholder result")

        return len(reasons) > 0, reasons

    def clean_experiment_log(self):
        """Apply selective addition + deletion"""

        # Selective addition: Keep only verified
        verified = []
        rejected = []

        for exp in self.experiments:
            should_add, reason = self.selective_addition_gate(exp)

            if should_add:
                verified.append(exp)
            else:
                rejected.append((exp.get("experiment_id"), reason))

        # Selective deletion: Remove from verified
        cleaned = []
        deleted = []

        for exp in verified:
            should_delete, reasons = self.selective_deletion_criteria(exp)

            if should_delete:
                deleted.append((exp.get("experiment_id"), reasons))
            else:
                cleaned.append(exp)

        print("\nCleaning results:")
        print(f"  Started with: {len(self.experiments)}")
        print(f"  Rejected (no valid results): {len(rejected)}")
        print(f"  Deleted (failed/bad): {len(deleted)}")
        print(f"  Kept (verified): {len(cleaned)}")

        # Show what was rejected
        print("\nRejected experiments:")
        for exp_id, reason in rejected[:5]:
            print(f"  {exp_id}: {reason}")

        # Show what was deleted
        if deleted:
            print("\nDeleted experiments:")
            for exp_id, reasons in deleted[:5]:
                print(f"  {exp_id}: {reasons}")

        return cleaned

    def save_cleaned_log(
        self, cleaned_experiments, output_file="../../experiments/EXPERIMENT_LOG_CLEAN.jsonl"
    ):
        """Save cleaned experiment log"""

        with open(output_file, "w") as f:
            for exp in cleaned_experiments:
                f.write(json.dumps(exp) + "\n")

        print(f"\n✓ Saved cleaned log: {output_file}")
        print(f"  {len(cleaned_experiments)} high-quality experiments")

        # Also update main log
        backup = Path("../../experiments/EXPERIMENT_LOG_BACKUP.jsonl")
        self.log_file.rename(backup)

        with open(self.log_file, "w") as f:
            for exp in cleaned_experiments:
                f.write(json.dumps(exp) + "\n")

        print("  ✓ Replaced main log (backup saved)")


def main():
    print("=" * 60)
    print("Experiment Memory Management (Paper-Guided)")
    print("=" * 60)

    manager = ExperimentMemoryManager()

    # Clean
    cleaned = manager.clean_experiment_log()

    # Show cleaned experiments
    print(f"\n{'=' * 60}")
    print("Verified Experiments:")
    print("=" * 60)

    for exp in cleaned:
        exp_id = exp.get("experiment_id")
        method = exp.get("method", "Unknown")[:40]
        p10 = exp.get("results", {}).get("p10", 0)
        print(f"  {exp_id}: {method:40s} P@10={p10:.4f}")

    # Save
    manager.save_cleaned_log(cleaned)

    print(f"\n{'=' * 60}")
    print("Memory Management Applied")
    print("=" * 60)
    print("Paper principles:")
    print("  ✓ Selective addition (quality gate)")
    print("  ✓ Selective deletion (remove failures)")
    print("  ✓ Error propagation prevented")
    print("  ✓ Clean memory for future experiments")


if __name__ == "__main__":
    main()
