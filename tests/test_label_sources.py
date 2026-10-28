"""Registry policy tests: the file ships valid, and reject/unknown are refused."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from ml.data.label_sources import (
    SourcePolicyError,
    assert_source_allowed,
    load_sources,
)


@pytest.fixture(scope="module")
def sources():
    return load_sources()


def test_shipped_registry_is_valid(sources):
    assert sources
    assert sources["commander-spellbook"].verdict == "adopt"
    assert sources["edhrec"].terms == "licence-required"


def test_adopt_sources_are_not_prohibited(sources):
    for source in sources.values():
        if source.verdict == "adopt":
            assert source.terms != "prohibited", source.id
            assert source.labels, source.id


def test_rejected_source_is_refused(sources):
    with pytest.raises(SourcePolicyError):
        assert_source_allowed("tappedout", "substitute", sources)


def test_unknown_source_is_refused(sources):
    with pytest.raises(SourcePolicyError):
        assert_source_allowed("no-such-source", "synergy", sources)


def test_label_must_be_registered(sources):
    with pytest.raises(SourcePolicyError):
        assert_source_allowed("commander-spellbook", "substitute", sources)


def test_trial_source_is_allowed_for_its_labels(sources):
    source = assert_source_allowed("edhrec", "substitute", sources)
    assert source.verdict == "trial"


def test_duplicate_id_is_rejected(tmp_path):
    path = tmp_path / "registry.toml"
    path.write_text(
        '[[source]]\nid = "a"\nlabels = ["x"]\naccess = "api"\n'
        'terms = "permissive"\nverdict = "adopt"\n'
        '[[source]]\nid = "a"\nlabels = ["x"]\naccess = "api"\n'
        'terms = "permissive"\nverdict = "adopt"\n'
    )
    with pytest.raises(SourcePolicyError):
        load_sources(path)


@pytest.mark.parametrize("verdict", ["adopt", "trial"])
def test_usable_prohibited_source_is_rejected(tmp_path, verdict):
    path = tmp_path / "registry.toml"
    path.write_text(
        '[[source]]\nid = "a"\nlabels = ["x"]\naccess = "api"\n'
        f'terms = "prohibited"\nverdict = "{verdict}"\n'
    )
    with pytest.raises(SourcePolicyError):
        load_sources(path)
