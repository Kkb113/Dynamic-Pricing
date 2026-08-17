from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from audit.database_profile import connect_read_only, load_env_file
from validation.artifacts import sha256_file, write_json


def _connection_string(project_root: Path) -> str:
    env_path = Path(os.environ.get("PHASE6_ENV_FILE", project_root / ".env"))
    values = load_env_file(env_path)
    required = ["SQL_SERVER_DATABASE", "SQL_SERVER_USER_NAME", "SQL_SERVER_PASSWORD"]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError("COST_INPUT_UNAVAILABLE")
    server = os.environ.get("PHASE6_SQL_SERVER", "localhost")
    return ";".join([
        f"Server={server}", f"Database={values['SQL_SERVER_DATABASE']}",
        f"UID={values['SQL_SERVER_USER_NAME']}", f"PWD={values['SQL_SERVER_PASSWORD']}",
        "Encrypt=no", "TrustServerCertificate=yes",
    ])


def resolve_cost_prices(
    context: pd.DataFrame,
    *,
    project_root: Path,
    artifact_dir: Path,
    schema: str = "dbo",
    batch_size: int = 500,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Resolve static optimizer-only CostPrice from Phase 2 or read-only Product."""

    result = context.copy()
    product_ids = result["ProductID"].astype(str)
    if "CostPrice" in result.columns:
        costs = pd.to_numeric(result["CostPrice"], errors="coerce")
        source = "phase2_frame"
        sidecar = pd.DataFrame({"ProductID": product_ids.unique(), "CostPrice": costs.groupby(product_ids).first().reindex(product_ids.unique()).to_numpy()})
    else:
        unique_ids = sorted(product_ids.dropna().unique().tolist())
        if not unique_ids:
            raise RuntimeError("COST_INPUT_UNAVAILABLE")
        rows: list[dict[str, Any]] = []
        try:
            raw = _connection_string(project_root)
            ctx = connect_read_only(None, "ODBC Driver 18 for SQL Server", 30, raw_connection=raw)
            db = ctx.__enter__()
            try:
                for start in range(0, len(unique_ids), batch_size):
                    chunk = unique_ids[start:start + batch_size]
                    placeholders = ",".join("?" for _ in chunk)
                    rows.extend(db.rows(f"SELECT [ProductID], [CostPrice] FROM [{schema}].[Product] WHERE [ProductID] IN ({placeholders})", chunk))
            finally:
                ctx.__exit__(None, None, None)
        except Exception as exc:
            raise RuntimeError("COST_INPUT_UNAVAILABLE") from exc
        sidecar = pd.DataFrame(rows, columns=["ProductID", "CostPrice"])
        source = "dbo.Product.CostPrice_read_only"
        if sidecar.empty:
            raise RuntimeError("COST_INPUT_UNAVAILABLE")
    sidecar["ProductID"] = sidecar["ProductID"].astype(str)
    sidecar["CostPrice"] = pd.to_numeric(sidecar["CostPrice"], errors="coerce")
    sidecar = sidecar.drop_duplicates("ProductID", keep="last").sort_values("ProductID", kind="mergesort").reset_index(drop=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = artifact_dir / "product_cost_sidecar.parquet"
    sidecar.to_parquet(sidecar_path, index=False)
    lookup = sidecar.set_index("ProductID")["CostPrice"]
    result["CostPrice"] = product_ids.map(lookup).to_numpy()
    coverage = float(result["CostPrice"].notna().mean()) if len(result) else 0.0
    invalid = (~np.isfinite(result["CostPrice"].to_numpy(float))) | (result["CostPrice"].to_numpy(float) <= 0)
    if coverage < 1.0:
        raise RuntimeError("COST_INPUT_UNAVAILABLE")
    if invalid.any():
        raise RuntimeError("COST_INPUT_INVALID")
    prices = result["CostPrice"].to_numpy(float)
    audit = {
        "source": source,
        "sidecar_path": str(sidecar_path.relative_to(project_root).as_posix()) if sidecar_path.is_relative_to(project_root) else str(sidecar_path.as_posix()),
        "sidecar_sha256": sha256_file(sidecar_path),
        "decision_rows": int(len(result)),
        "unique_products": int(result["ProductID"].nunique()),
        "covered_rows": int(len(result) - int(invalid.sum())),
        "coverage_rate": coverage,
        "missing_count": int(result["CostPrice"].isna().sum()),
        "invalid_count": int(invalid.sum()),
        "min": float(prices.min()),
        "max": float(prices.max()),
        "mean": float(prices.mean()),
        "median": float(np.median(prices)),
        "cost_gt_current_count": int((result["CostPrice"] > result["CurrentPrice"]).sum()),
        "cost_gt_current_rate": float((result["CostPrice"] > result["CurrentPrice"]).mean()),
        "cost_gt_base_count": int((result["CostPrice"] > result["BasePrice"]).sum()),
        "cost_gt_base_rate": float((result["CostPrice"] > result["BasePrice"]).mean()),
        "optimizer_only": True,
        "static_cost_limitation": "Product.CostPrice is a static reference; historical cost variation is unavailable in Phase 2.",
    }
    write_json(artifact_dir / "cost_audit.json", audit)
    return result, audit


__all__ = ["resolve_cost_prices"]
