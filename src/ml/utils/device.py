"""Device selection shared by training and inference scripts.

Apple MPS is the default on this machine: the operator runs training on
Apple Silicon and wants MPS used whenever it is available. CUDA remains the
fallback for remote GPU hosts, then CPU.

Override with DECKSAGE_DEVICE=cpu|cuda|mps|auto.
"""

from __future__ import annotations

import os

import torch


def _mps_available() -> bool:
    backend = getattr(torch.backends, "mps", None)
    return bool(backend is not None and backend.is_available())


def get_device(prefer: str | None = None) -> torch.device:
    """Return the preferred torch device.

    Order when ``prefer`` is unset or ``auto``: mps, cuda, cpu.
    An explicit ``cpu`` short-circuits; an explicit ``cuda`` falls through to
    mps when CUDA is missing rather than silently dropping to CPU.
    """
    prefer = (prefer or os.environ.get("DECKSAGE_DEVICE", "mps")).lower()

    if prefer == "cpu":
        return torch.device("cpu")
    if prefer == "mps":
        return torch.device("mps") if _mps_available() else _fallback()
    if prefer == "cuda":
        return torch.device("cuda") if torch.cuda.is_available() else _fallback()
    return _fallback()


def _fallback() -> torch.device:
    if _mps_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def device_report(device: torch.device) -> str:
    """Human-readable device description for logs and experiment records."""
    name = device.type
    if name == "mps" and hasattr(torch, "mps") and hasattr(torch.mps, "device_count"):
        return f"mps ({torch.mps.device_count()} device)"
    if name == "cuda":
        return f"cuda:{torch.cuda.current_device()} ({torch.cuda.get_device_name(0)})"
    return "cpu"
