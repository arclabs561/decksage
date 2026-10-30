"""Magic adapter over Forge's batch CLI.

Forge is the only rules-complete Magic engine with a documented, licence-clean
batch mode (`sim -d deckA deckB -n N -q`, GPL-3, invoked as a separate process).
It is *not* installed here, so this adapter declares itself unavailable and
refuses until `DECKSAGE_FORGE_JAR` points at a forge jar.

What is deliberately unverified: Forge's stdout format. This adapter therefore
returns `status="partial"` and keeps the raw output in `notes` for the first
run, so nobody ranks a deck on a parse that was never checked against a known
outcome.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .contract import (
    BatchResult,
    Capabilities,
    DeckList,
    Game,
    Refusal,
    SimStatus,
    Timer,
)


class ForgeSimulator:
    game = Game.MAGIC
    engine = "Forge batch CLI"

    def _jar(self) -> Path | None:
        raw = os.environ.get("DECKSAGE_FORGE_JAR", "")
        if not raw:
            return None
        path = Path(raw).expanduser()
        return path if path.is_file() else None

    def capabilities(self) -> Capabilities:
        jar = self._jar()
        return Capabilities(
            game=self.game,
            engine=self.engine,
            available=jar is not None and shutil.which("java") is not None,
            licensed_for_service=True,  # GPL-3: invoked as a process, not linked
            addressable_by="name",
            notes=(
                "set DECKSAGE_FORGE_JAR to the forge jar and have java on PATH",
                "commander-vs-other formats have very different per-game cost",
                "stdout parsing is unverified until a known outcome is reproduced",
            ),
        )

    def _write_deck(self, deck: DeckList, directory: Path, tag: str) -> Path:
        path = directory / f"{tag}.dck"
        path.write_text("\n".join(deck.as_lines()) + "\n")
        return path

    def batch(self, deck_a: DeckList, deck_b: DeckList, games: int, seed: int = 0) -> BatchResult:
        jar = self._jar()
        if jar is None:
            raise Refusal(self.game, "Forge jar not configured", "set DECKSAGE_FORGE_JAR")
        java = shutil.which("java")
        if java is None:
            raise Refusal(self.game, "java not on PATH")

        timer = Timer()
        with tempfile.TemporaryDirectory(prefix="decksage-forge-") as tmp:
            tmpdir = Path(tmp)
            a = self._write_deck(deck_a, tmpdir, "a")
            b = self._write_deck(deck_b, tmpdir, "b")
            cmd = [java, "-jar", str(jar), "sim", "-d", str(a), str(b), "-n", str(games), "-q"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            output = (proc.stdout or "") + (proc.stderr or "")

        wins_a = len(re.findall(r"\bseat\s*1\s*(?:win|wins)\b", output, re.IGNORECASE))
        wins_b = len(re.findall(r"\bseat\s*2\s*(?:win|wins)\b", output, re.IGNORECASE))
        parsed = wins_a + wins_b
        notes = [
            "stdout parse is unverified; treat counts as provisional",
            f"exit={proc.returncode}",
        ]
        if parsed != games:
            notes.append(f"parsed {parsed} decided games of {games} requested")
        return BatchResult(
            game=self.game,
            deck_a=deck_a,
            deck_b=deck_b,
            games=games,
            wins_a=wins_a,
            wins_b=wins_b,
            draws=max(0, games - parsed),
            status=SimStatus.PARTIAL,
            engine=self.engine,
            seed=seed,
            wall_ms=timer.ms(),
            notes=notes,
            coverage={"card_pool": "forge card database", "parse": "unverified"},
        )
