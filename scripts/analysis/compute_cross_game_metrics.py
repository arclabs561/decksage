#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_adjacency(pairs_csv: Path) -> dict[str, set]:
    adj: dict[str, set] = defaultdict(set)
    with pairs_csv.open("r", encoding="utf-8") as f:
        header = True
        for line in f:
            if header:
                header = False
                continue
            parts = line.rstrip("\n").split(",")
            if len(parts) < 2:
                continue
            a, b = parts[0], parts[1]
            if not a or not b:
                continue
            if a == b:
                continue
            adj[a].add(b)
            adj[b].add(a)
    return adj


def jaccard_topk(query: str, adj: dict[str, set], top_k: int = 10) -> list[tuple[str, float]]:
    if query not in adj:
        return []
    qn = adj[query]
    scores: list[tuple[str, float]] = []
    for other, on in adj.items():
        if other == query:
            continue
        if not on:
            continue
        inter = len(qn & on)
        if inter == 0:
            continue
        uni = len(qn | on)
        if uni <= 0:
            continue
        s = inter / uni
        if s <= 0:
            continue
        scores.append((other, float(s)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


def evaluate_games() -> dict:
    # Import evaluation helper
    import sys

    sys.path.insert(0, str(ROOT / "src" / "ml"))
    from utils.evaluation import evaluate_similarity  # type: ignore

    tests = {
        "magic": ROOT / "experiments" / "test_set_canonical_magic.json",
        "yugioh": ROOT / "experiments" / "test_set_canonical_yugioh.json",
        "pokemon": ROOT / "experiments" / "test_set_canonical_pokemon.json",
    }

    present = {g: p for g, p in tests.items() if p.exists()}
    if not present:
        return {}

    # Build adjacency once
    pairs_csv = ROOT / "src" / "backend" / "pairs.csv"
    adj = build_adjacency(pairs_csv)

    results: dict = {"games": {}, "weighted": {}}
    totals = 0
    num_weighted = 0.0
    for game, tpath in present.items():
        data = load_json(tpath)
        test_set = data.get("queries", {})

        def sim_func(q: str, k: int) -> list[tuple[str, float]]:
            return jaccard_topk(q, adj, top_k=k)

        res = evaluate_similarity(test_set, sim_func, top_k=10, verbose=False)
        results["games"][game] = res
        nq = int(res.get("num_evaluated", 0))
        p10 = float(res.get("p@10", 0.0))
        if nq > 0:
            totals += int((data.get("queries") and len(test_set)) or nq)
            num_weighted += p10 * nq

    if totals > 0:
        results["weighted"]["p@10"] = (
            num_weighted
            / sum(results["games"][g].get("num_evaluated", 0) or 0 for g in results["games"])
            if any(results["games"][g].get("num_evaluated", 0) for g in results["games"])
            else 0.0
        )

    return results


def main() -> int:
    out = ROOT / "experiments" / "cross_game_metrics.json"
    res = evaluate_games()
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"Wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
