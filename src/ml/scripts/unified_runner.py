#!/usr/bin/env python3
"""
Unified script runner for ML operations.
Provides consistent interface for common operations.
"""
import sys
from pathlib import Path

# Set up project paths
from ml.utils.path_setup import setup_project_paths
setup_project_paths()

def main():
    if len(sys.argv) < 2:
        print("Usage: python unified_runner.py <operation> [args...]")
        print("Operations: evaluate, train, label, process")
        return 1
    
    operation = sys.argv[1]
    args = sys.argv[2:]
    
    # Route to appropriate script
    if operation == "evaluate":
        from ml.scripts.evaluate_all_embeddings import main as eval_main
        return eval_main()
    elif operation == "train":
        print("Training operations - use runctl for orchestration")
        return 0
    elif operation == "label":
        print("Labeling operations - use generate_labels_enhanced.py")
        return 0
    else:
        print(f"Unknown operation: {operation}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
