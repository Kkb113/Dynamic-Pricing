from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

import numpy as np
import pandas as pd


FIXED_MULTIPLIERS: tuple[float, ...] = (
    0.800, 0.825, 0.850, 0.875, 0.900, 0.925, 0.950, 0.975,
    1.000, 1.025, 1.050, 1.075, 1.100, 1.125, 1.150, 1.175, 1.200,
)
CENT = Decimal("0.01")


@dataclass(frozen=True)
class CandidateGrid:
    """Frozen global multiplier grid and the empirical support envelope."""

    technical_low: float
    technical_high: float
    training_p01: float
    training_p99: float
    effective_low: float
    effective_high: float
    multipliers: tuple[float, ...]

    @property
    def global_count(self) -> int:
        return len(self.multipliers)

    def as_dict(self) -> dict[str, object]:
        return {
            "technical_multiplier_low": self.technical_low,
            "technical_multiplier_high": self.technical_high,
            "training_ratio_p01": self.training_p01,
            "training_ratio_p99": self.training_p99,
            "effective_support_low": self.effective_low,
            "effective_support_high": self.effective_high,
            "candidate_multiplier_template": list(self.multipliers),
        }


def training_price_ratio(frame: pd.DataFrame) -> pd.Series:
    """Return valid TRAIN AppliedPrice/CurrentPrice observations only."""

    current = pd.to_numeric(frame["CurrentPrice"], errors="coerce")
    applied = pd.to_numeric(frame["AppliedPrice"], errors="coerce")
    ratio = applied / current
    valid = np.isfinite(current) & np.isfinite(applied) & current.gt(0) & applied.gt(0) & np.isfinite(ratio)
    return ratio.loc[valid]


def audit_price_support(train_frame: pd.DataFrame) -> dict[str, float | int]:
    ratios = training_price_ratio(train_frame)
    if ratios.empty:
        raise ValueError("PRICE_SUPPORT_UNAVAILABLE")
    values = ratios.to_numpy(float)
    percentiles = np.percentile(values, [1, 5, 25, 50, 75, 95, 99])
    return {
        "count": int(len(values)),
        "min": float(values.min()),
        "max": float(values.max()),
        "mean": float(values.mean()),
        "std": float(values.std(ddof=1)),
        "p01": float(percentiles[0]),
        "p05": float(percentiles[1]),
        "p25": float(percentiles[2]),
        "p50": float(percentiles[3]),
        "p75": float(percentiles[4]),
        "p95": float(percentiles[5]),
        "p99": float(percentiles[6]),
        "valid_positive_rate": float(len(values) / len(train_frame)),
    }


def build_candidate_grid(
    support_audit: dict[str, float | int],
    *,
    technical_low: float = 0.80,
    technical_high: float = 1.20,
) -> CandidateGrid:
    p01 = float(support_audit["p01"])
    p99 = float(support_audit["p99"])
    low = max(float(technical_low), p01)
    high = min(float(technical_high), p99)
    if not np.isfinite(low) or not np.isfinite(high) or low > high:
        raise ValueError("CANDIDATE_SUPPORT_ENVELOPE_INVALID")
    multipliers = tuple(float(m) for m in FIXED_MULTIPLIERS if low - 1e-12 <= m <= high + 1e-12 or abs(m - 1.0) <= 1e-12)
    if 1.0 not in multipliers:
        multipliers = tuple(sorted((*multipliers, 1.0)))
    if len(multipliers) < 5:
        raise ValueError("INSUFFICIENT_OBSERVED_PRICE_SUPPORT_FOR_OPTIMIZATION")
    return CandidateGrid(float(technical_low), float(technical_high), p01, p99, low, high, multipliers)


def round_price_half_up(value: float) -> float:
    """Round a scalar price to cents without binary-float banker rounding."""

    if not np.isfinite(value):
        raise ValueError("INVALID_CANDIDATE_PRICE")
    return float(Decimal(str(float(value))).quantize(CENT, rounding=ROUND_HALF_UP))


def scenario_prices(current_prices: Iterable[float], multiplier: float) -> np.ndarray:
    current = np.asarray(list(current_prices), dtype=float)
    if not np.isfinite(current).all() or np.any(current <= 0):
        raise ValueError("INVALID_CURRENT_PRICE")
    return np.asarray([round_price_half_up(float(price) * float(multiplier)) for price in current], dtype=float)


def generate_candidate_rows(context: pd.DataFrame, grid: CandidateGrid) -> pd.DataFrame:
    """Create a deterministic long candidate index, deduplicated after cents rounding."""

    rows: list[pd.DataFrame] = []
    base_columns = ["PricingDecisionID", "DecisionTime", "ProductID", "StoreID", "Channel", "CurrentPrice", "AppliedPrice", "BasePrice"]
    if "CostPrice" in context.columns:
        base_columns.append("CostPrice")
    for multiplier in grid.multipliers:
        prices = scenario_prices(context["CurrentPrice"], multiplier)
        part = context[base_columns].copy()
        part["HistoricalAppliedPrice"] = part["AppliedPrice"]
        part["candidate_multiplier"] = float(multiplier)
        part["CandidatePrice"] = prices
        rows.append(part)
    candidates = pd.concat(rows, ignore_index=True)
    # If an alternative rounds to the same cent as CurrentPrice, retain the
    # explicit baseline row rather than letting a neighbouring multiplier
    # replace the no-change candidate.
    candidates["_current_priority"] = candidates["candidate_multiplier"].eq(1.0).astype(int)
    candidates = candidates.sort_values(["PricingDecisionID", "CandidatePrice", "_current_priority", "candidate_multiplier"], ascending=[True, True, False, True], kind="mergesort").reset_index(drop=True)
    # A low-valued CurrentPrice can map adjacent multipliers to the same cent.
    candidates = candidates.drop_duplicates(["PricingDecisionID", "CandidatePrice"], keep="first").reset_index(drop=True)
    candidates = candidates.drop(columns=["_current_priority"])
    candidates["candidate_rank_by_price"] = candidates.groupby("PricingDecisionID", sort=False).cumcount()
    if candidates.duplicated(["PricingDecisionID", "CandidatePrice"]).any():
        raise ValueError("DUPLICATE_CANDIDATE_ROWS_AFTER_NORMALIZATION")
    counts = candidates.groupby("PricingDecisionID", sort=False).size()
    if (counts < 1).any():
        raise ValueError("CANDIDATE_GENERATION_EMPTY")
    candidates["is_current_price_candidate"] = candidates["candidate_multiplier"].eq(1.0)
    if not candidates.groupby("PricingDecisionID")["is_current_price_candidate"].sum().eq(1).all():
        raise ValueError("NO_CHANGE_CANDIDATE")
    candidates["is_support_lower_boundary"] = candidates["candidate_multiplier"].eq(min(grid.multipliers))
    candidates["is_support_upper_boundary"] = candidates["candidate_multiplier"].eq(max(grid.multipliers))
    candidates["candidate_vs_current_pct"] = candidates["CandidatePrice"] / candidates["CurrentPrice"] - 1.0
    candidates["candidate_vs_base_pct"] = candidates["CandidatePrice"] / candidates["BasePrice"] - 1.0
    candidates["support_low"] = float(grid.effective_low)
    candidates["support_high"] = float(grid.effective_high)
    return candidates


__all__ = [
    "FIXED_MULTIPLIERS", "CandidateGrid", "audit_price_support", "build_candidate_grid",
    "generate_candidate_rows", "round_price_half_up", "scenario_prices", "training_price_ratio",
]
