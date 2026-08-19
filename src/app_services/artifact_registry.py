"""Central, read-only access to the accepted Phase 4--8 artifacts.

The application deliberately loads small, allowlisted projections.  In
particular, recommendation and simulation contexts never read outcome or PII
columns, even though the Phase 8 factual artifact contains those columns for
evaluation only.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


OUTCOME_FIELDS = frozenset(
    {"PurchasedFlag", "QuantityPurchased", "ActualRevenue", "OutcomeTime", "OrderLineID"}
)
PII_FIELDS = frozenset(
    {"CustomerID", "CustomerName", "CustomerEmail", "Email", "Phone", "Address", "SessionID"}
)


class ArtifactIntegrityError(RuntimeError):
    """Raised when an accepted artifact is missing or has the wrong digest."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ArtifactPaths:
    phase4_model: Path
    phase4_spec: Path
    phase5_estimator: Path
    phase5_spec: Path
    phase6_spec: Path
    phase6_surface: Path
    phase6_recommendations: Path
    phase7_manifest: Path
    phase7_policy: Path
    phase7_validation: Path
    phase7_test: Path
    phase7_current: Path
    phase8_manifest: Path
    phase8_eval_spec: Path
    phase8_metrics: Path
    phase8_scenario_summary: Path


class ArtifactRegistry:
    """Read-only registry for frozen model, economics, and business artifacts."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or os.environ.get("DYNAMIC_PRICING_ROOT", Path(__file__).resolve().parents[2])).resolve()
        self.paths = ArtifactPaths(
            phase4_model=self.root / "artifacts/phase4/models/purchase_catboost.cbm",
            phase4_spec=self.root / "artifacts/phase4/frozen_model_spec.json",
            phase5_estimator=self.root / "artifacts/phase5/models/quantity_estimator_metadata.json",
            phase5_spec=self.root / "artifacts/phase5/frozen_quantity_spec.json",
            phase6_spec=self.root / "artifacts/phase6/frozen_optimizer_spec.json",
            phase6_surface=self.root / "artifacts/phase6/validation_candidate_surface.parquet",
            phase6_recommendations=self.root / "artifacts/phase6/validation_recommendations.parquet",
            phase7_manifest=self.root / "artifacts/phase7/phase7_manifest.json",
            phase7_policy=self.root / "artifacts/phase7/frozen_business_policy_spec.json",
            phase7_validation=self.root / "artifacts/phase7/validation_business_decisions.parquet",
            phase7_test=self.root / "artifacts/phase7/test_business_decisions.parquet",
            phase7_current=self.root / "artifacts/phase7/current_inventory_business_decisions.parquet",
            phase8_manifest=self.root / "artifacts/phase8/phase8_manifest.json",
            phase8_eval_spec=self.root / "artifacts/phase8/frozen_evaluation_spec.json",
            phase8_metrics=self.root / "artifacts/phase8/test_factual_metrics.json",
            phase8_scenario_summary=self.root / "artifacts/phase8/test_scenario_summary.json",
        )
        self._validate_cache: dict[str, Any] | None = None

    @property
    def phase4_feature_names(self) -> tuple[str, ...]:
        return tuple(_json(self.paths.phase4_spec)["ordered_feature_names"])

    @property
    def phase6_spec(self) -> dict[str, Any]:
        return _json(self.paths.phase6_spec)

    @property
    def phase7_policy(self) -> dict[str, Any]:
        return _json(self.paths.phase7_policy)

    @property
    def phase8_manifest(self) -> dict[str, Any]:
        return _json(self.paths.phase8_manifest)

    def _require(self, paths: Iterable[Path]) -> list[str]:
        return [path.relative_to(self.root).as_posix() for path in paths if not path.exists()]

    def _expected_hashes(self) -> dict[Path, str]:
        if not self.paths.phase8_manifest.exists():
            return {}
        manifest = self.phase8_manifest
        upstream = manifest.get("upstream_validation", {})
        fingerprints = upstream.get("fingerprints", {})
        phase7_upstream = upstream.get("phase7_upstream", {})
        phase6_manifest = phase7_upstream.get("phase6_manifest", {})
        optimizer = phase7_upstream.get("frozen_optimizer_spec", {})
        recommendation_fingerprints = phase6_manifest.get("recommendation_fingerprints", {})
        candidate_fingerprints = phase7_upstream.get("candidate_surface_fingerprints", {})
        expected: dict[Path, str] = {
            self.paths.phase7_manifest: fingerprints.get("manifest_sha256", ""),
            self.paths.phase7_policy: fingerprints.get("frozen_policy_sha256", ""),
            self.paths.phase7_validation: fingerprints.get("validation_decisions_sha256", ""),
            self.paths.phase7_test: fingerprints.get("test_decisions_sha256", ""),
            self.paths.phase7_current: fingerprints.get("current_decisions_sha256", ""),
            self.paths.phase6_spec: optimizer.get("spec_sha256", ""),
            self.paths.phase6_surface: candidate_fingerprints.get("validation", ""),
            self.paths.phase6_recommendations: recommendation_fingerprints.get("validation", ""),
            self.paths.phase8_eval_spec: manifest.get("frozen_evaluation_spec_sha256", ""),
            self.paths.phase4_model: optimizer.get("phase4_model_sha", ""),
            self.paths.phase5_estimator: optimizer.get("phase5_estimator_fingerprint", ""),
        }
        return {path: value for path, value in expected.items() if value}

    def validate_integrity(self, *, raise_on_error: bool = False) -> dict[str, Any]:
        """Validate critical hashes and return a serializable startup report."""

        if self._validate_cache is not None:
            return dict(self._validate_cache)
        required = [
            self.paths.phase4_model,
            self.paths.phase4_spec,
            self.paths.phase5_estimator,
            self.paths.phase5_spec,
            self.paths.phase6_spec,
            self.paths.phase6_surface,
            self.paths.phase6_recommendations,
            self.paths.phase7_manifest,
            self.paths.phase7_policy,
            self.paths.phase7_validation,
            self.paths.phase7_test,
            self.paths.phase7_current,
            self.paths.phase8_manifest,
            self.paths.phase8_eval_spec,
            self.paths.phase8_metrics,
            self.paths.phase8_scenario_summary,
        ]
        missing = self._require(required)
        mismatches: list[dict[str, str]] = []
        for path, expected in self._expected_hashes().items():
            if not path.exists():
                continue
            actual = sha256_file(path)
            if actual != expected:
                mismatches.append({"path": path.relative_to(self.root).as_posix(), "expected": expected, "actual": actual})
        manifest = self.phase8_manifest if self.paths.phase8_manifest.exists() else {}
        blockers = list(manifest.get("major_blockers", []))
        result = manifest.get("result", manifest.get("acceptance", {}).get("status"))
        if result not in {"PASS", "PASS_WITH_WARNINGS"}:
            blockers.append("UPSTREAM_ARTIFACT_INTEGRITY_FAILURE")
        if missing or mismatches or blockers:
            report = {
                "status": "BLOCKED",
                "code": "ARTIFACT_INTEGRITY_FAILURE",
                "missing": missing,
                "hash_mismatches": mismatches,
                "major_blockers": sorted(set(blockers)),
                "phase8_result": result,
            }
            if raise_on_error:
                raise ArtifactIntegrityError(json.dumps(report, sort_keys=True))
        else:
            report = {
                "status": "PASS",
                "code": "OK",
                "missing": [],
                "hash_mismatches": [],
                "major_blockers": [],
                "phase8_result": result,
            }
        self._validate_cache = dict(report)
        return report

    def _load(self, path: Path, columns: list[str] | None = None) -> pd.DataFrame:
        if columns:
            return pd.read_parquet(path, columns=columns)
        return pd.read_parquet(path)

    @lru_cache(maxsize=4)
    def load_decisions(self, split: str = "validation") -> pd.DataFrame:
        path = {"validation": self.paths.phase7_validation, "test": self.paths.phase7_test, "current": self.paths.phase7_current}.get(split)
        if path is None:
            raise ValueError(f"Unknown decision split: {split}")
        frame = self._load(path).copy()
        return frame

    @lru_cache(maxsize=2)
    def load_candidate_surface(self, split: str = "validation") -> pd.DataFrame:
        if split != "validation":
            raise ValueError("Only the accepted validation candidate surface is exposed to the application")
        return self._load(self.paths.phase6_surface).copy()

    @lru_cache(maxsize=2)
    def load_recommendations(self, split: str = "validation") -> pd.DataFrame:
        if split != "validation":
            raise ValueError("Only the accepted validation recommendation surface is exposed to the application")
        return self._load(self.paths.phase6_recommendations).copy()

    @lru_cache(maxsize=2)
    def load_feature_context(self, split: str = "validation") -> pd.DataFrame:
        """Load only model features and cost; never read outcomes or PII."""

        if split != "validation":
            raise ValueError("Only validation feature context is supported")
        factual_path = self.root / "artifacts/phase8/validation_factual_backtest.parquet"
        columns = ["PricingDecisionID", "CostPrice", *self.phase4_feature_names]
        try:
            import pyarrow.parquet as pq

            available = set(pq.ParquetFile(factual_path).schema.names)
        except Exception:
            # The application dependency set includes pyarrow; this fallback
            # keeps a useful error path for unusually minimal environments.
            available = set(columns)
        selected = [column for column in dict.fromkeys(columns) if column in available]
        frame = self._load(factual_path, selected).copy()
        forbidden = (OUTCOME_FIELDS | PII_FIELDS).intersection(frame.columns)
        if forbidden:
            raise ArtifactIntegrityError(f"Forbidden fields loaded into feature context: {sorted(forbidden)}")
        return frame

    @lru_cache(maxsize=1)
    def load_metrics(self) -> dict[str, Any]:
        return _json(self.paths.phase8_metrics)

    @lru_cache(maxsize=1)
    def load_scenario_summary(self) -> dict[str, Any]:
        return _json(self.paths.phase8_scenario_summary)

    @lru_cache(maxsize=1)
    def load_current_inventory(self) -> pd.DataFrame:
        return self.load_decisions("current")

    def runtime_environment(self) -> dict[str, Any]:
        logical = os.cpu_count() or 1
        physical = logical
        try:
            import psutil

            physical = psutil.cpu_count(logical=False) or logical
        except Exception:
            pass
        return {
            "os": platform.platform(),
            "python": sys.version,
            "catboost": _package_version("catboost"),
            "openai_agents": _package_version("openai-agents"),
            "openai": _package_version("openai"),
            "streamlit": _package_version("streamlit"),
            "plotly": _package_version("plotly"),
            "numpy": _package_version("numpy"),
            "pandas": _package_version("pandas"),
            "physical_cores": int(physical),
            "logical_threads": int(logical),
            "threads_used": min(int(logical), 22),
        }

    def outcome_access_audit(self) -> dict[str, Any]:
        return {
            "outcome_fields_exposed": [],
            "historical_outcome_row_fields_exposed": [],
            "PII_fields_exposed": [],
            "api_key_exposed": False,
            "sql_write_paths": [],
        }


def _package_version(name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


__all__ = ["ArtifactIntegrityError", "ArtifactRegistry", "OUTCOME_FIELDS", "PII_FIELDS", "sha256_file"]
