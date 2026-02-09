"""Unified log monitoring for training jobs (runctl + local).

This module parses structured log prefixes emitted by `ml.utils.logging_config`:

- `[PROGRESS] stage: current/total (pct%)`
- `[CHECKPOINT] name saved ...`
- `[METRIC] key=value ...`
- `[STAGE] free text`

It also extracts a best-effort correlation ID when present as:

- `corr_id=<token>` or
- `[token]` (excluding the prefix tokens above).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


try:
    from .logging_config import get_logger

    logger = get_logger(__name__)
except Exception:
    logger = logging.getLogger(__name__)


_PREFIX_TOKENS = {"PROGRESS", "CHECKPOINT", "STAGE", "METRIC"}


@dataclass
class LogEvent:
    timestamp: datetime
    level: str
    prefix: str | None
    correlation_id: str | None
    message: str
    raw_line: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrainingStatus:
    correlation_id: str | None = None
    stage: str | None = None
    progress: str | None = None
    last_checkpoint: str | None = None
    last_metric: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    last_update: datetime | None = None
    is_complete: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class LogParser:
    PREFIX_RE = re.compile(r"\[(PROGRESS|CHECKPOINT|STAGE|METRIC)\]")
    CORR_KV_RE = re.compile(r"\bcorr_id=(?P<corr>[^\s]+)")
    BRACKET_TOK_RE = re.compile(r"\[(?P<tok>[^\]]+)\]")
    PROGRESS_RE = re.compile(
        r"(?P<stage>[A-Za-z0-9_]+)\s*:\s*(?P<current>[\d.]+)\s*/\s*(?P<total>[\d.]+)"
        r"(?:\s*\((?P<pct>[\d.]+)%\))?"
    )
    CHECKPOINT_RE = re.compile(r"\[CHECKPOINT\]\s*(?P<name>\S+)")
    METRIC_KV_RE = re.compile(r"(?P<k>[A-Za-z_][A-Za-z0-9_]*)=(?P<v>[^\s,]+)")

    @classmethod
    def parse_line(cls, line: str) -> LogEvent | None:
        if not line or not line.strip():
            return None

        raw = line.rstrip("\n")
        timestamp = datetime.now(UTC)
        level = "INFO"
        message = raw.strip()

        # Common logging format: ts - LEVEL - name - func:line - message
        parts = raw.split(" - ", 4)
        if len(parts) == 5:
            ts_str, lvl, _name, _loc, msg = parts
            parsed_ts = _parse_timestamp(ts_str.strip())
            if parsed_ts is not None:
                timestamp = parsed_ts
            level = (lvl or "INFO").strip().upper() or "INFO"
            message = msg.strip()
        elif len(parts) == 4:
            ts_str, lvl, _name, msg = parts
            parsed_ts = _parse_timestamp(ts_str.strip())
            if parsed_ts is not None:
                timestamp = parsed_ts
            level = (lvl or "INFO").strip().upper() or "INFO"
            message = msg.strip()

        prefix_match = cls.PREFIX_RE.search(message)
        prefix = prefix_match.group(1) if prefix_match else None

        correlation_id = None
        kv = cls.CORR_KV_RE.search(message)
        if kv:
            correlation_id = kv.group("corr").strip()
        else:
            for tok in (m.group("tok").strip() for m in cls.BRACKET_TOK_RE.finditer(message)):
                if tok in _PREFIX_TOKENS:
                    continue
                if not tok or " " in tok:
                    continue
                correlation_id = tok
                break

        metadata: dict[str, Any] = {}
        if prefix == "PROGRESS":
            pm = cls.PROGRESS_RE.search(message)
            if pm:
                metadata["stage"] = pm.group("stage")
                metadata["current"] = float(pm.group("current"))
                metadata["total"] = float(pm.group("total"))
                if pm.group("pct") is not None:
                    metadata["percentage"] = float(pm.group("pct"))
        elif prefix == "CHECKPOINT":
            cm = cls.CHECKPOINT_RE.search(message)
            if cm:
                metadata["name"] = cm.group("name")
        elif prefix == "METRIC":
            for m in cls.METRIC_KV_RE.finditer(message):
                k, v = m.group("k"), m.group("v")
                try:
                    metadata[k] = float(v) if "." in v else int(v)
                except ValueError:
                    metadata[k] = v

        return LogEvent(
            timestamp=timestamp,
            level=level,
            prefix=prefix,
            correlation_id=correlation_id,
            message=message,
            raw_line=raw,
            metadata=metadata,
        )

    @classmethod
    def parse_file(cls, log_path: Path | str, *, last_n_lines: int = 100) -> list[LogEvent]:
        path = Path(log_path)
        if not path.exists():
            return []

        tail: list[str] = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                tail.append(line)
                if len(tail) > last_n_lines:
                    tail.pop(0)

        events: list[LogEvent] = []
        for line in tail:
            ev = cls.parse_line(line)
            if ev is not None:
                events.append(ev)
        return events


class RunctlLogMonitor:
    """Tail logs for a runctl-managed instance (best-effort)."""

    def __init__(
        self,
        instance_id: str,
        *,
        runctl_bin: Path | str = "runctl",
        log_path: Path | str | None = None,
    ):
        self.instance_id = instance_id
        self.runctl_bin = str(runctl_bin)
        self.log_path = str(log_path) if log_path is not None else None

    def tail_logs(self, *, lines: int = 50, timeout_s: int = 30) -> list[str]:
        cmd = [self.runctl_bin, "aws", "logs", self.instance_id, "--tail", f"--lines={lines}"]
        if self.log_path:
            cmd.extend(["--path", self.log_path])
        else:
            cmd.append("--auto-detect")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or f"runctl logs failed (exit={result.returncode})"
            )
        return [ln for ln in (result.stdout or "").splitlines() if ln.strip()]

    def get_status(self, *, use_live_logs: bool = True) -> TrainingStatus:
        if use_live_logs:
            try:
                lines = self.tail_logs(lines=120)
                return _status_from_lines(lines)
            except Exception:
                logger.debug("runctl live log fetch failed; returning empty status", exc_info=True)
        return TrainingStatus()


class LocalLogMonitor:
    """Monitor a local log file written by training scripts."""

    def __init__(self, log_path: Path | str):
        self.log_path = Path(log_path)

    def get_status(self, *, last_n_lines: int = 100) -> TrainingStatus:
        if not self.log_path.exists():
            return TrainingStatus()
        events = LogParser.parse_file(self.log_path, last_n_lines=last_n_lines)
        return _status_from_events(events)

    def tail(
        self, callback: Callable[[LogEvent], None], *, follow: bool = True, poll_s: float = 0.1
    ) -> None:
        if not self.log_path.exists():
            raise FileNotFoundError(self.log_path)

        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)  # to end
            while True:
                line = f.readline()
                if line:
                    ev = LogParser.parse_line(line)
                    if ev is not None:
                        callback(ev)
                else:
                    if not follow:
                        return
                    time.sleep(poll_s)


def monitor_training(
    *,
    instance_id: str | None = None,
    log_path: Path | str | None = None,
    use_runctl: bool = True,
) -> TrainingStatus:
    if use_runctl and instance_id:
        return RunctlLogMonitor(instance_id).get_status()
    if log_path:
        return LocalLogMonitor(log_path).get_status()
    raise ValueError("Either instance_id (use_runctl) or log_path must be provided")


def format_status(status: TrainingStatus, *, verbose: bool = False) -> str:
    lines: list[str] = []
    if status.correlation_id:
        lines.append(f"Correlation ID: {status.correlation_id}")
    if status.stage:
        lines.append(f"Stage: {status.stage}")
    if status.progress:
        lines.append(f"Progress: {status.progress}")
    if status.last_checkpoint:
        lines.append(f"Last checkpoint: {status.last_checkpoint}")
    if status.last_metric:
        if verbose:
            lines.append(f"Latest metrics: {json.dumps(status.last_metric, sort_keys=True)}")
        else:
            items = list(status.last_metric.items())
            show = items[:5]
            metric_str = ", ".join(f"{k}={v}" for k, v in show)
            if len(items) > len(show):
                metric_str += f", ... (+{len(items) - len(show)} more)"
            lines.append(f"Latest metrics: {metric_str}")
    if status.errors:
        show = status.errors if verbose else status.errors[-3:]
        lines.append(f"Errors: {len(status.errors)}")
        lines.extend([f" - {e}" for e in show])
        if not verbose and len(status.errors) > len(show):
            lines.append(f" ... (+{len(status.errors) - len(show)} more)")

    if status.is_complete:
        lines.append("Status: COMPLETE")
    elif status.last_update is not None:
        age_s = (datetime.now(UTC) - _ensure_aware(status.last_update)).total_seconds()
        lines.append(f"Status: RUNNING (last update: {int(age_s)}s ago)")
    else:
        lines.append("Status: UNKNOWN (no log data)")

    return "\n".join(lines)


def _parse_timestamp(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        ts = ts_str.replace("Z", "+00:00").replace(",", ".")
        dt = datetime.fromisoformat(ts)
        return _ensure_aware(dt)
    except Exception:
        return None


def _ensure_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _status_from_lines(lines: list[str]) -> TrainingStatus:
    events: list[LogEvent] = []
    for ln in lines:
        ev = LogParser.parse_line(ln)
        if ev is not None:
            events.append(ev)
    return _status_from_events(events)


def _status_from_events(events: list[LogEvent]) -> TrainingStatus:
    status = TrainingStatus()

    for ev in reversed(events):
        # Iterating newest -> oldest: first timestamp wins.
        if status.last_update is None:
            status.last_update = ev.timestamp

        if status.correlation_id is None and ev.correlation_id:
            status.correlation_id = ev.correlation_id

        if ev.level == "ERROR":
            status.errors.append(ev.message)

        if ev.prefix == "PROGRESS" and ev.metadata:
            if status.stage is None:
                status.stage = ev.metadata.get("stage")
            if status.progress is None:
                cur = ev.metadata.get("current")
                tot = ev.metadata.get("total")
                if cur is not None and tot is not None:
                    status.progress = (
                        f"{int(cur)}/{int(tot)}"
                        if float(cur).is_integer() and float(tot).is_integer()
                        else f"{cur}/{tot}"
                    )
                status.metadata.update(ev.metadata)

        if ev.prefix == "CHECKPOINT" and ev.metadata and status.last_checkpoint is None:
            status.last_checkpoint = str(ev.metadata.get("name") or status.last_checkpoint)

        if ev.prefix == "METRIC" and ev.metadata and status.last_metric is None:
            status.last_metric = dict(ev.metadata)

        msg = ev.message.lower()
        if any(k in msg for k in ("training complete", "complete!", "finished", "done", "success")):
            status.is_complete = True

    return status


__all__ = [
    "LocalLogMonitor",
    "LogEvent",
    "LogParser",
    "RunctlLogMonitor",
    "TrainingStatus",
    "format_status",
    "monitor_training",
]
