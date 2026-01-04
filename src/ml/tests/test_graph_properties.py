#!/usr/bin/env python3
from __future__ import annotations

import pandas as pd
from hypothesis import given
from hypothesis import strategies as st


@given(
    st.lists(
        st.tuples(
            st.text(min_size=1, max_size=6),
            st.text(min_size=1, max_size=6),
            st.integers(min_value=0, max_value=10),
        ),
        min_size=0,
        max_size=200,
    )
)
def test_build_adjacency_bidirectional(pairs):
    from ..utils.data_loading import build_adjacency_dict

    df = pd.DataFrame(pairs, columns=["NAME_1", "NAME_2", "COUNT_MULTISET"])
    adj = build_adjacency_dict(df)

    # Bidirectional: NAME_1 in adj implies NAME_2 contains NAME_1, and vice versa
    for a, b, _ in pairs:
        if a in adj:
            assert b in adj[a] or a == b
        if b in adj:
            assert a in adj[b] or a == b

    # No self-loops introduced beyond data
    self_nodes = {u for (u, v, _) in pairs if u == v}
    for u, nbrs in adj.items():
        if u in self_nodes:
            # Allowed if explicitly present in data
            continue
        assert u not in nbrs
