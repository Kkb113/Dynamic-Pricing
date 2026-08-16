from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from audit.database_profile import ReadOnlyConnection, database_profile, schema_columns


class SourceDataChangedError(RuntimeError):
    """Raised when the live source no longer matches the accepted Phase 1 snapshot."""

    code = "SOURCE_DATA_CHANGED_SINCE_PHASE1"


def _phase1_metadata(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    fingerprint = json.loads((root / "artifacts/phase1/dataset_fingerprint.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "artifacts/phase1/phase1_manifest.json").read_text(encoding="utf-8"))
    metadata = fingerprint.get("canonical_metadata", {})
    schema = metadata.get("schema_reconciliation", {})
    expected = schema.get("documented", {})
    if not expected:
        expected = {
            "table_count": 24,
            "column_count": 224,
            "row_count": 328420,
            "table_rows": {
                "Pricing_Decision_Log": 35000,
                "Product_Price_History": 50000,
                "Competitor_Price": 40000,
                "Sales_Order_Line": 30000,
                "Sales_Order": 12000,
                "Inventory": 15000,
                "Product": 3000,
                "Customer": 5000,
                "Browsing_Events": 45000,
                "Cart_Events": 12000,
                "Search_Events": 12000,
                "Promotions": 200,
                "Pricing_Rules": 200,
                "Weather": 3650,
                "Holiday": 80,
            },
        }
    return expected, {"fingerprint": fingerprint, "manifest": manifest}


def _canonical_signature(profile: dict[str, Any], targets: dict[str, Any], decision_range: dict[str, Any]) -> str:
    payload = {
        "table_count": profile.get("table_count"),
        "column_count": profile.get("column_count"),
        "row_count": profile.get("row_count"),
        "tables": [
            {"table_name": row["table_name"], "column_count": row["column_count"], "row_count": row["row_count"]}
            for row in profile.get("tables", [])
        ],
        "targets": targets,
        "decision_range": decision_range,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def validate_source_snapshot(
    db: ReadOnlyConnection, root: Path, schema: str = "dbo", accepted_head: str | None = None
) -> dict[str, Any]:
    expected, phase1 = _phase1_metadata(root)
    profile = database_profile(db, schema)
    expected_rows = expected.get("table_rows", {})
    live_rows = {row["table_name"]: int(row["row_count"]) for row in profile["tables"]}
    table_checks = {
        table: {"expected": int(count), "actual": live_rows.get(table), "match": live_rows.get(table) == int(count)}
        for table, count in expected_rows.items()
    }
    target = db.row(
        f"""
        SELECT COUNT_BIG(*) AS total_rows,
               SUM(CASE WHEN PurchasedFlag=1 THEN 1 ELSE 0 END) AS purchase_count,
               SUM(CASE WHEN PurchasedFlag=0 THEN 1 ELSE 0 END) AS non_purchase_count,
               SUM(CASE WHEN PurchasedFlag IS NULL OR QuantityPurchased IS NULL THEN 1 ELSE 0 END) AS target_null_count
        FROM [{schema}].[Pricing_Decision_Log]
        """
    ) or {}
    decision_range = db.row(
        f"SELECT MIN(DecisionTime) AS min_decision_time, MAX(DecisionTime) AS max_decision_time FROM [{schema}].[Pricing_Decision_Log]"
    ) or {}
    targets = {
        "total_rows": int(target.get("total_rows") or 0),
        "purchase_count": int(target.get("purchase_count") or 0),
        "non_purchase_count": int(target.get("non_purchase_count") or 0),
        "target_null_count": int(target.get("target_null_count") or 0),
    }
    ranges = {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in decision_range.items()}
    checks = {
        "table_count": {"expected": int(expected.get("table_count", 24)), "actual": profile["table_count"]},
        "column_count": {"expected": int(expected.get("column_count", 224)), "actual": profile["column_count"]},
        "row_count": {"expected": int(expected.get("row_count", 328420)), "actual": profile["row_count"]},
        "pricing_decision_rows": {"expected": 35000, "actual": targets["total_rows"]},
        "purchases": {"expected": 6492, "actual": targets["purchase_count"]},
        "non_purchases": {"expected": 28508, "actual": targets["non_purchase_count"]},
        "target_null_count": {"expected": 0, "actual": targets["target_null_count"]},
        "decision_min": {"expected": "2025-01-01", "actual": str(ranges.get("min_decision_time", ""))[:10]},
        "decision_max": {"expected": "2025-12-31", "actual": str(ranges.get("max_decision_time", ""))[:10]},
    }
    for check in checks.values():
        check["match"] = check["expected"] == check["actual"]
    all_match = all(item["match"] for item in checks.values()) and all(item["match"] for item in table_checks.values())
    actual_signature = _canonical_signature(profile, targets, ranges)
    result = {
        "status": "MATCH" if all_match else "BLOCKED",
        "code": None if all_match else SourceDataChangedError.code,
        "accepted_phase1_head": accepted_head or phase1["manifest"].get("git_sha"),
        "accepted_dataset_fingerprint_sha256": phase1["fingerprint"].get("sha256"),
        "expected": expected,
        "live_profile": profile,
        "table_checks": table_checks,
        "checks": checks,
        "targets": targets,
        "decision_range": ranges,
        "live_source_signature": actual_signature,
    }
    if not all_match:
        raise SourceDataChangedError(json.dumps(result, sort_keys=True))
    return result
