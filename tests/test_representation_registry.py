"""The representation surface refuses, and the refusal names the repair.

Every test here is a failure class that used to be silent: a missing artefact
scored as zero, a dimension nobody compared, a text index with no encoder, a
withdrawn calibration still readable as if it were live. If the registry ever
grows a fallback, the expected exception disappears and these tests fail.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from ml.representations import manifest as manifest_module
from ml.representations.manifest import (
    Capability,
    Representation,
    RepresentationManifest,
    Status,
    build_manifest,
)
from ml.representations.registry import (
    RefusalCode,
    RepresentationRefusal,
    RepresentationRegistry,
    VerifyTable,
)


@pytest.fixture(scope="module")
def declared() -> RepresentationManifest:
    return build_manifest()


@pytest.fixture(scope="module")
def registry(declared: RepresentationManifest) -> RepresentationRegistry:
    return RepresentationRegistry(declared)


def revise(manifest: RepresentationManifest, record_id: str, **changes: object):
    """A manifest with one record changed, so nothing on disk is touched."""
    records = tuple(
        dataclasses.replace(record, **changes) if record.id == record_id else record
        for record in manifest
    )
    assert any(record.id == record_id for record in manifest)
    return RepresentationManifest(root=manifest.root, representations=records)


# --- the declaration points at what is actually on this machine --------------


def test_manifest_reads_env_and_disk(declared: RepresentationManifest) -> None:
    primary = declared.get("magic:card_embedding:primary")
    assert primary is not None
    assert primary.path.name == "magic_v7_spectral_mu35.wv"
    assert primary.status is Status.PRESENT
    assert primary.dim == 128
    assert primary.sha256 == "3d221e573abf447dbb634a789cf256d167b6e7898a609ab08adc6569b5bd5419"

    text = declared.get("magic:text_index:encoder_keyed_npz")
    assert text is not None
    assert text.encoder == "intfloat/e5-base-v2"
    assert text.sha256 is None, "a derived cache is not pinned; its identity is the encoder"

    legacy = declared.get("magic:text_index:legacy_npy")
    assert legacy is not None and legacy.status is Status.HISTORICAL
    assert legacy.encoder is None, "the producer of the legacy matrix was never recorded"


def test_secondary_embedding_is_a_member_not_a_default(declared: RepresentationManifest) -> None:
    """Two card embeddings exist per game; only one may answer an unpinned lookup."""
    secondary = declared.get("magic:card_embedding:secondary_metapath2vec")
    assert secondary is not None and secondary.served is False
    with pytest.raises(ValueError, match="two servable representations"):
        RepresentationManifest(
            root=declared.root,
            representations=tuple(
                dataclasses.replace(record, served=True) if record is secondary else record
                for record in declared
            ),
        )


# --- success -----------------------------------------------------------------


def test_resolve_returns_a_loaded_artefact_and_its_identity(
    registry: RepresentationRegistry,
) -> None:
    resolution = registry.resolve("pokemon", "card_embedding")
    assert resolution.identity.id == "pokemon:card_embedding:primary"
    assert resolution.dim == 128
    assert resolution.identity.sha256 is not None
    assert resolution.loaded.kind == "keyed_vectors"
    assert len(resolution.loaded.names) == 4384
    assert resolution.identity.as_dict()["status"] == "PRESENT"


def test_resolve_reads_a_member_by_pinned_id(registry: RepresentationRegistry) -> None:
    resolution = registry.resolve(
        "magic", "card_embedding", pinned="magic:card_embedding:secondary_metapath2vec"
    )
    assert resolution.identity.encoder == "metapath2vec"
    assert len(resolution.loaded.names) == 35272


def test_resolve_graph_does_not_materialise_the_csv(registry: RepresentationRegistry) -> None:
    resolution = registry.resolve("pokemon", "cooccurrence_graph")
    assert resolution.loaded.kind == "edge_csv"
    assert resolution.payload.count_column in {"COUNT_MULTISET", "COUNT"}
    left, right, weight = next(iter(resolution.payload.iter_edges(limit=1)))
    assert left and right and weight > 0


# --- one test per refusal code ----------------------------------------------


def test_missing_artefact_refuses(registry: RepresentationRegistry) -> None:
    """The visual index is declared and has never been built on this checkout."""
    with pytest.raises(RepresentationRefusal) as caught:
        registry.resolve("magic", "visual_index")
    assert caught.value.code is RefusalCode.MISSING
    assert "absent: data/cache/visual_embeddings/magic_embeddings.npy" in caught.value.detail


def test_absent_file_refuses_even_when_declared_present(
    declared: RepresentationManifest, tmp_path: Path
) -> None:
    tampered = revise(
        declared,
        "pokemon:card_embedding:primary",
        path=tmp_path / "pokemon_v7_fused.wv",
    )
    with pytest.raises(RepresentationRefusal) as caught:
        RepresentationRegistry(tampered).resolve("pokemon", "card_embedding")
    assert caught.value.code is RefusalCode.MISSING


def test_fabricated_dimension_refuses(declared: RepresentationManifest) -> None:
    tampered = revise(declared, "pokemon:card_embedding:primary", dim=384)
    with pytest.raises(RepresentationRefusal) as caught:
        RepresentationRegistry(tampered).resolve("pokemon", "card_embedding")
    assert caught.value.code is RefusalCode.DIM_MISMATCH
    assert "declared dim 384, file has 128" in caught.value.detail


def test_caller_dimension_requirement_refuses(registry: RepresentationRegistry) -> None:
    with pytest.raises(RepresentationRefusal) as caught:
        registry.resolve("pokemon", "card_embedding", require_dim=384)
    assert caught.value.code is RefusalCode.DIM_MISMATCH


def test_encoder_requirement_refuses_the_unrecorded_legacy_index(
    registry: RepresentationRegistry,
) -> None:
    """Both text matrices are 768D, so only the encoder identity can refuse this."""
    with pytest.raises(RepresentationRefusal) as caught:
        registry.resolve(
            "magic",
            "text_index",
            pinned="magic:text_index:legacy_npy",
            allow_historical=True,
            require_encoder="intfloat/e5-base-v2",
        )
    assert caught.value.code is RefusalCode.ENCODER_MISMATCH


def test_artefact_that_records_another_encoder_refuses(
    declared: RepresentationManifest, tmp_path: Path
) -> None:
    archive = tmp_path / "text_emb_cache_cards_magic.npz"
    np.savez(archive, matrix=np.zeros((2, 768), dtype=np.float32), encoder=np.array("other/model"))
    tampered = revise(declared, "magic:text_index:encoder_keyed_npz", path=archive)
    with pytest.raises(RepresentationRefusal) as caught:
        RepresentationRegistry(tampered).resolve("magic", "text_index")
    assert caught.value.code is RefusalCode.ENCODER_MISMATCH
    assert "other/model" in caught.value.detail


def test_calibrated_weights_resolve_with_their_evidence(
    registry: RepresentationRegistry,
) -> None:
    """0067 replaced the withdrawn file; the loader demands its evidence fields."""
    resolution = registry.resolve("magic", "fusion_weights")
    assert resolution.identity.status is Status.PRESENT
    payload = resolution.payload
    assert payload["experiment"] == "0067"
    assert payload["objective"] == "partial-coverage-v1"
    assert 0.0 < float(payload["holdout_coverage"]) <= 1.0
    assert payload["best_weights"]["embed"] > 0.0


def test_historical_entry_refuses_for_serving_but_reads_when_asked(
    declared: RepresentationManifest,
) -> None:
    """The refusal is exercised on a declaration, not on whatever is on disk."""
    historical = revise(declared, "magic:fusion_weights:calibrated", status=Status.HISTORICAL)
    registry = RepresentationRegistry(historical)
    with pytest.raises(RepresentationRefusal) as caught:
        registry.resolve("magic", "fusion_weights")
    assert caught.value.code is RefusalCode.HISTORICAL_ONLY

    resolution = registry.resolve("magic", "fusion_weights", allow_historical=True)
    assert resolution.identity.status is Status.HISTORICAL
    assert resolution.payload["best_weights"]["embed"] > 0.0


def test_hash_mismatch_is_the_declaration_not_the_file(
    declared: RepresentationManifest,
) -> None:
    """The file is untouched; the expected value is wrong, and that is enough."""
    tampered = revise(declared, "pokemon:card_embedding:primary", sha256="0" * 64)
    with pytest.raises(RepresentationRefusal) as caught:
        RepresentationRegistry(tampered).resolve("pokemon", "card_embedding")
    assert caught.value.code is RefusalCode.HASH_MISMATCH
    assert caught.value.detail.startswith("declared 000000000000...")


def test_capability_without_a_loader_refuses(
    declared: RepresentationManifest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delitem(manifest_module.LOADERS, Capability.CARD_EMBEDDING)
    with pytest.raises(RepresentationRefusal) as caught:
        RepresentationRegistry(declared).resolve("pokemon", "card_embedding")
    assert caught.value.code is RefusalCode.NO_LOADER


def test_unknown_capability_refuses(declared: RepresentationManifest) -> None:
    tampered = revise(declared, "pokemon:card_embedding:primary", capability="policy_state")
    with pytest.raises(RepresentationRefusal) as caught:
        RepresentationRegistry(tampered).resolve("pokemon", "policy_state")
    assert caught.value.code is RefusalCode.NO_LOADER


def test_unreadable_artefact_refuses(declared: RepresentationManifest, tmp_path: Path) -> None:
    broken = tmp_path / "fusion_weights_magic.json"
    broken.write_text("{not json")
    tampered = revise(
        declared,
        "magic:fusion_weights:calibrated",
        path=broken,
        sha256=None,
    )
    with pytest.raises(RepresentationRefusal) as caught:
        RepresentationRegistry(tampered).resolve("magic", "fusion_weights", allow_historical=True)
    assert caught.value.code is RefusalCode.UNREADABLE


def test_undeclared_lookup_refuses_rather_than_returning_none(
    registry: RepresentationRegistry,
) -> None:
    with pytest.raises(RepresentationRefusal) as caught:
        registry.resolve("digimon", "card_embedding")
    assert caught.value.code is RefusalCode.MISSING
    assert caught.value.representation_id is None


def test_task_scoping_filters_the_declaration(registry: RepresentationRegistry) -> None:
    """The withdrawn weights were calibrated for substitution, and say so."""
    with pytest.raises(RepresentationRefusal) as caught:
        registry.resolve("magic", "fusion_weights", task="synergy")
    assert caught.value.code is RefusalCode.MISSING
    assert "task='synergy'" in caught.value.detail


def test_refusal_message_carries_the_repair(registry: RepresentationRegistry) -> None:
    with pytest.raises(RepresentationRefusal) as caught:
        registry.resolve("magic", "visual_index")
    assert "build_visual_embedding_index.py" not in str(caught.value)
    assert "produce the artefact, or stop declaring it" in str(caught.value)


# --- the table ---------------------------------------------------------------


def test_verify_covers_every_declaration(registry: RepresentationRegistry) -> None:
    table = registry.verify()
    assert isinstance(table, VerifyTable)
    assert {row.id for row in table} == set(registry.ids())
    printed = table.format()
    assert "magic:card_embedding:primary" in printed
    assert "HISTORICAL_ONLY" in printed
    assert not table.ok, "a table where every artefact passes is not this checkout"


def test_verify_agrees_with_resolve(registry: RepresentationRegistry) -> None:
    for row in registry.verify():
        record = row.representation
        pinned = row.id
        if row.code is RefusalCode.HISTORICAL_ONLY:
            with pytest.raises(RepresentationRefusal) as caught:
                registry.resolve(record.game, str(record.capability), pinned=pinned)
            assert caught.value.code is RefusalCode.HISTORICAL_ONLY
            resolved = registry.resolve(
                record.game, str(record.capability), pinned=pinned, allow_historical=True
            )
            assert resolved.identity.status is Status.HISTORICAL
            continue
        if row.code is None:
            registry.resolve(record.game, str(record.capability), pinned=pinned)
            continue
        with pytest.raises(RepresentationRefusal) as caught:
            registry.resolve(
                record.game,
                str(record.capability),
                pinned=pinned,
                allow_historical=True,
            )
        assert caught.value.code is row.code, row.id


def test_verify_rows_are_json_safe(registry: RepresentationRegistry) -> None:
    payload = json.dumps(registry.verify().as_dicts())
    assert "HISTORICAL_ONLY" in payload
    assert "MagicMock" not in payload


def test_hash_is_lazy_not_at_import() -> None:
    """Building the manifest stats files; it must not hash them."""
    manifest_module._digest.cache_clear()
    build_manifest()
    assert manifest_module._digest.cache_info().currsize == 0
    record: Representation = next(r for r in build_manifest() if r.sha256 is not None)
    record.actual_sha256()
    assert manifest_module._digest.cache_info().currsize == 1
