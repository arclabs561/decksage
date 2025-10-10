#!/usr/bin/env python3
from __future__ import annotations

import math

import pytest
from hypothesis import given, strategies as st


def _jaccard_python(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter) / float(union) if union else 0.0


@given(st.floats(allow_nan=False, allow_infinity=False, width=32))
def test_clamp01_range_and_monotone(x: float):
    from ..similarity.fusion import _clamp01  # type: ignore[attr-defined]

    y = _clamp01(x)
    assert 0.0 <= y <= 1.0

    # Monotonicity: x1 <= x2 => clamp(x1) <= clamp(x2)
    x1 = x - 0.5
    x2 = x + 0.5
    assert _clamp01(x1) <= _clamp01(x2)


@given(st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_cosine_to_unit_maps_bounds_and_is_linear_in_between(c: float):
    from ..similarity.fusion import _cosine_to_unit  # type: ignore[attr-defined]

    y = _cosine_to_unit(c)
    assert 0.0 <= y <= 1.0
    if math.isclose(c, -1.0):
        assert math.isclose(y, 0.0)
    if math.isclose(c, 1.0):
        assert math.isclose(y, 1.0)


@given(
    st.dictionaries(st.text(min_size=1, max_size=5), st.booleans(), min_size=0, max_size=10),
    st.dictionaries(st.text(min_size=1, max_size=5), st.booleans(), min_size=0, max_size=10),
)
def test_tag_jaccard_matches_python(a_map: dict[str, bool], b_map: dict[str, bool]):
    # Emulate fusion tag extraction: only truthy boolean fields contribute
    from ..similarity.fusion import _jaccard_sets  # type: ignore[attr-defined]

    a = {k for k, v in a_map.items() if isinstance(v, bool) and v}
    b = {k for k, v in b_map.items() if isinstance(v, bool) and v}

    j1 = _jaccard_sets(a, b)
    j2 = _jaccard_python(a, b)
    assert math.isclose(j1, j2)


@given(
    st.lists(st.text(min_size=1, max_size=6), min_size=0, max_size=50),
    st.lists(st.text(min_size=1, max_size=6), min_size=0, max_size=50),
)
def test_fusion_weights_normalize_sum_to_one(embed_list, jacc_list):
    from ..similarity.fusion import FusionWeights

    # Build some arbitrary positive totals
    e = float(len(embed_list))
    j = float(len(jacc_list))
    f = 1.0
    fw = FusionWeights(embed=e, jaccard=j, functional=f).normalized()
    total = fw.embed + fw.jaccard + fw.functional
    assert math.isclose(total, 1.0, rel_tol=1e-9)


@given(st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False))
def test_fusion_weight_scale_invariance_property(scale: float):
    from ..similarity.fusion import FusionWeights

    base = FusionWeights(embed=0.4, jaccard=0.35, functional=0.25)
    scaled = FusionWeights(embed=base.embed * scale, jaccard=base.jaccard * scale, functional=base.functional * scale)
    nb = base.normalized()
    ns = scaled.normalized()
    assert math.isclose(nb.embed, ns.embed)
    assert math.isclose(nb.jaccard, ns.jaccard)
    assert math.isclose(nb.functional, ns.functional)


