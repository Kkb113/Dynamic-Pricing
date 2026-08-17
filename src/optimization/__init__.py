"""Phase 6 candidate-price simulation and optimizer primitives."""

from .candidate_grid import FIXED_MULTIPLIERS, CandidateGrid, build_candidate_grid
from .economics import score_economics
from .price_selector import select_model_optimal_prices
from .response_safety import apply_response_safety

__all__ = [
    "FIXED_MULTIPLIERS",
    "CandidateGrid",
    "build_candidate_grid",
    "score_economics",
    "select_model_optimal_prices",
    "apply_response_safety",
]
