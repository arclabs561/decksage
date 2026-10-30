"""Training-pair provenance and evaluation-pair exclusion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class AttributePair(BaseModel):
    """A heuristic attribute-similarity pair, not a human judgment."""

    model_config = ConfigDict(extra="forbid")
    game: Literal["magic", "pokemon", "yugioh"]
    source: Literal["card_attributes"]
    task: Literal["attribute_similarity"]
    query: str = Field(min_length=1)
    candidate: str = Field(min_length=1)
    query_text: str = Field(min_length=1)
    candidate_text: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def distinct_cards(self) -> AttributePair:
        if self.query == self.candidate:
            raise ValueError("a pair must contain distinct cards")
        return self


def evaluation_pairs(data_dir: Path, game: str) -> set[frozenset[str]]:
    """Include both scored and bucket-only evaluation candidates."""
    path = data_dir / "test_sets" / f"annotated_{game}_v2.json"
    if not path.exists():
        raise FileNotFoundError(f"Cannot check evaluation overlap: missing {path}")
    evaluation = json.loads(path.read_text())
    if not isinstance(evaluation, dict) or not isinstance(evaluation.get("queries"), dict):
        raise ValueError(f"Cannot check evaluation overlap: invalid queries in {path}")
    if not evaluation["queries"]:
        raise ValueError(f"Cannot check evaluation overlap: empty queries in {path}")
    result = set()
    for query, entry in evaluation["queries"].items():
        names = [ann.get("candidate") for ann in entry.get("annotations", [])]
        for bucket in (
            "highly_relevant",
            "relevant",
            "somewhat_relevant",
            "marginally_relevant",
            "irrelevant",
        ):
            names.extend(entry.get(bucket, []))
        result.update(frozenset((query, name)) for name in names if name)
    return result


def verified_pairs(entries: list[dict], data_dir: Path, games: list[str]) -> list[dict]:
    """Fail closed on unknown provenance and exclude current eval pairs."""
    validated = []
    for row in entries:
        try:
            pair = AttributePair.model_validate(row)
        except ValidationError as exc:
            raise ValueError("Training pairs lack valid game provenance; regenerate") from exc
        if pair.game in games:
            validated.append(row)
    held_out: dict[str, set[frozenset[str]]] = {}
    for game in games:
        held_out[game] = evaluation_pairs(data_dir, game)
    return [
        row
        for row in validated
        if frozenset((row["query"], row["candidate"])) not in held_out[row["game"]]
    ]
