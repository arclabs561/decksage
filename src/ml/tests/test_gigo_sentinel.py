#!/usr/bin/env python3
import pandas as pd


def test_detect_cooccurrence_outliers_flags_high_counts():
    from ..validation.validators.gigo_sentinel import detect_cooccurrence_outliers

    df = pd.DataFrame(
        {
            "NAME_1": ["A", "A", "B"],
            "NAME_2": ["B", "C", "C"],
            "COUNT_MULTISET": [10, 100000, 12],
        }
    )

    findings = detect_cooccurrence_outliers(df)
    assert any(f.get("type") == "cooccurrence_outlier_high" for f in findings)





