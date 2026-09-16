"""Versioned, deployment-neutral pricing contract types."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP
from enum import StrEnum
from typing import Any


class CurrencyStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED_SOURCE_UNIT = "UNVERIFIED_SOURCE_UNIT"


class ScenarioMode(StrEnum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    HISTORICAL_WHAT_IF = "HISTORICAL_WHAT_IF"
    FRESH_INPUT = "FRESH_INPUT"


@dataclass(frozen=True)
class PricingRuntimeContract:
    """Identity, money, version, and freshness metadata for one price result."""

    contract_version: str = "pricing.runtime.v1"
    timezone: str = "UTC"
    currency_code: str | None = None
    currency_status: CurrencyStatus = CurrencyStatus.UNVERIFIED_SOURCE_UNIT
    money_scale: int = 2
    rounding_mode: str = ROUND_HALF_UP
    advisory_only: bool = True

    @property
    def currency_label(self) -> str:
        return self.currency_code if self.currency_status is CurrencyStatus.VERIFIED and self.currency_code else "source currency units"

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "timezone": self.timezone,
            "currency_code": self.currency_code,
            "currency_status": self.currency_status.value,
            "currency_label": self.currency_label,
            "money_scale": self.money_scale,
            "rounding_mode": self.rounding_mode,
            "advisory_only": self.advisory_only,
        }
