import numpy as np
import pandas as pd

from features.price_features import build_price_dependent_features, safe_divide


def test_safe_division_returns_null_for_non_positive_denominators():
    values = safe_divide(pd.Series([10.0, 10.0, 10.0]), pd.Series([2.0, 0.0, -1.0]))
    assert values.iloc[0] == 5.0
    assert values.iloc[1:].isna().all()


def test_safe_divide_broadcasts_scalar_denominator_over_series():
    values = safe_divide(pd.Series([7.0, 14.0, 0.0]), 7)
    assert values.tolist() == [1.0, 2.0, 0.0]


def test_safe_divide_broadcasts_scalar_numerator_over_series():
    values = safe_divide(14.0, pd.Series([7.0, 0.0, -7.0]))
    assert values.iloc[0] == 2.0
    assert values.iloc[1:].isna().all()


def test_safe_divide_aligns_series_indices():
    numerator = pd.Series([10.0, 20.0], index=["a", "b"])
    denominator = pd.Series([2.0, 4.0], index=["b", "c"])
    values = safe_divide(numerator, denominator)
    assert pd.isna(values.loc["a"])
    assert values.loc["b"] == 10.0


def test_safe_divide_scalar_inputs_and_invalid_denominators():
    assert safe_divide(6.0, 3.0) == 2.0
    assert pd.isna(safe_divide(6.0, 0.0))
    assert pd.isna(safe_divide(6.0, -3.0))


def test_candidate_price_recomputes_only_price_dependent_values():
    historical = build_price_dependent_features([110.0], [100.0], [120.0], [105.0])
    candidate = build_price_dependent_features([90.0], [100.0], [120.0], [105.0])
    assert historical.loc[0, "price_change_amount"] == 10.0
    assert candidate.loc[0, "price_change_amount"] == -10.0
    assert historical.loc[0, "price_vs_competitor_pct"] != candidate.loc[0, "price_vs_competitor_pct"]
    assert np.isfinite(candidate["price_change_pct"]).all()


def test_scalar_candidate_price_api_is_reusable():
    result = build_price_dependent_features(90.0, 100.0, 120.0, 105.0)
    assert result["price_change_amount"] == -10.0
    assert result["price_vs_base_pct"] < 0
