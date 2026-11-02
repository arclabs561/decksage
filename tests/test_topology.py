"""Topology expansion and staleness assessment."""

from __future__ import annotations

import os
import time
from pathlib import Path

from ml.utils.topology import assess, expand


def spec(**overrides) -> dict:
    base = {
        "games": ["magic", "pokemon"],
        "node": [
            {"id": "source.{game}", "path": "s/{game}.txt", "layer": "source"},
            {
                "id": "derived.{game}",
                "path": "d/{game}.txt",
                "layer": "derived",
                "inputs": ["source.{game}"],
            },
            {"id": "shared", "path": "s/shared.txt", "layer": "source"},
        ],
    }
    base.update(overrides)
    return base


def touch(path: Path, age_seconds: float = 0.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


def test_expand_dedupes_nodes_without_a_placeholder():
    nodes = expand(spec())
    ids = [node["id"] for node in nodes]
    assert ids.count("shared") == 1
    assert "derived.magic" in ids and "derived.pokemon" in ids


def test_expand_honours_only_and_exclude():
    data = spec()
    data["node"].append(
        {"id": "magic_only", "path": "m.txt", "only": ["magic"]},
    )
    data["node"].append(
        {"id": "not_magic", "path": "n.txt", "exclude": ["magic"]},
    )
    ids = [node["id"] for node in expand(data)]
    assert "magic_only" in ids
    assert "not_magic" in ids  # pokemon expands it
    assert "magic_only.pokemon" not in ids


def test_assess_reports_missing(tmp_path: Path):
    touch(tmp_path / "s/magic.txt")
    touch(tmp_path / "s/pokemon.txt")
    touch(tmp_path / "s/shared.txt")
    report = assess(spec(), root=tmp_path)
    assert "derived.magic" in report["findings"]["missing"]
    assert not report["ok"]


def test_assess_reports_stale_when_an_input_is_newer(tmp_path: Path):
    touch(tmp_path / "s/magic.txt")
    touch(tmp_path / "s/pokemon.txt")
    touch(tmp_path / "s/shared.txt")
    touch(tmp_path / "d/magic.txt", age_seconds=60)
    touch(tmp_path / "d/pokemon.txt")
    report = assess(spec(), root=tmp_path)
    assert report["findings"]["stale"] == ["derived.magic"]
    assert not report["ok"]


def test_assess_is_clean_when_outputs_are_newer(tmp_path: Path):
    touch(tmp_path / "s/magic.txt", age_seconds=120)
    touch(tmp_path / "s/pokemon.txt", age_seconds=120)
    touch(tmp_path / "s/shared.txt", age_seconds=120)
    touch(tmp_path / "d/magic.txt")
    touch(tmp_path / "d/pokemon.txt")
    report = assess(spec(), root=tmp_path)
    assert report["ok"], report["findings"]


def test_assess_flags_unknown_inputs_and_cycles(tmp_path: Path):
    data = spec()
    data["node"].append(
        {"id": "orphan", "path": "o.txt", "inputs": ["nowhere"]},
    )
    touch(tmp_path / "s/magic.txt")
    touch(tmp_path / "s/pokemon.txt")
    touch(tmp_path / "s/shared.txt")
    touch(tmp_path / "o.txt")
    report = assess(data, root=tmp_path)
    assert report["findings"]["unknown_inputs"] == ["orphan <- nowhere"]
    assert report["findings"]["cycles"] == []

    cyclic = spec()
    cyclic["node"][0]["inputs"] = ["derived.magic"]  # source depends on derived
    report = assess(cyclic, root=tmp_path)
    assert report["findings"]["cycles"] != []


def test_order_puts_inputs_before_consumers(tmp_path: Path):
    report = assess(spec(), root=tmp_path)
    position = {name: index for index, name in enumerate(report["order"])}
    for edge in report["edges"]:
        assert position[edge["from"]] < position[edge["to"]]


def test_remote_nodes_are_not_stale_checked(tmp_path: Path):
    data = spec()
    data["node"].append(
        {"id": "meili", "kind": "remote", "layer": "serving", "inputs": ["derived.magic"]}
    )
    touch(tmp_path / "s/magic.txt")
    touch(tmp_path / "s/pokemon.txt")
    touch(tmp_path / "s/shared.txt")
    touch(tmp_path / "d/magic.txt")
    touch(tmp_path / "d/pokemon.txt")
    report = assess(data, root=tmp_path)
    remote = next(node for node in report["nodes"] if node["id"] == "meili")
    assert remote["exists"] is None
    assert "meili" not in report["findings"]["missing"]
