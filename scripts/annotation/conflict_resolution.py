#!/usr/bin/env python3
"""
Annotation conflict resolution system.

Handles conflicts when multiple annotation sources disagree on the same card pair.
Implements various resolution strategies: majority vote, weighted consensus, expert override.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.utils.annotation_utils import normalize_card_name
    HAS_UTILS = True
except ImportError:
    HAS_UTILS = False
    def normalize_card_name(name: str) -> str:
        return name.strip().lower() if name else ""


class ConflictResolver:
    """Resolve conflicts between multiple annotation sources."""
    
    # Source priority (higher = more trusted)
    SOURCE_PRIORITY = {
        "hand_annotation": 10,  # Expert human annotations
        "user_feedback": 8,     # User feedback from UI
        "llm_judgment": 6,      # Multi-judge LLM
        "llm_generated": 5,     # Single LLM annotation
        "multi_perspective": 7, # Multi-perspective judge
        "browser_annotation": 8, # Browser-based annotation
    }
    
    def __init__(self, strategy: str = "weighted_consensus"):
        """
        Initialize conflict resolver.
        
        Strategies:
        - majority_vote: Use most common value
        - weighted_consensus: Weight by source priority
        - expert_override: Prefer hand_annotation over others
        - conservative: Use lower similarity score
        - aggressive: Use higher similarity score
        """
        self.strategy = strategy
    
    def group_by_pair(self, annotations: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
        """Group annotations by card pair."""
        grouped = defaultdict(list)
        
        for ann in annotations:
            card1 = normalize_card_name(ann.get("card1", ""))
            card2 = normalize_card_name(ann.get("card2", ""))
            
            if not card1 or not card2:
                continue
            
            # Normalize pair (always sorted)
            pair = tuple(sorted([card1, card2]))
            grouped[pair].append(ann)
        
        return dict(grouped)
    
    def resolve_conflicts(
        self,
        annotations: list[dict[str, Any]],
        min_confidence: float = 0.5,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Resolve conflicts in annotations.
        
        Returns:
            (resolved_annotations, conflicts)
        """
        grouped = self.group_by_pair(annotations)
        resolved = []
        conflicts = []
        
        for pair, anns in grouped.items():
            if len(anns) == 1:
                # No conflict
                resolved.append(anns[0])
                continue
            
            # Multiple annotations for same pair - check for conflicts
            similarity_scores = [ann.get("similarity_score", 0) for ann in anns]
            is_substitute_flags = [ann.get("is_substitute", False) for ann in anns]
            
            # Check if there's actual conflict
            score_range = max(similarity_scores) - min(similarity_scores)
            has_score_conflict = score_range > 0.2  # More than 0.2 difference
            has_substitute_conflict = len(set(is_substitute_flags)) > 1
            
            if not has_score_conflict and not has_substitute_conflict:
                # No real conflict, just use first one
                resolved.append(anns[0])
                continue
            
            # Resolve conflict based on strategy
            resolved_ann = self._resolve_conflict(anns, pair)
            
            if resolved_ann:
                resolved.append(resolved_ann)
                
                # Record conflict details
                conflicts.append({
                    "pair": pair,
                    "annotations": anns,
                    "resolved": resolved_ann,
                    "strategy": self.strategy,
                    "score_range": score_range,
                    "has_substitute_conflict": has_substitute_conflict,
                })
        
        return resolved, conflicts
    
    def _resolve_conflict(
        self,
        annotations: list[dict[str, Any]],
        pair: tuple[str, str],
    ) -> dict[str, Any] | None:
        """Resolve a single conflict using the configured strategy."""
        if not annotations:
            return None
        
        if self.strategy == "majority_vote":
            return self._majority_vote(annotations, pair)
        elif self.strategy == "weighted_consensus":
            return self._weighted_consensus(annotations, pair)
        elif self.strategy == "expert_override":
            return self._expert_override(annotations, pair)
        elif self.strategy == "conservative":
            return self._conservative(annotations, pair)
        elif self.strategy == "aggressive":
            return self._aggressive(annotations, pair)
        else:
            # Default: weighted consensus
            return self._weighted_consensus(annotations, pair)
    
    def _majority_vote(
        self,
        annotations: list[dict[str, Any]],
        pair: tuple[str, str],
    ) -> dict[str, Any]:
        """Use most common similarity score."""
        # Round scores to 0.1 precision for voting
        rounded_scores = [round(ann.get("similarity_score", 0), 1) for ann in annotations]
        score_counts = Counter(rounded_scores)
        most_common_score = score_counts.most_common(1)[0][0]
        
        # Find annotation with this score (prefer higher priority source)
        candidates = [ann for ann in annotations if round(ann.get("similarity_score", 0), 1) == most_common_score]
        best = max(candidates, key=lambda a: self.SOURCE_PRIORITY.get(a.get("source", ""), 0))
        
        return best
    
    def _weighted_consensus(
        self,
        annotations: list[dict[str, Any]],
        pair: tuple[str, str],
    ) -> dict[str, Any]:
        """Weight annotations by source priority and compute weighted average."""
        total_weight = 0
        weighted_score = 0
        weighted_substitute = 0
        
        for ann in annotations:
            source = ann.get("source", "")
            weight = self.SOURCE_PRIORITY.get(source, 1)
            score = ann.get("similarity_score", 0)
            is_sub = 1.0 if ann.get("is_substitute", False) else 0.0
            
            total_weight += weight
            weighted_score += score * weight
            weighted_substitute += is_sub * weight
        
        if total_weight == 0:
            return annotations[0]
        
        consensus_score = weighted_score / total_weight
        consensus_substitute = (weighted_substitute / total_weight) >= 0.5
        
        # Use highest priority source as base, update with consensus values
        best_source = max(annotations, key=lambda a: self.SOURCE_PRIORITY.get(a.get("source", ""), 0))
        resolved = best_source.copy()
        resolved["similarity_score"] = round(consensus_score, 3)
        resolved["is_substitute"] = consensus_substitute
        resolved["source"] = "resolved_consensus"
        resolved["conflict_resolution"] = {
            "strategy": "weighted_consensus",
            "num_sources": len(annotations),
            "sources": [ann.get("source") for ann in annotations],
        }
        
        return resolved
    
    def _expert_override(
        self,
        annotations: list[dict[str, Any]],
        pair: tuple[str, str],
    ) -> dict[str, Any]:
        """Prefer hand annotations over all others."""
        hand_anns = [ann for ann in annotations if ann.get("source") == "hand_annotation"]
        if hand_anns:
            return hand_anns[0]
        
        # Fallback to highest priority
        return max(annotations, key=lambda a: self.SOURCE_PRIORITY.get(a.get("source", ""), 0))
    
    def _conservative(
        self,
        annotations: list[dict[str, Any]],
        pair: tuple[str, str],
    ) -> dict[str, Any]:
        """Use lower similarity score (more conservative)."""
        min_score_ann = min(annotations, key=lambda a: a.get("similarity_score", 0))
        resolved = min_score_ann.copy()
        resolved["source"] = "resolved_conservative"
        resolved["conflict_resolution"] = {
            "strategy": "conservative",
            "num_sources": len(annotations),
        }
        return resolved
    
    def _aggressive(
        self,
        annotations: list[dict[str, Any]],
        pair: tuple[str, str],
    ) -> dict[str, Any]:
        """Use higher similarity score (more aggressive)."""
        max_score_ann = max(annotations, key=lambda a: a.get("similarity_score", 0))
        resolved = max_score_ann.copy()
        resolved["source"] = "resolved_aggressive"
        resolved["conflict_resolution"] = {
            "strategy": "aggressive",
            "num_sources": len(annotations),
        }
        return resolved


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Resolve annotation conflicts")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input integrated annotations JSONL file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output resolved annotations JSONL file",
    )
    parser.add_argument(
        "--strategy",
        choices=["majority_vote", "weighted_consensus", "expert_override", "conservative", "aggressive"],
        default="weighted_consensus",
        help="Conflict resolution strategy",
    )
    parser.add_argument(
        "--conflicts-report",
        type=Path,
        help="Output path for conflicts report JSON",
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("ANNOTATION CONFLICT RESOLUTION")
    print("=" * 80)
    print(f"Strategy: {args.strategy}")
    print()
    
    # Load annotations
    annotations = []
    errors = []
    with open(args.input) as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    ann = json.loads(line)
                    # Basic validation
                    if ann.get("card1") and ann.get("card2"):
                        annotations.append(ann)
                    else:
                        errors.append(f"Line {line_num}: Missing card1 or card2")
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {e}")
                    continue
                except Exception as e:
                    errors.append(f"Line {line_num}: Error - {e}")
                    continue
    
    if errors:
        print(f"⚠ {len(errors)} errors encountered while loading:")
        for error in errors[:5]:
            print(f"  {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more errors")
        print()
    
    print(f"Loaded {len(annotations)} annotations")
    
    # Resolve conflicts
    resolver = ConflictResolver(strategy=args.strategy)
    resolved, conflicts = resolver.resolve_conflicts(annotations)
    
    print(f"Resolved: {len(resolved)} annotations")
    print(f"Conflicts found: {len(conflicts)}")
    
    if conflicts:
        print("\nConflicts:")
        for i, conflict in enumerate(conflicts[:10], 1):
            pair = conflict["pair"]
            score_range = conflict["score_range"]
            print(f"  {i}. {pair[0]} <-> {pair[1]}: score_range={score_range:.3f}")
        if len(conflicts) > 10:
            print(f"  ... and {len(conflicts) - 10} more")
    
    # Save resolved annotations (atomic write)
    output_path = args.output or args.input.parent / f"{args.input.stem}_resolved.jsonl"
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with open(temp_path, "w") as f:
            for ann in resolved:
                f.write(json.dumps(ann) + "\n")
        temp_path.replace(output_path)
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        raise
    
    print(f"\n✓ Saved resolved annotations: {output_path}")
    
    # Save conflicts report
    if args.conflicts_report:
        with open(args.conflicts_report, "w") as f:
            json.dump(conflicts, f, indent=2)
        print(f"✓ Saved conflicts report: {args.conflicts_report}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

