"""Typed guards for ranking comparisons.

These exist because three evaluation errors were found by hand and all were
representable in the data before they were caught:

* a comparison whose judged pool was far smaller than the candidate pool,
  because nDCG calls an unjudged candidate irrelevant;
* a verdict string that no consumer agreed on;
* a label patch applied to a pair that did not exist, silently doing nothing.

The models make each one unrepresentable or loud at the boundary.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Verdict(StrEnum):
    """The only verdicts a comparison may report."""

    CANDIDATE_BETTER = "candidate_better"
    CANDIDATE_WORSE = "candidate_worse"
    NO_DIFFERENCE = "no_difference"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SparseLabelsError(RuntimeError):
    """The judged pool is too small for the metric to be informative."""


class Coverage(BaseModel):
    """Judged coverage of the fixed candidate pool, checked before a verdict.

    ``required`` is ``max(k, depth // 2)``: a pool where half the candidates
    have no label lets an arm that moves away from the annotated neighbourhood
    lose by construction. The threshold is a property of the metric, not a
    per-run option.
    """

    model_config = ConfigDict(frozen=True)

    k: int = Field(ge=1)
    depth: int = Field(ge=1)
    median_judged: float = Field(ge=0)
    min_judged: int = Field(ge=0)

    @property
    def required(self) -> int:
        return max(self.k, self.depth // 2)

    def check(self, *, judged_only: bool, allow_sparse: bool) -> Coverage:
        """Raise unless the pool is dense, judged-only, or explicitly overridden."""
        if judged_only or allow_sparse:
            return self
        if self.median_judged < self.required:
            raise SparseLabelsError(
                f"median judged pool {self.median_judged:.0f} of {self.depth} candidates "
                f"(need {self.required}): nDCG counts every unjudged candidate as 0. "
                "Rerun with --judged-only, or pass --allow-sparse-labels to record "
                "the biased comparison explicitly."
            )
        return self


class LabelPatchEntry(BaseModel):
    """One corrected relevance value, with provenance that cannot be empty."""

    model_config = ConfigDict(extra="allow", frozen=True)

    query: str = Field(min_length=1)
    candidate: str = Field(min_length=1)
    functional_score: float = Field(ge=0, le=1)


class LabelPolicy(BaseModel):
    """Patches and exclusions for one comparison; a pair cannot be both.

    Excluding a pair whose label is impossible and patching a pair whose label
    is known are different actions. Applying both to one pair means the run
    depends on load order, which is exactly the kind of silent ambiguity the
    old ``--exclude-pairs`` + ``--label-patch`` flags allowed.
    """

    model_config = ConfigDict(frozen=True)

    patches: tuple[LabelPatchEntry, ...] = ()
    excluded: tuple[tuple[str, str], ...] = ()

    @model_validator(mode="after")
    def disjoint(self) -> LabelPolicy:
        patched = {(entry.query, entry.candidate) for entry in self.patches}
        overlap = patched & set(self.excluded)
        if overlap:
            sample = sorted(overlap)[:3]
            raise ValueError(f"pairs are both patched and excluded: {sample}")
        return self
