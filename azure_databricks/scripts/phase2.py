"""Frozen-snapshot lakehouse contracts. Local plan performs no cloud operations."""
from __future__ import annotations

import argparse
import json
import io
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from phase1 import ROOT, CONFIG_PATH, make_plan, packed, require, digest

VERSION = "pricing.lakehouse.v1"
SOURCES = {
    "features": ("artifacts/phase2/feature_dataset.parquet", 35000, ["PricingDecisionID"]),
    "splits": ("artifacts/phase3/split_assignments.parquet", 35000, ["PricingDecisionID"]),
    "validation_candidates": ("artifacts/phase6/validation_candidate_surface.parquet", 47250,
                              ["PricingDecisionID", "CandidatePrice"]),
    "validation_model_decisions": ("artifacts/phase6/validation_recommendations.parquet", 5250,
                                   ["PricingDecisionID"]),
    "inventory_decisions": ("artifacts/phase7/current_inventory_business_decisions.parquet", 1829,
                            ["PricingDecisionID"]),
    "test_decisions": ("artifacts/phase7/test_business_decisions.parquet", 5250, ["PricingDecisionID"]),
    "validation_decisions": ("artifacts/phase7/validation_business_decisions.parquet", 5250,
                             ["PricingDecisionID"]),
    "validation_outcomes": ("artifacts/phase8/validation_factual_backtest.parquet", 5250,
                            ["PricingDecisionID"]),
}
CHANNELS = {"Email", "Kiosk", "Mobile", "Online", "Store", "Web"}
BUSINESS_COLUMNS = ["PricingDecisionID", "DecisionTime", "ProductID", "StoreID", "Channel",
                    "CurrentPrice", "FinalRecommendedPrice", "FinalAction", "manual_review_flag",
                    "phase7_change_reason_codes", "InventorySnapshotDate", "AvailableQty"]
MONEY_COLUMNS = {"CurrentPrice", "FinalRecommendedPrice"}


def identifier(value):
    require(bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)), "Unsafe SQL identifier")
    return "`" + value + "`"


def sql_type(field):
    """Explicit logical schema, including all-null Arrow and empty-list columns."""
    t = field.type
    if pa.types.is_null(t):
        require(field.name == "StockStatus", "Uncontracted null-only field: " + field.name)
        return "STRING"
    if pa.types.is_list(t) or pa.types.is_large_list(t):
        require(pa.types.is_string(t.value_type) or pa.types.is_null(t.value_type), "Unexpected array")
        return "ARRAY<STRING>"
    if pa.types.is_string(t) or pa.types.is_large_string(t):
        return "STRING"
    if pa.types.is_timestamp(t):
        require(t.tz is None, "Unexpected source timezone")
        return "TIMESTAMP_NTZ"
    if pa.types.is_boolean(t):
        return "BOOLEAN"
    if pa.types.is_integer(t):
        return "BIGINT"
    if pa.types.is_floating(t):
        return "DOUBLE"
    if pa.types.is_decimal(t):
        return f"DECIMAL({t.precision},{t.scale})"
    raise RuntimeError("Uncontracted Arrow type: " + str(t))


def money(value):
    """Business presentation only; original scoring doubles stay unchanged."""
    d = Decimal(str(value))
    require(d.is_finite(), "Non-finite monetary value")
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compatible_parquet(path):
    """Lossless timestamp-unit normalization for SQL; originals remain untouched."""
    table = pq.read_table(path)
    fields = []
    for field in table.schema:
        kind = field.type
        if pa.types.is_timestamp(kind):
            kind = pa.timestamp("us")
        elif pa.types.is_null(kind):
            require(field.name == "StockStatus", "Unexpected untyped column")
            kind = pa.string()
        elif pa.types.is_list(kind) and pa.types.is_null(kind.value_type):
            kind = pa.list_(pa.string())
        fields.append(pa.field(field.name, kind, nullable=field.nullable))
    converted = table.cast(pa.schema(fields), safe=True)
    # Safe casting fails if any submicrosecond precision would be discarded.
    buffer = io.BytesIO()
    pq.write_table(converted, buffer, version="2.6", compression="snappy")
    return buffer.getvalue(), converted.schema


