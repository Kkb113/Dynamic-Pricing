"""Read-only service container and startup integrity state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app_services.artifact_registry import ArtifactRegistry
from app_services.model_performance_service import ModelPerformanceService
from app_services.recommendation_service import RecommendationService
from app_services.simulation_service import SimulationService


@dataclass
class ServiceContainer:
    """One process-local, read-only instance of the accepted service layer."""

    registry: Any
    recommendations: Any
    simulation: Any
    performance: Any
    integrity: dict[str, Any]

    @classmethod
    def create(cls, root: Path | str | None = None) -> "ServiceContainer":
        registry = ArtifactRegistry(root)
        integrity = registry.validate_integrity()
        return cls(
            registry=registry,
            recommendations=RecommendationService(registry),
            simulation=SimulationService(registry),
            performance=ModelPerformanceService(registry),
            integrity=integrity,
        )

    @property
    def ready(self) -> bool:
        return str(self.integrity.get("status", "")).upper() == "PASS"

    @property
    def integrity_status(self) -> str:
        return "pass" if self.ready else "blocked"

    def health(self, *, agent_available: bool) -> dict[str, Any]:
        return {
            "status": "ready" if self.ready else "blocked",
            "runtime": "local",
            "contract_version": "1",
            "agent_available": bool(agent_available),
            "artifacts_integrity": self.integrity_status,
        }


__all__ = ["ServiceContainer"]
