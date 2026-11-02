"""Data-plane topology: expand the spec and assess freshness.

The spec lives in config/topology.toml; the API serves this assessment and the
ops CLI exits non-zero when an artifact is missing or older than its inputs.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "config" / "topology.toml"


def load_spec(path: Path = SPEC) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def expand(spec: dict) -> list[dict]:
    """Expand {game} placeholders and drop nodes that exclude a game."""
    games: list[str] = spec.get("games", [])
    nodes: list[dict] = []
    seen: set[str] = set()
    for raw in spec.get("node", []):
        template = dict(raw)
        for game in games:
            if "only" in template and game not in template["only"]:
                continue
            if "exclude" in template and game in template["exclude"]:
                continue
            node = {
                key: (value.format(game=game) if isinstance(value, str) else value)
                for key, value in template.items()
                if key not in ("only", "exclude")
            }
            if isinstance(node.get("inputs"), list):
                node["inputs"] = [
                    item.format(game=game) if isinstance(item, str) else item
                    for item in node["inputs"]
                ]
            # A template without {game} expands once per game to the same id.
            if node["id"] in seen:
                continue
            seen.add(node["id"])
            nodes.append(node)
    return nodes


def assess(spec: dict, root: Path = ROOT) -> dict:
    nodes = expand(spec)
    by_id = {node["id"]: node for node in nodes}
    findings: dict[str, list[str]] = {"missing": [], "stale": [], "unknown_inputs": []}

    for node in nodes:
        node["kind"] = node.get("kind", "file")
        node["exists"] = None
        node["mtime"] = None
        for dependency in node.get("inputs", []):
            if dependency not in by_id:
                findings["unknown_inputs"].append(f"{node['id']} <- {dependency}")
        if node["kind"] != "file":
            continue
        path = root / node["path"]
        node["exists"] = path.exists()
        if not node["exists"]:
            findings["missing"].append(node["id"])
            continue
        node["mtime"] = path.stat().st_mtime
        newest_input = 0.0
        for dependency in node.get("inputs", []):
            parent = by_id.get(dependency)
            if not parent or parent.get("mtime") is None:
                continue
            newest_input = max(newest_input, parent["mtime"])
        node["stale"] = newest_input > node["mtime"] + 1.0
        if node["stale"]:
            findings["stale"].append(node["id"])

    order = _topological_order(nodes)
    findings["cycles"] = [] if order is not None else ["graph has a cycle"]
    edges = [
        {"from": dependency, "to": node["id"]}
        for node in nodes
        for dependency in node.get("inputs", [])
        if dependency in by_id
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "findings": findings,
        "order": order or [],
        "ok": not any(findings[key] for key in ("missing", "stale", "unknown_inputs", "cycles")),
    }


def _topological_order(nodes: list[dict]) -> list[str] | None:
    remaining = {node["id"]: set(node.get("inputs", [])) for node in nodes}
    order: list[str] = []
    while remaining:
        pending = set(remaining)
        ready = sorted(name for name, deps in remaining.items() if not (deps & pending))
        if not ready:
            return None
        for name in ready:
            remaining.pop(name)
            order.append(name)
    return order
