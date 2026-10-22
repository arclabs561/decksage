"""Ingestion skeleton: registry refusals, ADR-0002, dedup, JSONL, validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from ml.data.label_sources import SourcePolicyError
from ml.ingest import (
    Fetcher,
    FetchError,
    InvalidCandidateError,
    LabelCandidate,
    LabelPolicyError,
    LabelWriter,
    StaticFetcher,
    content_sha256,
    read_jsonl,
    write_jsonl,
)


SHA = "a" * 64


def make_candidate(**overrides) -> LabelCandidate:
    """Build a valid adopt-source candidate; override one field per test."""
    fields = {
        "source_id": "commander-spellbook",
        "label_type": "synergy",
        "query": "Kiki-Jiki, Mirror Breaker",
        "candidate": "Zealous Conscripts",
        "score": 0.9,
        "source_url": "https://backend.commanderspellbook.com/variants/123",
        "fetched_at": "2026-10-22T09:30:00Z",
        "content_sha256": SHA,
        "extractor": "spellbook-combos-v1",
        "prompt_version": "none",
        "confidence": 0.8,
    }
    fields.update(overrides)
    return LabelCandidate(**fields)


def make_trial_candidate(**overrides) -> LabelCandidate:
    fields = {
        "source_id": "edhrec",
        "label_type": "substitute",
        "query": "Atraxa, Praetors' Voice",
        "candidate": "Deepglow Skate",
        "extractor": "edhrec-precon-cuts-v1",
    }
    fields.update(overrides)
    return make_candidate(**fields)


# --- registry refusals -------------------------------------------------------


@pytest.mark.parametrize("evaluation", [True, False])
def test_rejected_source_is_refused(tmp_path, evaluation):
    writer = LabelWriter(tmp_path / "labels.jsonl", evaluation=evaluation)
    with pytest.raises(SourcePolicyError):
        writer.write(make_candidate(source_id="tappedout", label_type="substitute"))


def test_unknown_source_is_refused(tmp_path):
    writer = LabelWriter(tmp_path / "labels.jsonl")
    with pytest.raises(SourcePolicyError):
        writer.write(make_candidate(source_id="no-such-source"))


def test_unregistered_label_is_refused(tmp_path):
    writer = LabelWriter(tmp_path / "labels.jsonl")
    with pytest.raises(SourcePolicyError):
        writer.write(make_candidate(source_id="commander-spellbook", label_type="substitute"))


def test_refusal_writes_nothing(tmp_path):
    path = tmp_path / "labels.jsonl"
    writer = LabelWriter(path)
    with pytest.raises(SourcePolicyError):
        writer.write(make_candidate(source_id="mtggoldfish", label_type="meta"))
    assert not path.exists()
    assert len(writer) == 0


# --- trial sources and the training path ------------------------------------


def test_trial_source_is_allowed_on_evaluation_path(tmp_path):
    writer = LabelWriter(tmp_path / "eval.jsonl", evaluation=True)
    row = writer.write(make_trial_candidate())
    assert row.allow_trial_training is False
    assert writer.rows[0].source_id == "edhrec"


def test_trial_source_is_refused_on_training_path(tmp_path):
    path = tmp_path / "train.jsonl"
    writer = LabelWriter(path, evaluation=False)
    with pytest.raises(LabelPolicyError):
        writer.write(make_trial_candidate())
    assert not path.exists()


def test_trial_source_trains_only_with_explicit_exception(tmp_path):
    path = tmp_path / "train.jsonl"
    writer = LabelWriter(path, evaluation=False, allow_trial_training=True)
    row = writer.write(make_trial_candidate())
    assert row.allow_trial_training is True
    assert read_jsonl(path)[0].allow_trial_training is True


def test_training_writer_refuses_trial_row_without_recorded_exception(tmp_path):
    path = tmp_path / "train.jsonl"
    row = make_trial_candidate().to_dict()
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(LabelPolicyError):
        LabelWriter(path, evaluation=False)


# --- synthetic labels are training-only (ADR-0002) ---------------------------


def test_synthetic_is_refused_on_evaluation_path(tmp_path):
    path = tmp_path / "eval.jsonl"
    writer = LabelWriter(path, evaluation=True)
    with pytest.raises(LabelPolicyError):
        writer.write(make_candidate(synthetic=True))
    assert not path.exists()


def test_synthetic_is_allowed_on_training_path(tmp_path):
    path = tmp_path / "train.jsonl"
    writer = LabelWriter(path, evaluation=False)
    row = writer.write(make_candidate(synthetic=True))
    assert row.synthetic is True
    assert LabelWriter(path, evaluation=False).rows[0].synthetic is True


def test_evaluation_writer_refuses_file_holding_synthetic_rows(tmp_path):
    path = tmp_path / "eval.jsonl"
    LabelWriter(path, evaluation=False).write(make_candidate(synthetic=True))
    with pytest.raises(LabelPolicyError):
        LabelWriter(path, evaluation=True)


# --- deduplication -----------------------------------------------------------


def test_dedup_keeps_highest_confidence(tmp_path):
    path = tmp_path / "labels.jsonl"
    writer = LabelWriter(path)

    writer.write(make_candidate(score=0.3, confidence=0.2))
    stored = writer.write(make_candidate(score=0.9, confidence=0.9))
    assert stored.confidence == 0.9
    assert stored.score == 0.9
    assert stored.duplicate_count == 1

    # A later weaker reading is dropped but counted.
    writer.write(make_candidate(score=0.5, confidence=0.4))
    assert len(writer) == 1
    assert writer.rows[0].confidence == 0.9
    assert writer.rows[0].duplicate_count == 2
    assert len(read_jsonl(path)) == 1


def test_dedup_survives_reload(tmp_path):
    path = tmp_path / "labels.jsonl"
    LabelWriter(path).write(make_candidate(confidence=0.2))
    LabelWriter(path).write(make_candidate(confidence=0.7))
    reloaded = LabelWriter(path)
    assert len(reloaded) == 1
    assert reloaded.rows[0].confidence == 0.7
    assert reloaded.rows[0].duplicate_count == 1


def test_dedup_keys_on_label_type(tmp_path):
    writer = LabelWriter(tmp_path / "labels.jsonl")
    writer.write(make_candidate())
    writer.write(
        make_candidate(
            source_id="mtgjson", label_type="role", query="Sol Ring", candidate="Mana Crypt"
        )
    )
    writer.write(
        make_candidate(
            source_id="mtgjson", label_type="meta", query="Sol Ring", candidate="Mana Crypt"
        )
    )
    assert len(writer) == 3


# --- JSONL round trip --------------------------------------------------------


def test_candidate_jsonl_round_trip():
    original = make_candidate(synthetic=True, allow_trial_training=True, duplicate_count=3)
    restored = LabelCandidate.from_json(original.to_json())
    assert restored == original
    assert restored.to_dict() == original.to_dict()


def test_jsonl_file_round_trip(tmp_path):
    path = tmp_path / "labels.jsonl"
    rows = [make_candidate(), make_candidate(query="Thassa's Oracle")]
    assert write_jsonl(path, rows) == 2
    assert read_jsonl(path) == rows
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_from_dict_rejects_unknown_field():
    row = make_candidate().to_dict()
    row["conficence"] = 0.5
    with pytest.raises(InvalidCandidateError):
        LabelCandidate.from_dict(row)


def test_from_dict_rejects_missing_field():
    row = make_candidate().to_dict()
    del row["content_sha256"]
    with pytest.raises(InvalidCandidateError):
        LabelCandidate.from_dict(row)


# --- field validation --------------------------------------------------------


@pytest.mark.parametrize("score", [-0.01, 1.01, 2, "0.5", None, True])
def test_score_must_be_in_unit_interval(score):
    with pytest.raises(InvalidCandidateError):
        make_candidate(score=score)


@pytest.mark.parametrize("confidence", [-0.5, 1.5])
def test_confidence_must_be_in_unit_interval(confidence):
    with pytest.raises(InvalidCandidateError):
        make_candidate(confidence=confidence)


@pytest.mark.parametrize("name", ["source_id", "label_type", "query", "candidate"])
@pytest.mark.parametrize("value", ["", "   "])
def test_identifiers_must_not_be_empty(name, value):
    with pytest.raises(InvalidCandidateError):
        make_candidate(**{name: value})


def test_extractor_provenance_is_required():
    with pytest.raises(InvalidCandidateError):
        make_candidate(extractor="")
    with pytest.raises(InvalidCandidateError):
        make_candidate(prompt_version="")


@pytest.mark.parametrize(
    "payload",
    ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65, 123],
)
def test_sha256_shape_is_enforced(payload):
    with pytest.raises(InvalidCandidateError):
        make_candidate(content_sha256=payload)


@pytest.mark.parametrize(
    "payload",
    ["", "2026-10-22", "2026-10-22T09:30:00", "yesterday", "2026-10-22 09:30:00Z"],
)
def test_timestamp_must_be_iso_with_offset(payload):
    with pytest.raises(InvalidCandidateError):
        make_candidate(fetched_at=payload)


def test_timestamp_offsets_are_accepted():
    assert make_candidate(fetched_at="2026-10-22T11:30:00+02:00").fetched_at.endswith("+02:00")


def test_negative_duplicate_count_is_refused():
    with pytest.raises(InvalidCandidateError):
        make_candidate(duplicate_count=-1)


# --- fetch seam --------------------------------------------------------------


def test_content_sha256_is_stable():
    assert content_sha256(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert content_sha256(b"combo") == content_sha256(b"combo")
    assert content_sha256(b"combo") != content_sha256(b"combo ")


def test_content_sha256_rejects_text():
    with pytest.raises(TypeError):
        content_sha256("combo")  # type: ignore[arg-type]


def test_static_fetcher_serves_bytes_and_hashes_match_rows(tmp_path):
    url = "https://example.invalid/tips"
    fetcher = StaticFetcher({url: b"<html>searched by</html>"})
    assert isinstance(fetcher, Fetcher)
    body = fetcher.fetch(url)
    assert body == b"<html>searched by</html>"

    row = make_candidate(
        source_id="yugipedia",
        label_type="synergy",
        query="Blue-Eyes White Dragon",
        candidate="Lord of D.",
        source_url=url,
        content_sha256=content_sha256(body),
    )
    assert LabelWriter(tmp_path / "labels.jsonl").write(row).content_sha256 == content_sha256(body)
    assert fetcher.requests == [url]


def test_static_fetcher_raises_for_unknown_url():
    fetcher = StaticFetcher({})
    with pytest.raises(FetchError):
        fetcher.fetch("https://example.invalid/missing")
