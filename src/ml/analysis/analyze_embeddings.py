#!/usr/bin/env python3
"""
Deep Analysis of Card Embeddings
- Cluster analysis (find archetypes automatically)
- Format detection (can embeddings predict format?)
- Visualization (t-SNE with archetype coloring)
- Quality metrics (precision@k, coverage)
"""

import argparse
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.manifold import TSNE
from sklearn.metrics import silhouette_score

try:
    from gensim.models import KeyedVectors

    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False
    print("Install gensim: pip install gensim")


def load_embeddings(wv_file):
    """Load trained embeddings"""
    print(f"📚 Loading embeddings from {wv_file}...")
    wv = KeyedVectors.load(wv_file)
    print(f"   Loaded {len(wv):,} card embeddings ({wv.vector_size} dimensions)")
    return wv


def cluster_analysis(wv, n_clusters=20):
    """Find natural clusters in embedding space"""
    print(f"\n🔬 Cluster Analysis (k={n_clusters})...")

    # Get all embeddings
    cards = list(wv.index_to_key)
    X = np.array([wv[card] for card in cards])

    # K-means clustering
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X)

    # Silhouette score (quality of clusters)
    score = silhouette_score(X, labels)
    print(f"   Silhouette score: {score:.3f} (higher is better, range: -1 to 1)")

    # Group cards by cluster
    clusters = defaultdict(list)
    for card, label in zip(cards, labels, strict=False):
        clusters[label].append(card)

    # Show largest clusters
    print("\n   Top 10 clusters by size:")
    sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)

    for i, (cluster_id, cluster_cards) in enumerate(sorted_clusters[:10], 1):
        print(f"   {i:2d}. Cluster {cluster_id:2d}: {len(cluster_cards):4d} cards")
        # Show sample cards
        sample = cluster_cards[:5]
        print(f"       Sample: {', '.join(sample)}")

    return labels, clusters


def archetype_detection(wv, known_archetypes):
    """Test if embeddings can detect known archetypes"""
    print("\n🎯 Archetype Detection Test...")

    results = []

    for archetype_name, seed_cards in known_archetypes.items():
        # Find cards in vocabulary
        valid_seeds = [c for c in seed_cards if c in wv]

        if not valid_seeds:
            print(f"   ⚠️  {archetype_name}: No seed cards in vocabulary")
            continue

        # Average embedding of seed cards
        archetype_emb = np.mean([wv[card] for card in valid_seeds], axis=0)

        # Find most similar cards
        # Compute similarity to all cards
        all_cards = list(wv.index_to_key)
        similarities = {}
        for card in all_cards:
            if card not in valid_seeds:  # Exclude seeds
                sim = np.dot(archetype_emb, wv[card]) / (
                    np.linalg.norm(archetype_emb) * np.linalg.norm(wv[card])
                )
                similarities[card] = sim

        # Top 10
        top_cards = sorted(similarities.items(), key=lambda x: x[1], reverse=True)[:10]

        print(f"\n   📌 {archetype_name} (seeds: {', '.join(valid_seeds)})")
        for j, (card, sim) in enumerate(top_cards, 1):
            bar = "█" * int(sim * 20)
            print(f"      {j:2d}. {card:40s} {bar} {sim:.3f}")

        results.append((archetype_name, valid_seeds, top_cards))

    return results