def validate_frames(frames):
    evidence = {}
    for name, (_, rows, keys) in SOURCES.items():
        f = frames[name]
        require(len(f) == rows, name + ": row count mismatch")
        require(not f[keys].isna().any().any(), name + ": null key")
        require(not f.duplicated(keys).any(), name + ": duplicate key")
        if "Channel" in f:
            require(not f.Channel.isna().any() and set(f.Channel).issubset(CHANNELS), name + ": channel")
        evidence[name] = {"rows": len(f), "unique_keys": True, "null_keys": 0}
    f, s = frames["features"], frames["splits"]
    joined = f.merge(s, on="PricingDecisionID", validate="one_to_one", suffixes=("", "_split"), how="outer", indicator=True)
    require(joined._merge.eq("both").all(), "Feature/split key mismatch")
    require(joined.DecisionTime.eq(joined.DecisionTime_split).all(), "Split timestamp mismatch")
    require(joined.split.value_counts().to_dict() == {"train": 24500, "validation": 5250, "test": 5250}, "Split counts")
    boundaries = {}
    previous = None
    for split in ("train", "validation", "test"):
        times = joined.loc[joined.split.eq(split), "DecisionTime"]
        require(times.notna().all(), "Missing decision time")
        require(previous is None or previous < times.min(), "Temporal split overlap")
        previous = times.max()
        boundaries[split] = {"start": times.min().isoformat(), "end": times.max().isoformat()}
    for c in ("selected_price_effective_from", "selected_sales_order_date",
              "selected_competitor_observed_at", "selected_behavior_event_at"):
        require(not (pd.to_datetime(f[c]) > f.DecisionTime).any(), "Future context: " + c)
    ends = pd.to_datetime(f.selected_price_effective_to)
    require(not (ends.notna() & (f.DecisionTime >= ends)).any(), "Price interval not half-open")
    for name in ("validation_decisions", "test_decisions", "validation_outcomes", "validation_model_decisions"):
        split = "test" if name == "test_decisions" else "validation"
        require(set(frames[name].PricingDecisionID) == set(s.loc[s.split.eq(split), "PricingDecisionID"]), name + ": split membership")
    require(set(frames["validation_candidates"].PricingDecisionID) ==
            set(frames["validation_decisions"].PricingDecisionID), "Candidate membership mismatch")
    require(frames["validation_candidates"].groupby("PricingDecisionID").size().eq(9).all(), "Candidate count mismatch")
    for name in ("validation_decisions", "test_decisions", "inventory_decisions"):
        d = frames[name]
        require(d[["ProductID", "StoreID", "Channel", "DecisionTime", "CostPrice", "CurrentPrice", "BasePrice"]].notna().all().all(), name + ": missing required context")
        require(d.CostPrice.map(lambda x: Decimal(str(x)).is_finite() and x > 0).all(), "Invalid cost")
        for column in ("CurrentPrice", "BasePrice", "FinalRecommendedPrice"):
            require(d[column].dropna().map(lambda x: Decimal(str(x)).is_finite() and x > 0).all(),
                    "Invalid price: " + column)
        require(d.ADVISORY_ONLY.eq(True).all() and d.AUTO_WRITEBACK.eq(False).all(), "Unsafe writeback contract")
        require((d.FinalRecommendedPrice.notna() | d.manual_review_flag).all(), "Missing price without review")
        require((d.FinalRecommendedPrice.dropna() > 0).all(), "Non-positive recommendation")
        if name == "inventory_decisions":
            require(pd.to_datetime(d.InventorySnapshotDate).eq(pd.Timestamp("2025-12-31")).all(), "Inventory snapshot changed")
        else:
            require(d.InventorySnapshotDate.isna().all() and d.AvailableQty.isna().all(), "Future inventory in historical replay")
            j = d.merge(f[["PricingDecisionID", "ProductID", "StoreID", "Channel", "DecisionTime"]],
                        on="PricingDecisionID", validate="one_to_one", suffixes=("", "_feature"))
            require(all(j[c].eq(j[c + "_feature"]).all() for c in ("ProductID", "StoreID", "Channel", "DecisionTime")), "Decision context mismatch")
        evidence[name]["manual_review_rows"] = int(d.manual_review_flag.sum())
        evidence[name]["missing_price_rows"] = int(d.FinalRecommendedPrice.isna().sum())
    return {"status": "PASS", "sources": evidence, "split_boundaries": boundaries,
            "temporal_audit": "Available source audit columns checked; raw history not independently rebuilt",
            "raw_source_refresh": "UNAVAILABLE_FROZEN_SNAPSHOT_ONLY"}


def build_plan(root=ROOT):
    config = json.loads(CONFIG_PATH.read_text())
    release = make_plan(root, config)
    entries = {x["path"]: x for x in release["files"]}
    frames = {n: pd.read_parquet(root / spec[0]) for n, spec in SOURCES.items()}
    validation = validate_frames(frames)
    suffix = release["phase0_manifest_sha256"][:12]
    tables = []
    for name, (path, count, keys) in SOURCES.items():
        compatibility, schema = compatible_parquet(root / path)
        fields = [{"name": f.name, "type": sql_type(f)} for f in schema]
        # Explicit schema is supplied to read_files, avoiding Spark inference for NULL/list<NULL>.
        ddl = ", ".join(identifier(f["name"]) + " " + f["type"] for f in fields)
        compatibility_hash = digest(compatibility)
        source = release["roots"]["restricted"].rsplit("/", 1)[0] + "/lakehouse/" + compatibility_hash + ".parquet"
        query = "SELECT * FROM read_files('" + source + "', format => 'parquet', schema => '" + ddl + "')"
        tables.append({"name": name, "table": config["catalog"] + ".pricing_silver." + name + "_" + suffix,
                       "source": source, "original_path": path, "source_sha256": entries[path]["sha256"],
                       "compatibility_sha256": compatibility_hash, "compatibility_bytes": len(compatibility), "rows": count,
                       "keys": keys, "fields": fields, "query": query})
    versions = {name: entries[path]["sha256"] for name, path in {
        "model_version": "artifacts/phase4/models/purchase_catboost.cbm",
        "policy_version": "artifacts/phase7/frozen_business_policy_spec.json",
        "data_version": "artifacts/phase2/feature_dataset.parquet"}.items()}
    return {"contract_version": VERSION, "release_id": release["release_id"], "versions": versions,
            "manifest_sha256": release["phase0_manifest_sha256"], "tables": tables,
            "validation": validation, "currency_status": "UNVERIFIED_SOURCE_UNIT",
            "inventory_as_of": "2025-12-31", "combined_tools_enabled": False,
            "mapping_status": "PENDING_LIVE_RECONCILIATION", "compute_started": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["plan"])
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = build_plan()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(packed(result))
    print(json.dumps({"status": result["validation"]["status"], "tables": len(result["tables"]),
                      "compute_started": False}))


if __name__ == "__main__":
    main()
