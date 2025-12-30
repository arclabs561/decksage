#!/usr/bin/env python3
"""
exp_009: Word2Vec on Card Sequences

Hypothesis: Treating decks as sentences, cards as words might capture semantics.

Method: word2vec (skip-gram) on deck sequences
- Deck = sentence
- Card = word
- Context window = cards that appear near each other in deck order

vs Node2Vec which uses random walks on co-occurrence graph.

Question: Does deck ORDERING matter for similarity?
"""

import json
import subprocess

from gensim.models import Word2Vec


def load_decks_as_sequences():
    """Load decks, preserving card order"""
    print("Loading decks as sequences...")

    # Extract deck sequences from MTGTop8
    result = subprocess.run(
        ["../backend/dataset", "cat", "magic/mtgtop8", "--bucket", "file://../backend/data-full"],
        check=False,
        capture_output=True,
        text=True,
        cwd=".",
    )

    deck_sequences = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            if data.get("collection"):
                col = data["collection"]

                # Extract card list (preserving partition order)
                deck = []
                for partition in col.get("partitions", []):
                    for card_desc in partition.get("cards", []):
                        # Repeat card based on count (4x Lightning Bolt)
                        deck.extend([card_desc["name"]] * card_desc["count"])

                if deck:
                    deck_sequences.append(deck)
        except:
            continue

    print(f"✓ Loaded {len(deck_sequences)} deck sequences")
    return deck_sequences


def train_word2vec(deck_sequences, dim=128, window=5):
    """Train Word2Vec on deck sequences"""
    print("\nTraining Word2Vec:")
    print(f"  Decks: {len(deck_sequences)}")
    print(f"  Dimensions: {dim}")
    print(f"  Window: {window}")

    model = Word2Vec(
        sentences=deck_sequences,
        vector_size=dim,
        window=window,
        min_count=2,  # Ignore rare cards
        sg=1,  # Skip-gram
        workers=8,
        epochs=10,
    )

    print(f"✓ Trained on {len(model.wv)} cards")
    return model.wv


def main():
    print("=" * 60)
    print("exp_009: Word2Vec on Deck Sequences")
    print("=" * 60)

    # Load decks
    decks = load_decks_as_sequences()

    # Train
    wv = train_word2vec(decks, dim=128, window=5)

    # Save
    wv.save("../../data/embeddings/word2vec_decks.wv")
    print("✓ Saved to word2vec_decks.wv")

    # Test
    queries = ["Lightning Bolt", "Brainstorm", "Sol Ring", "Counterspell"]

    print(f"\n{'=' * 60}")
    print("Results:")
    print("=" * 60)

    for query in queries:
        if query in wv:
            results = wv.most_similar(query, topn=5)
            print(f"\n{query}:")
            for i, (card, score) in enumerate(results, 1):
                print(f"  {i}. {card:40s} {score:.4f}")

    # Log
    with open("../../experiments/EXPERIMENT_LOG.jsonl", "a") as f:
        exp = {
            "experiment_id": "exp_009",
            "date": "2025-10-01",
            "phase": "alternative_embeddings",
            "hypothesis": "Word2Vec on deck sequences captures different signal than Node2Vec on graph",
            "method": "Word2Vec (window=5) on deck card lists",
            "data": f"{len(decks)} deck sequences",
            "key_difference": "Uses deck ordering, not co-occurrence graph",
            "results": {"num_cards": len(wv)},
            "next_steps": ["Compare to Node2Vec and Jaccard", "Try different window sizes"],
        }
        f.write(json.dumps(exp) + "\n")

    print("\n✓ Logged exp_009")


if __name__ == "__main__":
    main()
