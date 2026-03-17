#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "gensim>=4.3.0",
#   "numpy<2.0.0",
#   "scikit-learn>=1.4.0",
#   "scipy>=1.12.0",
# ]
# ///
"""
Build archetype templates from tournament deck corpus.

Clusters decks by card composition (sparse count vectors projected via
embeddings to 32D, then KMeans or HDBSCAN), names each cluster by its
most distinctive cards (TF-IDF), and extracts per-archetype role/curve
templates for use in OT deck completion.

Usage:
    uv run scripts/training/build_archetype_templates.py --game magic --k 25
    uv run scripts/training/build_archetype_templates.py --game magic --auto-k
    uv run scripts/training/build_archetype_templates.py --game pokemon --k 10
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_archetypes")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

MAIN_PARTITION: dict[str, str] = {
    "magic": "Main",
    "yugioh": "Main Deck",
    "pokemon": "Main Deck",
}

# Major card supertypes for Magic type distribution
_MAGIC_TYPE_BUCKETS = [
    ("creature", re.compile(r"\bcreature\b", re.I)),
    ("planeswalker", re.compile(r"\bplaneswalker\b", re.I)),
    ("instant", re.compile(r"\binstant\b", re.I)),
    ("sorcery", re.compile(r"\bsorcery\b", re.I)),
    ("enchantment", re.compile(r"\benchantment\b", re.I)),
    ("artifact", re.compile(r"\bartifact\b", re.I)),
    ("land", re.compile(r"\bland\b", re.I)),
]


@dataclass
class ArchetypeTemplate:
    name: str
    game: str
    cluster_id: int
    deck_count: int
    type_distribution: dict[str, float]
    cmc_histogram: dict[str, float]  # str keys for JSON compat
    color_distribution: dict[str, float]
    core_cards: list[list]  # [[card_name, inclusion_rate], ...]
    flex_cards: list[list]


# ---------------------------------------------------------------------------
# Deck loading
# ---------------------------------------------------------------------------


def _deck_files(game: str) -> list[Path]:
    """Return JSONL deck files for a game, excluding commander/enriched."""
    decks_dir = PROJECT_ROOT / "data" / "decks"
    files = sorted(decks_dir.glob(f"decks_{game}*.jsonl"))
    # Exclude enriched copies and commander (different deck size)
    return [
        f
        for f in files
        if "enriched" not in f.name and "commander" not in f.name and "seq" not in f.name
    ]


def _extract_main_cards(deck: dict, game: str) -> list[tuple[str, int]]:
    """Return [(card_name, count)] for the main partition only."""
    part_name = MAIN_PARTITION.get(game, "Main")
    cards = deck.get("cards", [])
    result = []
    for c in cards:
        if c.get("partition") == part_name:
            name = c.get("name", "").strip()
            count = int(c.get("count", 0))
            if name and count > 0:
                result.append((name, count))
    return result


def load_decks(game: str, max_decks: int = 20000) -> list[list[tuple[str, int]]]:
    """Load decks as lists of (card_name, count) tuples."""
    files = _deck_files(game)
    if not files:
        log.error("No deck files found for game=%s", game)
        sys.exit(1)
    log.info("Loading decks from %d files for %s", len(files), game)

    all_decks: list[list[tuple[str, int]]] = []
    for fpath in files:
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    deck = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Skip metadata lines
                if deck.get("_meta"):
                    continue
                cards = _extract_main_cards(deck, game)
                if len(cards) < 10:
                    continue
                all_decks.append(cards)
    log.info("Loaded %d decks total", len(all_decks))

    if len(all_decks) > max_decks:
        log.info("Sampling %d decks from %d", max_decks, len(all_decks))
        random.seed(42)
        all_decks = random.sample(all_decks, max_decks)

    return all_decks


# ---------------------------------------------------------------------------
# Card attributes
# ---------------------------------------------------------------------------


def load_card_attributes(game: str) -> dict[str, dict]:
    """Load card attributes CSV into {name: {type, colors, cmc, ...}}."""
    # Try enriched first, then bulk, then base
    candidates = [
        f"card_attributes_{game}_enriched.csv",
        f"card_attributes_{game}_bulk.csv",
        f"card_attributes_enriched.csv" if game == "magic" else None,
        f"card_attributes_{game}.csv",
    ]
    attrs_dir = PROJECT_ROOT / "data" / "processed"
    csv_path = None
    for name in candidates:
        if name and (attrs_dir / name).exists():
            csv_path = attrs_dir / name
            break

    if csv_path is None:
        log.warning("No card attributes CSV found for %s", game)
        return {}

    log.info("Loading card attributes from %s", csv_path.name)
    result: dict[str, dict] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if name:
                result[name] = dict(row)
    log.info("Loaded attributes for %d cards", len(result))
    return result


def _card_type_bucket(type_line: str) -> str:
    """Map a Magic type line to its primary bucket."""
    for bucket, pat in _MAGIC_TYPE_BUCKETS:
        if pat.search(type_line):
            return bucket
    return "other"


def _parse_colors(colors_str: str) -> list[str]:
    """Parse color string like 'WU' or 'W, U' into individual colors."""
    if not colors_str or colors_str.strip() in ("", "nan"):
        return []
    # Handle comma-separated or space-separated
    cleaned = colors_str.replace(",", "").replace(" ", "")
    return [c for c in cleaned if c in "WUBRG"]


# ---------------------------------------------------------------------------
# Vectorization and clustering
# ---------------------------------------------------------------------------


def build_deck_matrix(
    decks: list[list[tuple[str, int]]],
    vocab: list[str],
) -> np.ndarray:
    """Build a sparse-ish deck x card count matrix."""
    vocab_idx = {name: i for i, name in enumerate(vocab)}
    n_decks = len(decks)
    n_cards = len(vocab)
    mat = np.zeros((n_decks, n_cards), dtype=np.float32)
    for i, deck in enumerate(decks):
        for name, count in deck:
            if name in vocab_idx:
                mat[i, vocab_idx[name]] = count
    return mat


def project_with_embeddings(
    deck_matrix: np.ndarray,
    vocab: list[str],
    embeddings,
    target_dim: int = 32,
) -> np.ndarray:
    """Project deck count vectors through embedding space, then PCA to target_dim."""
    from sklearn.decomposition import PCA

    emb_dim = embeddings.vector_size
    # Build embedding matrix for vocab
    emb_mat = np.zeros((len(vocab), emb_dim), dtype=np.float32)
    for i, name in enumerate(vocab):
        if name in embeddings:
            emb_mat[i] = embeddings[name]

    # Project: deck_matrix (n_decks, n_cards) @ emb_mat (n_cards, emb_dim)
    # = (n_decks, emb_dim)
    projected = deck_matrix @ emb_mat

    # L2 normalize rows
    norms = np.linalg.norm(projected, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    projected = projected / norms

    # PCA to target_dim
    actual_dim = min(target_dim, projected.shape[0], projected.shape[1])
    if actual_dim < projected.shape[1]:
        pca = PCA(n_components=actual_dim, random_state=42)
        projected = pca.fit_transform(projected)
        explained = sum(pca.explained_variance_ratio_)
        log.info(
            "PCA %dD -> %dD (%.1f%% variance explained)",
            emb_dim,
            actual_dim,
            explained * 100,
        )

    return projected


def cluster_decks(
    features: np.ndarray,
    k: int | None = None,
    auto_k: bool = False,
) -> np.ndarray:
    """Cluster deck feature vectors. Returns integer labels."""
    n = features.shape[0]

    if auto_k:
        try:
            from sklearn.cluster import HDBSCAN

            log.info("Clustering with HDBSCAN (auto cluster count)")
            clusterer = HDBSCAN(min_cluster_size=max(10, n // 200), min_samples=5)
            labels = clusterer.fit_predict(features)
            n_clusters = len(set(labels) - {-1})
            n_noise = int((labels == -1).sum())
            log.info("HDBSCAN found %d clusters, %d noise points", n_clusters, n_noise)
            return labels
        except ImportError:
            log.warning("HDBSCAN not available, falling back to KMeans with k=25")
            k = 25

    if k is None:
        k = 25

    from sklearn.cluster import KMeans

    log.info("Clustering with KMeans k=%d", k)
    km = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=300)
    labels = km.fit_predict(features)
    inertia = km.inertia_
    log.info("KMeans inertia=%.1f", inertia)
    return labels


# ---------------------------------------------------------------------------
# TF-IDF naming
# ---------------------------------------------------------------------------

# Basic lands and energy -- not distinctive for naming
_BASIC_LANDS = {
    "Plains",
    "Island",
    "Swamp",
    "Mountain",
    "Forest",
    "Snow-Covered Plains",
    "Snow-Covered Island",
    "Snow-Covered Swamp",
    "Snow-Covered Mountain",
    "Snow-Covered Forest",
    "Wastes",
}

_BASIC_ENERGY = {
    "Grass Energy",
    "Fire Energy",
    "Water Energy",
    "Lightning Energy",
    "Psychic Energy",
    "Fighting Energy",
    "Darkness Energy",
    "Metal Energy",
    "Fairy Energy",
}

_SKIP_FOR_NAMING = _BASIC_LANDS | _BASIC_ENERGY


def name_clusters(
    decks: list[list[tuple[str, int]]],
    labels: np.ndarray,
    vocab: list[str],
    top_n: int = 3,
) -> dict[int, str]:
    """Name each cluster by its most distinctive cards using TF-IDF."""
    cluster_ids = sorted(set(labels) - {-1})
    vocab_idx = {name: i for i, name in enumerate(vocab)}
    n_vocab = len(vocab)

    # Document frequency: how many clusters contain each card
    cluster_card_presence: dict[int, set[int]] = defaultdict(set)
    # Per-cluster term frequency (total count across all decks in cluster)
    cluster_tf: dict[int, np.ndarray] = {}

    for cid in cluster_ids:
        mask = labels == cid
        deck_indices = np.where(mask)[0]
        tf = np.zeros(n_vocab, dtype=np.float64)
        for di in deck_indices:
            for name, count in decks[di]:
                if name in vocab_idx:
                    idx = vocab_idx[name]
                    tf[idx] += count
                    cluster_card_presence[idx].add(cid)
        # Normalize to mean count per deck
        n_decks = max(1, len(deck_indices))
        tf /= n_decks
        cluster_tf[cid] = tf

    # IDF: log(n_clusters / df)
    n_clusters = len(cluster_ids)
    idf = np.zeros(n_vocab, dtype=np.float64)
    for idx in range(n_vocab):
        df = len(cluster_card_presence.get(idx, set()))
        if df > 0:
            idf[idx] = np.log(n_clusters / df)
        else:
            idf[idx] = 0.0

    names: dict[int, str] = {}
    for cid in cluster_ids:
        tfidf = cluster_tf[cid] * idf
        # Zero out basics and energy
        for name in _SKIP_FOR_NAMING:
            if name in vocab_idx:
                tfidf[vocab_idx[name]] = 0.0
        # Top distinctive cards
        top_indices = np.argsort(-tfidf)[:top_n]
        top_cards = [vocab[i] for i in top_indices if tfidf[i] > 0]
        if top_cards:
            names[cid] = " / ".join(top_cards)
        else:
            names[cid] = f"Cluster {cid}"

    return names


# ---------------------------------------------------------------------------
# Template extraction
# ---------------------------------------------------------------------------


def extract_templates(
    decks: list[list[tuple[str, int]]],
    labels: np.ndarray,
    cluster_names: dict[int, str],
    card_attrs: dict[str, dict],
    game: str,
) -> list[ArchetypeTemplate]:
    """Extract per-archetype templates from clustered decks."""
    cluster_ids = sorted(set(labels) - {-1})
    templates: list[ArchetypeTemplate] = []

    for cid in cluster_ids:
        mask = labels == cid
        deck_indices = np.where(mask)[0]
        n_decks = len(deck_indices)
        if n_decks < 3:
            continue

        # Aggregate card counts across all decks in cluster
        card_counts: Counter[str] = Counter()
        card_presence: Counter[str] = Counter()
        type_counts: Counter[str] = Counter()
        cmc_counts: Counter[int] = Counter()
        color_counts: Counter[str] = Counter()
        total_cards = 0

        for di in deck_indices:
            deck_cards = set()
            for name, count in decks[di]:
                card_counts[name] += count
                deck_cards.add(name)
                total_cards += count

                attrs = card_attrs.get(name, {})
                type_line = attrs.get("type", "")
                if type_line and game == "magic":
                    bucket = _card_type_bucket(type_line)
                    type_counts[bucket] += count
                elif game == "yugioh":
                    # YGO type field contains Monster/Spell/Trap
                    t = type_line.lower()
                    if "monster" in t:
                        type_counts["monster"] += count
                    elif "spell" in t:
                        type_counts["spell"] += count
                    elif "trap" in t:
                        type_counts["trap"] += count
                    else:
                        type_counts["other"] += count

                cmc_str = attrs.get("cmc", "")
                if cmc_str and cmc_str not in ("", "nan"):
                    try:
                        cmc_val = int(float(cmc_str))
                        cmc_counts[cmc_val] += count
                    except (ValueError, TypeError):
                        pass

                colors_str = attrs.get("colors", "")
                for c in _parse_colors(colors_str):
                    color_counts[c] += count

            for name in deck_cards:
                card_presence[name] += 1

        # Normalize distributions
        type_total = sum(type_counts.values()) or 1
        type_dist = {k: round(v / type_total, 4) for k, v in type_counts.most_common()}

        cmc_total = sum(cmc_counts.values()) or 1
        cmc_hist = {str(k): round(v / cmc_total, 4) for k, v in sorted(cmc_counts.items())}

        color_total = sum(color_counts.values()) or 1
        color_dist = {}
        for c in "WUBRG":
            if color_counts[c] > 0:
                color_dist[c] = round(color_counts[c] / color_total, 4)

        # Core/flex thresholds scale with cluster size: large heterogeneous
        # clusters get lower thresholds to still surface defining cards.
        if n_decks > 500:
            core_thresh = 0.3
            flex_thresh = 0.15
        elif n_decks > 100:
            core_thresh = 0.5
            flex_thresh = 0.25
        else:
            core_thresh = 0.7
            flex_thresh = 0.3

        core: list[list] = []
        flex: list[list] = []
        for name, presence in card_presence.most_common():
            rate = presence / n_decks
            if name in _SKIP_FOR_NAMING:
                continue
            if rate > core_thresh:
                core.append([name, round(rate, 3)])
            elif rate > flex_thresh:
                flex.append([name, round(rate, 3)])

        templates.append(
            ArchetypeTemplate(
                name=cluster_names.get(cid, f"Cluster {cid}"),
                game=game,
                cluster_id=int(cid),
                deck_count=n_decks,
                type_distribution=type_dist,
                cmc_histogram=cmc_hist,
                color_distribution=color_dist,
                core_cards=core[:30],
                flex_cards=flex[:30],
            )
        )

    return templates


# ---------------------------------------------------------------------------
# Archetype detection
# ---------------------------------------------------------------------------


def detect_archetype(
    deck_cards: list[tuple[str, int]],
    templates: list[ArchetypeTemplate],
) -> tuple[str, int, float]:
    """
    Detect the closest archetype for a deck by Jaccard overlap with core+flex cards.

    Returns (archetype_name, cluster_id, similarity_score).
    """
    deck_set = {name for name, _ in deck_cards}
    best_name = "Unknown"
    best_id = -1
    best_score = 0.0

    for t in templates:
        template_core = {name for name, _ in t.core_cards}
        template_flex = {name for name, _ in t.flex_cards}
        # Weight core cards 2x
        template_all = template_core | template_flex
        if not template_all:
            continue
        intersection = deck_set & template_all
        core_overlap = len(deck_set & template_core)
        flex_overlap = len(deck_set & template_flex)
        # Weighted score: core matches count double
        score = (2 * core_overlap + flex_overlap) / (
            2 * len(template_core)
            + len(template_flex)
            + len(deck_set)
            - 2 * core_overlap
            - flex_overlap
        )
        if score > best_score:
            best_score = score
            best_name = t.name
            best_id = t.cluster_id

    return best_name, best_id, round(best_score, 4)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Build archetype templates from deck corpus")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--k", type=int, default=None, help="Number of clusters (KMeans)")
    parser.add_argument("--auto-k", action="store_true", help="Use HDBSCAN for automatic k")
    parser.add_argument("--max-decks", type=int, default=20000, help="Max decks to load")
    parser.add_argument("--dim", type=int, default=32, help="PCA target dimension")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON path (default: data/processed/archetype_templates_{game}.json)",
    )
    parser.add_argument(
        "--embeddings",
        type=str,
        default=None,
        help="Path to .wv embeddings file (default: auto-detect latest)",
    )
    args = parser.parse_args()

    game = args.game
    if args.output is None:
        output_path = PROJECT_ROOT / "data" / "processed" / f"archetype_templates_{game}.json"
    else:
        output_path = Path(args.output)

    # Default k per game
    if args.k is None and not args.auto_k:
        default_k = {"magic": 25, "pokemon": 10, "yugioh": 15}
        args.k = default_k.get(game, 20)

    # 1. Load decks
    decks = load_decks(game, max_decks=args.max_decks)
    if not decks:
        log.error("No decks loaded")
        sys.exit(1)

    # 2. Build vocabulary (cards appearing in >= 5 decks)
    card_freq: Counter[str] = Counter()
    for deck in decks:
        seen = set()
        for name, _ in deck:
            if name not in seen:
                card_freq[name] += 1
                seen.add(name)

    min_freq = 5
    vocab = sorted(name for name, freq in card_freq.items() if freq >= min_freq)
    log.info("Vocabulary: %d cards (min_freq=%d)", len(vocab), min_freq)

    # 3. Build deck matrix
    deck_matrix = build_deck_matrix(decks, vocab)

    # 4. Load embeddings and project
    emb_path = args.embeddings
    if emb_path is None:
        # Auto-detect: prefer cleaned/unified v4, then fallback
        emb_dir = PROJECT_ROOT / "data" / "embeddings"
        candidates = [
            f"{game}_cleaned_v4.wv",
            f"{game}_unified_v3.wv",
            f"{game}_unified_v2.wv",
            f"{game}_prone_unified.wv",
            f"{game}_blended.wv",
        ]
        for c in candidates:
            if (emb_dir / c).exists():
                emb_path = str(emb_dir / c)
                break

    if emb_path is None:
        log.error("No embeddings found for %s. Specify --embeddings path.", game)
        sys.exit(1)

    log.info("Loading embeddings from %s", Path(emb_path).name)
    from gensim.models import KeyedVectors

    embeddings = KeyedVectors.load(emb_path)
    log.info("Embeddings: %d vectors, %dD", len(embeddings), embeddings.vector_size)

    features = project_with_embeddings(deck_matrix, vocab, embeddings, target_dim=args.dim)

    # 5. Cluster
    labels = cluster_decks(features, k=args.k, auto_k=args.auto_k)

    # 6. Name clusters
    cluster_names = name_clusters(decks, labels, vocab)

    # 7. Load card attributes
    card_attrs = load_card_attributes(game)

    # 8. Extract templates
    templates = extract_templates(decks, labels, cluster_names, card_attrs, game)
    templates.sort(key=lambda t: t.deck_count, reverse=True)

    # 9. Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "game": game,
        "total_decks": len(decks),
        "total_clusters": len(templates),
        "vocab_size": len(vocab),
        "templates": [asdict(t) for t in templates],
    }
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    log.info("Saved %d templates to %s", len(templates), output_path)

    # 10. Print summary
    print(f"\n{'=' * 70}")
    print(f"Archetype Templates for {game.upper()}")
    print(f"{'=' * 70}")
    print(f"Decks: {len(decks)}, Clusters: {len(templates)}, Vocab: {len(vocab)}")
    print()
    for t in templates[:15]:
        colors = ", ".join(f"{c}={v:.0%}" for c, v in t.color_distribution.items())
        core_preview = ", ".join(name for name, _ in t.core_cards[:3])
        print(f"  [{t.cluster_id:2d}] {t.name}")
        print(f"       {t.deck_count} decks | colors: {colors or 'colorless'}")
        print(f"       core: {core_preview or '(none)'}")
        print()

    if len(templates) > 15:
        print(f"  ... and {len(templates) - 15} more archetypes")
        print()

    # 11. Quick self-test: detect archetype for first deck
    if decks:
        detected_name, detected_id, detected_score = detect_archetype(decks[0], templates)
        print(f"Self-test: first deck detected as '{detected_name}' (score={detected_score})")


if __name__ == "__main__":
    main()
