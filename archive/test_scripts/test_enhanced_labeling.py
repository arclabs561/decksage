#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-ai>=0.0.12",
# ]
# ///
"""
Quick test of enhanced labeling with improved prompts.
"""

import json
import sys
from pathlib import Path

# Add scripts to path
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

try:
    from generate_labels_enhanced import make_enhanced_label_agent, generate_labels_with_context, load_card_context
    from generate_labels_multi_judge import generate_labels_multi_judge
    HAS_SCRIPTS = True
except ImportError as e:
    print(f"Import error: {e}")
    HAS_SCRIPTS = False

def test_single_query(query: str, num_judges: int = 2):
    """Test label generation for a single query."""
    if not HAS_SCRIPTS:
        print("Scripts not available")
        return

    print(f"\n=== Testing: {query} ===")
    print(f"Using {num_judges} judges with enhanced prompts...")

    try:
        result = generate_labels_multi_judge(query, num_judges=num_judges)

        if result:
            print(f"\n✅ Generated labels:")
            print(f"  Highly relevant: {len(result.get('highly_relevant', []))}")
            print(f"  Relevant: {len(result.get('relevant', []))}")
            print(f"  Somewhat relevant: {len(result.get('somewhat_relevant', []))}")
            print(f"  Marginally relevant: {len(result.get('marginally_relevant', []))}")

            if result.get('highly_relevant'):
                print(f"\n  Examples (highly_relevant): {result['highly_relevant'][:5]}")

            iaa = result.get('iaa', {})
            print(f"\n  IAA: {iaa.get('agreement_rate', 0.0):.2f} ({iaa.get('num_judges', 0)} judges)")
        else:
            print("❌ No labels generated")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Test enhanced labeling on a few queries."""
    test_queries = [
        "Lightning Bolt",
        "Brainstorm",
        "Counterspell",
    ]

    print("Testing enhanced label generation with improved prompts...")
    print("=" * 60)

    for query in test_queries:
        test_single_query(query, num_judges=2)

    print("\n" + "=" * 60)
    print("✅ Test complete")

if __name__ == "__main__":
    main()
