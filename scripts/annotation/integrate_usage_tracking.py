#!/usr/bin/env python3
"""Integrate usage tracking into training/API/graph scripts.

This script patches existing scripts to add usage tracking calls.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

print("=" * 80)
print("USAGE TRACKING INTEGRATION GUIDE")
print("=" * 80)
print()
print("To integrate usage tracking into your scripts, add these imports and calls:")
print()
print("1. In training scripts (e.g., train_hybrid_full.py):")
print()
print("   from ml.utils.annotation_utils import extract_substitution_pairs_from_annotations")
print("   from scripts.annotation.track_annotation_usage import track_training_usage")
print()
print("   # After loading annotations and extracting pairs:")
print("   pairs = extract_substitution_pairs_from_annotations(annotations)")
print("   track_training_usage(annotation_file, pairs)")
print()
print("2. In API scripts (e.g., api.py):")
print()
print("   from scripts.annotation.track_annotation_usage import track_api_query")
print()
print("   # In similarity endpoint:")
print("   for result in results:")
print("       track_api_query(query, result.card, annotation_file)")
print()
print("3. In graph integration (e.g., integrate_annotations_into_graph.py):")
print()
print("   from scripts.annotation.track_annotation_usage import track_graph_integration")
print()
print("   # After integration:")
print("   track_graph_integration(annotation_file, pairs_integrated)")
print()
print("4. Generate usage reports:")
print()
print("   uv run python3 scripts/annotation/track_annotation_usage.py report")
print()
print("=" * 80)


