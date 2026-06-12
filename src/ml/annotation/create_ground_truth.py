#!/usr/bin/env python3
"""
Create proper ground truth for card similarity evaluation.

Current problem: We evaluate edge prediction but want functional similarity.
Solution: Manual annotation of true card similarities.
"""

from pathlib import Path

import yaml


# Hand-crafted ground truth based on MTG expertise
GROUND_TRUTH = {
    "Lightning Bolt": {
        "substitutes": [  # Functional replacements (4-3 rating)
            "Chain Lightning",
            "Lava Spike",
        ],
        "similar_function": [  # Same role, not exact replacements (3 rating)
            "Fireblast",
            "Lava Dart",
            "Skewer the Critics",
        ],
        "synergies": [  # Work well together, different function (2 rating)
            "Monastery Swiftspear",
            "Eidolon of the Great Revel",
        ],
        "related": [  # Same archetype but different role (1 rating)
            "Goblin Guide",
            "Rift Bolt",
        ],
        "irrelevant": [  # Wrong! (0 rating)
            "Counterspell",
            "Tarmogoyf",
            "Brainstorm",
        ],
    },
    "Brainstorm": {
        "substitutes": ["Ponder", "Preordain"],
        "similar_function": ["Gitaxian Probe", "Portent"],
        "synergies": ["Fetchlands", "Delver of Secrets"],
        "related": ["Force of Will", "Daze"],
        "irrelevant": ["Lightning Bolt", "Dark Ritual"],
    },
    "Dark Ritual": {
        "substitutes": ["Cabal Ritual", "Culling the Weak"],
        "similar_function": ["Lion's Eye Diamond", "Lotus Petal"],
        "synergies": ["Tendrils of Agony", "Ad Nauseam"],
        "related": ["Thoughtseize", "Duress"],
        "irrelevant": ["Lightning Bolt", "Counterspell"],
    },
    "Force of Will": {
        "substitutes": ["Force of Negation", "Pact of Negation"],
        "similar_function": ["Daze", "Flusterstorm"],
        "synergies": ["Brainstorm", "Delver of Secrets"],
        "related": ["Counterspell", "Spell Pierce"],
        "irrelevant": ["Lightning Bolt", "Tarmogoyf"],
    },
    "Delver of Secrets": {
        "substitutes": ["Insectile Aberration"],  # It's literally the same card
        "similar_function": ["Monastery Swiftspear", "Dragon's Rage Channeler"],
        "synergies": ["Brainstorm", "Ponder", "Lightning Bolt"],
        "related": ["Daze", "Force of Will"],
        "irrelevant": ["Tarmogoyf", "Dark Ritual"],
    },
}


def export_ground_truth(output_file="ground_truth.yaml"):
    """Export ground truth in annotation format"""
    tasks = []

    for query, categories in GROUND_TRUTH.items():
        task = {
            "query": query,
            "ground_truth": {
                "highly_relevant": categories.get("substitutes", []),  # 4
                "relevant": categories.get("similar_function", []),  # 3
                "somewhat_relevant": categories.get("synergies", []),  # 2
                "marginally_relevant": categories.get("related", []),  # 1
                "irrelevant": categories.get("irrelevant", []),  # 0
            },
        }
        tasks.append(task)

    with open(output_file, "w") as f:
        yaml.dump({"tasks": tasks}, f, default_flow_style=False)

    print(f"✓ Saved ground truth: {output_file}")
    print(f"  Queries: {len(tasks)}")

    # Also save as JSON for programmatic use
    import json

    test_set = {}
    for task in tasks:
        test_set[task["query"]] = task["ground_truth"]

    json_file = Path(output_file).with_suffix(".json")
    with open(json_file, "w") as f:
        json.dump(test_set, f, indent=2)

    print(f"✓ Saved JSON: {json_file}")


if __name__ == "__main__":
    export_ground_truth("ground_truth_v1.yaml")

    print("\nNext steps:")
    print("  1. python compare_models.py --test-set ground_truth_v1.json --models ../backend/*.wv")
    print("  2. See which method actually matches human judgment")
    print("  3. Deploy that method")
