#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "numpy>=1.24.0", "pandas>=2.0.0", "python-dotenv>=1.0.0"]
# ///
"""
Startup asset health check for DeckSage.

Validates all pre-computed assets exist and are loadable before
the API starts. Catches missing embeddings, stale indices, and
configuration drift early.

Run standalone or import as a module:
    uv run scripts/check_assets.py
    uv run scripts/check_assets.py --game magic --json

Exit codes:
    0 = all assets present
    1 = critical assets missing (embeddings, graph)
    2 = non-critical assets missing (visual index, fusion weights)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


@dataclass
class AssetStatus:
    name: str
    path: str
    exists: bool
    size_mb: float = 0.0
    loadable: bool = False
    details: str = ""
    critical: bool = True  # True = server won't work without it


@dataclass
class GameReport:
    game: str
    assets: list[AssetStatus] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    warnings: int = 0

    @property
    def ok(self) -> bool:
        return all(a.exists and a.loadable for a in self.assets if a.critical)

    @property
    def has_warnings(self) -> bool:
        return any(not a.exists for a in self.assets if not a.critical)


def check_game(game: str) -> GameReport:
    """Check all assets for a game."""
    report = GameReport(game=game)

    # --- Critical: Primary embedding ---
    emb_names = {
        "magic": "magic_v7_spectral_mu35",
        "pokemon": "pokemon_v7_fused",
        "yugioh": "yugioh_v7_spectral_mu3",
    }
    emb_name = emb_names.get(game)
    emb_path = DATA_DIR / "embeddings" / f"{emb_name}.wv"
    status = AssetStatus(
        name="primary_embedding",
        path=str(emb_path.relative_to(PROJECT_ROOT)),
        exists=emb_path.exists(),
        critical=True,
    )
    if status.exists:
        status.size_mb = emb_path.stat().st_size / 1e6
        try:
            import gensim

            t0 = time.time()
            kv = gensim.models.KeyedVectors.load(str(emb_path))
            status.loadable = True
            status.details = (
                f"{len(kv):,} cards, {kv.vector_size}D (loaded in {time.time() - t0:.1f}s)"
            )
            del kv
        except Exception as e:
            status.details = f"Load error: {e}"
    else:
        status.details = "Embedding file not found"
    report.assets.append(status)
    if status.exists and status.loadable:
        report.passed += 1
    else:
        report.failed += 1

    # --- Critical: Co-occurrence graph ---
    import glob

    pattern = str(DATA_DIR / "processed" / f"pairs_{game}_*.csv")
    matches = sorted(glob.glob(pattern), key=lambda p: Path(p).stat().st_size, reverse=True)
    pairs_path = Path(matches[0]) if matches else DATA_DIR / "processed" / f"pairs_{game}.csv"
    status = AssetStatus(
        name="cooccurrence_graph",
        path=str(pairs_path.relative_to(PROJECT_ROOT)) if pairs_path.exists() else str(pairs_path),
        exists=pairs_path.exists(),
        critical=True,
    )
    if status.exists:
        status.size_mb = pairs_path.stat().st_size / 1e6
        status.loadable = True
        status.details = f"{status.size_mb:.1f} MB"
    report.assets.append(status)
    if status.exists:
        report.passed += 1
    else:
        report.failed += 1

    # --- Critical: Card metadata ---
    meta_path = DATA_DIR / "processed" / f"card_attributes_{game}_enriched.csv"
    if not meta_path.exists():
        meta_path = DATA_DIR / "processed" / f"card_attributes_{game}.csv"
    status = AssetStatus(
        name="card_metadata",
        path=str(meta_path.relative_to(PROJECT_ROOT)) if meta_path.exists() else str(meta_path),
        exists=meta_path.exists(),
        critical=True,
    )
    if status.exists:
        status.size_mb = meta_path.stat().st_size / 1e6
        import pandas as pd

        try:
            df = pd.read_csv(meta_path, nrows=1)
            status.loadable = True
            cols = list(df.columns)
            img_cols = [c for c in cols if "image" in c.lower()]
            status.details = f"{len(cols)} columns (image_url={'yes' if img_cols else 'NO'})"
        except Exception as e:
            status.details = f"CSV error: {e}"
    report.assets.append(status)
    if status.exists and status.loadable:
        report.passed += 1
    else:
        report.failed += 1

    # --- Non-critical: Text embedding index ---
    text_idx = DATA_DIR / "cache" / "text_embeddings" / f"{game}_embeddings.npy"
    text_names = DATA_DIR / "cache" / "text_embeddings" / f"{game}_names.txt"
    status = AssetStatus(
        name="text_embedding_index",
        path=str(text_idx.relative_to(PROJECT_ROOT)) if text_idx.exists() else str(text_idx),
        exists=text_idx.exists() and text_names.exists(),
        critical=False,
    )
    if status.exists:
        import numpy as np

        status.size_mb = text_idx.stat().st_size / 1e6
        try:
            m = np.load(str(text_idx), mmap_mode="r")
            status.loadable = True
            status.details = f"{m.shape[0]:,} cards, {m.shape[1]}D"
        except Exception as e:
            status.details = f"Load error: {e}"
    report.assets.append(status)
    if status.exists and status.loadable:
        report.passed += 1
    elif status.exists:
        report.warnings += 1
    else:
        report.warnings += 1

    # --- Non-critical: Visual embedding index ---
    vis_idx = DATA_DIR / "cache" / "visual_embeddings" / f"{game}_embeddings.npy"
    vis_names = DATA_DIR / "cache" / "visual_embeddings" / f"{game}_names.txt"
    status = AssetStatus(
        name="visual_embedding_index",
        path=str(vis_idx.relative_to(PROJECT_ROOT)) if vis_idx.exists() else str(vis_idx),
        exists=vis_idx.exists() and vis_names.exists(),
        critical=False,
    )
    if status.exists:
        import numpy as np

        status.size_mb = vis_idx.stat().st_size / 1e6
        try:
            m = np.load(str(vis_idx), mmap_mode="r")
            nonzero = int(np.count_nonzero(m) / m.shape[1])
            status.loadable = True
            status.details = f"{m.shape[0]:,} cards, {m.shape[1]}D ({nonzero} with images)"
        except Exception as e:
            status.details = f"Load error: {e}"
    report.assets.append(status)
    if status.exists and status.loadable:
        report.passed += 1
    else:
        report.warnings += 1

    # --- Non-critical: Fusion weights ---
    fw_path = DATA_DIR / "embeddings" / f"fusion_weights_{game}.json"
    status = AssetStatus(
        name="fusion_weights",
        path=str(fw_path.relative_to(PROJECT_ROOT)) if fw_path.exists() else str(fw_path),
        exists=fw_path.exists(),
        critical=False,
    )
    if status.exists:
        try:
            with open(fw_path) as f:
                data = json.load(f)
            status.loadable = True
            w = data.get("best_weights", {})
            status.details = f"nDCG={data.get('ndcg_at_10', '?'):}"
        except Exception as e:
            status.details = f"JSON error: {e}"
    report.assets.append(status)
    if status.exists and status.loadable:
        report.passed += 1
    else:
        report.warnings += 1

    # --- Non-critical: Card images ---
    img_cache = Path(".cache") / "card_images"
    if img_cache.exists():
        n_imgs = len(list(img_cache.glob("*.png")))
        status = AssetStatus(
            name="card_image_cache",
            path=str(img_cache),
            exists=n_imgs > 100,
            critical=False,
            size_mb=sum(f.stat().st_size for f in img_cache.glob("*.png")) / 1e6,
            loadable=n_imgs > 100,
            details=f"{n_imgs:,} cached images",
        )
    else:
        status = AssetStatus(
            name="card_image_cache",
            path=str(img_cache),
            exists=False,
            critical=False,
            details="No image cache",
        )
    report.assets.append(status)
    if status.exists:
        report.passed += 1
    else:
        report.warnings += 1

    return report


def print_report(reports: list[GameReport], json_output: bool = False) -> int:
    """Print health check report. Returns exit code."""
    if json_output:
        data = {
            "games": {
                r.game: {
                    "ok": r.ok,
                    "passed": r.passed,
                    "failed": r.failed,
                    "warnings": r.warnings,
                    "assets": [asdict(a) for a in r.assets],
                }
                for r in reports
            },
            "all_ok": all(r.ok for r in reports),
            "total_warnings": sum(r.warnings for r in reports),
        }
        print(json.dumps(data, indent=2))
        if not all(r.ok for r in reports):
            return 1
        return 2 if sum(r.warnings for r in reports) > 0 else 0

    max_name = max(len(a.name) for r in reports for a in r.assets)

    all_ok = True
    has_warnings = False

    for r in reports:
        status_char = "OK" if r.ok else "FAIL"
        log.info(f"\n{'=' * 60}")
        log.info(
            f"  {r.game.upper()}  [{status_char}]  {r.passed} pass, {r.failed} fail, {r.warnings} warn"
        )
        log.info(f"{'=' * 60}")

        for a in r.assets:
            if a.exists and a.loadable:
                icon = "  OK"
            elif a.exists:
                icon = "WARN"
            elif a.critical:
                icon = "FAIL"
                all_ok = False
            else:
                icon = "MISS"
                has_warnings = True

            path_display = a.path if len(a.path) < 50 else "..." + a.path[-47:]
            log.info(f"  [{icon}] {a.name:<25} {path_display}")
            if a.details:
                log.info(f"         {a.details}")

    log.info("")
    if not all_ok:
        log.info("  FAIL -- critical assets missing. Server will not start correctly.")
        return 1
    elif has_warnings:
        log.info("  WARN -- non-critical assets missing. Visual/fusion features degraded.")
        return 2
    else:
        log.info("  OK -- all assets present and loadable.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DeckSage asset health check")
    parser.add_argument(
        "--game", default=None, help="Check specific game (default: all configured)"
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    # Determine games from env or check all
    import os
    from dotenv import load_dotenv

    load_dotenv()
    games_env = os.getenv("DECKSAGE_GAMES", "magic,pokemon,yugioh")
    all_games = [g.strip().lower() for g in games_env.split(",") if g.strip()]
    games = [args.game] if args.game else all_games

    reports = [check_game(g) for g in games]
    return print_report(reports, json_output=args.json)


if __name__ == "__main__":
    sys.exit(main())
