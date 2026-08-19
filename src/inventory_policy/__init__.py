"""Current-snapshot inventory and seasonal markdown policy."""

from .inventory_loader import load_inventory, validate_inventory
from .inventory_policy import (
    CURRENT_INVENTORY_MODE,
    HISTORICAL_POLICY_MODE,
    resolve_current_inventory,
)
from .markdown_policy import derive_slow_moving_thresholds, markdown_eligibility

__all__ = [
    "CURRENT_INVENTORY_MODE",
    "HISTORICAL_POLICY_MODE",
    "derive_slow_moving_thresholds",
    "load_inventory",
    "markdown_eligibility",
    "resolve_current_inventory",
    "validate_inventory",
]
