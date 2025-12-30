#!/usr/bin/env python3
"""Auto-run comparison when all game-specific embeddings complete."""
import sys
from pathlib import Path

script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir.parent.parent))

from ml.scripts.compare_game_specific_vs_multigame import main

if __name__ == "__main__":
    # Check if all embeddings exist
    games = ["magic", "pokemon", "yugioh"]
    all_exist = all(
        Path(f"data/embeddings/{game}_game_specific.wv").exists()
        for game in games
    )
    
    if all_exist:
        print("✅ All game-specific embeddings complete!")
        print("🚀 Running comparison...")
        sys.exit(main())
    else:
        print("⏳ Waiting for all embeddings to complete...")
        missing = [g for g in games if not Path(f"data/embeddings/{g}_game_specific.wv").exists()]
        print(f"   Missing: {', '.join(missing)}")
        sys.exit(1)
