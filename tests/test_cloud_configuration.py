"""Cloud helpers must use operator-selected destinations and honor dry-run."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def environment(tmp_path):
    env = os.environ.copy()
    for name in ("BUCKET", "S3_BUCKET", "DECKSAGE_S3_BUCKET", "GNN_OUTPUT", "EVAL_OUTPUT"):
        env.pop(name, None)
    env["LOG_DIR"] = str(tmp_path / "logs")
    return env


@pytest.mark.parametrize(
    ("script", "args", "setting"),
    [
        ("scripts/data_processing/sync_to_s3.sh", [], "BUCKET"),
        ("scripts/review_s3_buckets.sh", [], "BUCKET"),
        ("scripts/extract_all_collections.sh", [], "BUCKET"),
        ("scripts/automation/weekly_retrain.sh", [], "DECKSAGE_S3_BUCKET"),
        ("scripts/pipeline/run_full_pipeline_with_runctl.sh", [], "DECKSAGE_S3_BUCKET"),
        (
            "scripts/instance_management/auto_stop_after_training.sh",
            ["i-test"],
            "GNN_OUTPUT",
        ),
    ],
)
def test_cloud_scripts_reject_unconfigured_destination(tmp_path, script, args, setting):
    result = subprocess.run(
        ["bash", str(ROOT / script), *args],
        env=environment(tmp_path),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert setting in result.stderr


@pytest.mark.parametrize("script", ["daily_update.sh", "weekly_retrain.sh"])
def test_dry_run_never_uploads_logs(tmp_path, script):
    marker = tmp_path / "cloud-called"
    command = tmp_path / "s5cmd"
    command.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 99\n')
    command.chmod(0o700)
    env = environment(tmp_path)
    env.update(
        PATH=f"{tmp_path}:{env['PATH']}",
        S3_LOG_DESTINATION="s3://test-destination/logs/",
        DECKSAGE_S3_BUCKET="test-destination",
    )
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/automation" / script), "--dry-run"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "DRY-RUN" in result.stdout
    assert not marker.exists()


def test_runctl_cloud_path_overrides_do_not_require_default_bucket(tmp_path):
    command = tmp_path / "runctl"
    command.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    command.chmod(0o700)
    env = environment(tmp_path)
    env.update(
        RUNCTL_BIN=str(command),
        S3_DATA="s3://test-input/processed/",
        S3_OUTPUT="s3://test-output/annotations/",
    )
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/runctl_labeling.sh"), "aws", "i-test"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "s3://test-output/annotations/" in result.stdout


def test_local_promotion_requires_no_cloud_destination(tmp_path):
    script = tmp_path / "scripts/model_management/promote_to_production.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/model_management/promote_to_production.sh", script)
    model = tmp_path / "model_v1.json"
    model.write_text('{"weights": [1, 2]}')
    result = subprocess.run(
        ["bash", str(script), "--gnn", str(model), "--copy", "--no-archive"],
        cwd=tmp_path,
        env=environment(tmp_path),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "embeddings/gnn_graphsage.json").read_bytes() == model.read_bytes()
