#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Master pipeline: Orchestrates all tasks for comprehensive evaluation.

1. Fix vocabulary mismatches
2. Expand test sets for all games
3. Create downstream test data
4. Train multi-game embeddings
5. Run comprehensive evaluation
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n{'='*70}")
    print(f"{description}")
    print(f"{'='*70}")
    print(f"Running: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def main() -> int:
    """Run master pipeline."""
    parser = argparse.ArgumentParser(description="Master evaluation pipeline")
    parser.add_argument("--skip-vocab", action="store_true", help="Skip vocabulary fixing")
    parser.add_argument("--skip-expand", action="store_true", help="Skip test set expansion")
    parser.add_argument("--skip-downstream", action="store_true", help="Skip downstream test data creation")
    parser.add_argument("--skip-training", action="store_true", help="Skip training")
    parser.add_argument("--skip-eval", action="store_true", help="Skip evaluation")
    parser.add_argument("--embedding", type=str, help="Embedding file to evaluate (if skipping training)")
    
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent.parent
    
    # Import PATHS once at the top
    from ml.utils.paths import PATHS
    
    # Step 1: Fix vocabulary mismatches
    if not args.skip_vocab:
        for game in ["magic", "pokemon", "yugioh"]:
            # Use unified test sets (recommended)
            test_set = getattr(PATHS, f"test_{game}")
            # Use PATHS for pairs (magic uses pairs_large, others may have game-specific files)
            pairs_csv = PATHS.pairs_large if game == "magic" else (PATHS.processed / f"pairs_{game}.csv")
            
            if test_set.exists() and pairs_csv.exists():
                success = run_command(
                    ["uv", "run", "--script", "src/ml/scripts/fix_vocabulary_mismatch.py",
                     "--test-set", str(test_set),
                     "--pairs-csv", str(pairs_csv),
                     "--name-mapping", "experiments/name_mapping.json",
                     "--threshold", "0.80"],
                    f"Fixing vocabulary for {game}",
                )
                if not success:
                    print(f"Warning: Vocabulary fixing failed for {game}, continuing...")
    
    # Step 2: Expand test sets
    if not args.skip_expand:
        success = run_command(
            ["uv", "run", "--script", "src/ml/scripts/expand_test_set_multi_game.py",
             "--games", "magic", "pokemon", "yugioh",
             "--num-judges", "3",
             "--magic-target", "150",
             "--pokemon-target", "50",
             "--yugioh-target", "50"],
            "Expanding test sets for all games",
        )
        if not success:
            print("Warning: Test set expansion failed, continuing...")
    
    # Step 3: Create downstream test data
    if not args.skip_downstream:
        for game in ["magic", "pokemon", "yugioh"]:
            # Use unified test sets (recommended)
            test_set = getattr(PATHS, f"test_{game}")
            # Use PATHS for pairs (magic uses pairs_large, others may have game-specific files)
            pairs_csv = PATHS.pairs_large if game == "magic" else (PATHS.processed / f"pairs_{game}.csv")
            
            if test_set.exists() and pairs_csv.exists():
                success = run_command(
                    ["uv", "run", "--script", "src/ml/scripts/create_downstream_test_data.py",
                     "--game", game,
                     "--pairs-csv", str(pairs_csv),
                     "--test-set", str(test_set),
                     "--output-dir", "experiments/downstream_tests"],
                    f"Creating downstream test data for {game}",
                )
                if not success:
                    print(f"Warning: Downstream test data creation failed for {game}, continuing...")
    
    # Step 4: Train embeddings (if needed)
    embedding_path = args.embedding
    if not args.skip_training and not embedding_path:
        # Train multi-game embeddings
        pairs_multi_game = PATHS.data / "processed" / "pairs_multi_game.csv"
        if pairs_multi_game.exists():
            print("\n" + "="*70)
            print("Training multi-game embeddings")
            print("="*70)
            print("Warning: Multi-game training not yet implemented in master pipeline")
            print(" Run manually: just train-multi-game")
        else:
            print("Warning: Multi-game pairs not found, skipping multi-game training")
    
    # Step 5: Comprehensive evaluation
    if not args.skip_eval:
        if not embedding_path:
            # Use latest trained embedding
            embedding_path = str(PATHS.embeddings / "trained_validated.wv")
        
        if Path(embedding_path).exists():
            success = run_command(
                ["uv", "run", "--script", "src/ml/scripts/comprehensive_evaluation_pipeline.py",
                 "--embedding", embedding_path,
                 "--output", str(PATHS.experiments / "evaluation_comprehensive.json"),
                 "--test-sets", f"magic:{PATHS.test_magic}",
                 f"pokemon:{PATHS.test_pokemon}",
                 f"yugioh:{PATHS.test_yugioh}",
                 "--downstream"],
                "Running comprehensive evaluation",
            )
        else:
            print(f"Warning: Embedding not found: {embedding_path}, skipping evaluation")
    
    print("\n" + "="*70)
    print("MASTER PIPELINE COMPLETE")
    print("="*70)
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