def coverage_analysis(wv, pairs_csv):
    """Analyze coverage: what cards are in embeddings vs raw graph"""
    print("\n📊 Coverage Analysis...")

    # Load original graph
    df = pd.read_csv(pairs_csv)

    # All unique cards in graph
    all_cards = set(df["NAME_1"]) | set(df["NAME_2"])

    # Cards in embeddings
    emb_cards = set(wv.index_to_key)

    # Analysis
    missing = all_cards - emb_cards
    coverage = len(emb_cards) / len(all_cards) * 100

    print(f"   Cards in original graph: {len(all_cards):,}")
    print(f"   Cards in embeddings: {len(emb_cards):,}")
    print(f"   Coverage: {coverage:.1f}%")
    print(f"   Missing: {len(missing):,} cards")

    if missing and len(missing) < 50:
        print(f"\n   Missing cards: {', '.join(sorted(missing)[:20])}")

    # Analyze edge weight distribution
    print("\n   Edge weight distribution:")
    print(f"   Min co-occurrence: {df['COUNT_SET'].min()}")
    print(f"   Max co-occurrence: {df['COUNT_SET'].max()}")
    print(f"   Mean co-occurrence: {df['COUNT_SET'].mean():.1f}")
    print(f"   Median co-occurrence: {df['COUNT_SET'].median():.1f}")

    # Cards by co-occurrence frequency
    card_freq = defaultdict(int)
    for _, row in df.iterrows():
        card_freq[row["NAME_1"]] += 1
        card_freq[row["NAME_2"]] += 1

    print("\n   Top 10 most connected cards:")
    top_cards = sorted(card_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    for card, count in top_cards:
        print(f"      {card:40s} {count:5d} connections")


def visualize_with_labels(wv, output_file, max_cards=1000):
    """Create labeled t-SNE visualization"""
    print("\n🎨 Creating t-SNE visualization...")

    cards = list(wv.index_to_key)
    X = np.array([wv[card] for card in cards])

    # Sample if needed
    if len(cards) > max_cards:
        indices = np.random.choice(len(cards), max_cards, replace=False)
        cards_sample = [cards[i] for i in indices]
        X_sample = X[indices]
    else:
        cards_sample = cards
        X_sample = X

    # t-SNE
    print(f"   Running t-SNE on {len(cards_sample):,} cards...")
    tsne = TSNE(n_components=2, random_state=42, perplexity=min(50, len(cards_sample) - 1))
    X_2d = tsne.fit_transform(X_sample)

    # Cluster for coloring
    print("   Clustering for visualization...")
    kmeans = KMeans(n_clusters=10, random_state=42, n_init=10)
    cluster_labels = kmeans.fit_predict(X_sample)

    # Plot
    plt.figure(figsize=(24, 18))
    scatter = plt.scatter(X_2d[:, 0], X_2d[:, 1], c=cluster_labels, cmap="tab10", alpha=0.6, s=50)

    # Annotate high-frequency cards
    # TODO: Load frequency from pairs.csv
    for i in range(min(100, len(cards_sample))):
        if i % 10 == 0:  # Every 10th card
            plt.annotate(
                cards_sample[i],
                (X_2d[i, 0], X_2d[i, 1]),
                fontsize=8,
                alpha=0.7,
                bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.7},
            )

    plt.colorbar(scatter, label="Cluster")
    plt.title("Card Embedding Space - Clustered by Archetype", fontsize=18, fontweight="bold")
    plt.xlabel("t-SNE Dimension 1", fontsize=14)
    plt.ylabel("t-SNE Dimension 2", fontsize=14)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_file, dpi=200, bbox_inches="tight")
    print(f"   Saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Deep embedding analysis")
    parser.add_argument("--embeddings", type=str, required=True, help="Path to .wv file")
    parser.add_argument("--pairs", type=str, required=True, help="Path to pairs.csv")
    parser.add_argument("--visualize", action="store_true", help="Create visualization")
    parser.add_argument("--clusters", type=int, default=20, help="Number of clusters")

    args = parser.parse_args()

    if not HAS_GENSIM:
        print("Error: gensim not installed")
        return 1

    # Load embeddings
    wv = load_embeddings(args.embeddings)

    # Coverage analysis
    coverage_analysis(wv, args.pairs)

    # Cluster analysis
    _labels, _clusters = cluster_analysis(wv, n_clusters=args.clusters)

    # Archetype detection
    known_archetypes = {
        "Legacy Storm": ["Dark Ritual", "Lion's Eye Diamond", "Tendrils of Agony"],
        "UR Prowess": ["Monastery Swiftspear", "Dragon's Rage Channeler", "Expressive Iteration"],
        "Blue Cantrips": ["Brainstorm", "Ponder", "Preordain"],
        "Burn": ["Lightning Bolt", "Chain Lightning", "Fireblast"],
        "Pauper Faeries": ["Spellstutter Sprite", "Ninja of the Deep Hours", "Counterspell"],
        "Dredge/Graveyard": ["Faithless Looting", "Stinkweed Imp", "Narcomoeba"],
    }
    archetype_detection(wv, known_archetypes)

    # Visualization
    if args.visualize:
        output_file = Path(args.embeddings).parent / "embeddings_analysis.png"
        visualize_with_labels(wv, str(output_file))

    print("\n✅ Analysis complete!")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
