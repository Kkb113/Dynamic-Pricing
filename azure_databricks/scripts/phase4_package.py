"""Build a private App payload from the accepted model and allowlisted contexts.

No compute starts. Context projections remain in ignored build output and private
workspace files; never include source customer IDs, sessions, outcomes or affinities.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd
import yaml

from phase1 import ROOT, packed, digest, require, CONFIG_PATH, Cloud, make_plan
from phase3_live import authentication


def build(destination, *, model_path=None, product_catalog=None):
    destination = Path(destination)
    require(not destination.exists(), "Choose a new immutable payload directory")
    make_plan(ROOT, json.loads(CONFIG_PATH.read_text()))
    acceptance = json.loads((ROOT / "azure_databricks/evidence/phase_03/cloud_registration.json").read_text())
    require(acceptance["status"] == "PASS" and acceptance["model_version"] == "1", "Phase 3 acceptance missing")
    features = json.loads((ROOT / "artifacts/phase4/frozen_model_spec.json").read_text())["ordered_feature_names"]
    columns = list(dict.fromkeys(features + ["PricingDecisionID", "DecisionTime", "ProductID", "StoreID", "CostPrice"]))
    prohibited = {"CustomerID", "SessionID", "PurchasedFlag", "ActualRevenue", "QuantityPurchased", "CustomerSegment", "LoyaltyTier", "PriceSensitivity"}
    require(not prohibited.intersection(columns), "Unsafe inference projection")
    sources = [ROOT / f"artifacts/phase8/{split}_factual_backtest.parquet" for split in ("validation", "test")]
    contexts = pd.concat([pd.read_parquet(p, columns=columns) for p in sources], ignore_index=True)
    require(len(contexts) == 10500 and contexts.PricingDecisionID.is_unique, "Context reconciliation failed")
    names = {}
    catalog_hash = None
    if product_catalog:
        catalog = pd.read_parquet(product_catalog, columns=["ProductID", "ProductName", "CategoryID", "BrandID"])
        require(catalog.ProductID.is_unique, "Ambiguous product catalog")
        matched = contexts[["ProductID", "CategoryID", "BrandID"]].drop_duplicates().merge(
            catalog, on=["ProductID", "CategoryID", "BrandID"], how="inner", validate="many_to_one")
        require(matched.ProductID.is_unique, "Conflicting product attributes")
        names = dict(zip(matched.ProductID, matched.ProductName, strict=True))
        catalog_hash = digest(Path(product_catalog).read_bytes())
    destination.mkdir(parents=True)
    contexts.to_parquet(destination / "contexts.parquet", index=False)
    policy = ROOT / "artifacts/azure_databricks/phase3/policy"
    policy_manifest = json.loads((policy / "manifest.json").read_text())
    for item in policy_manifest["files"]:
        require(digest((policy / item["path"]).read_bytes()) == item["sha256"], "Policy drift")
        shutil.copyfile(policy / item["path"], destination / item["path"])
    if model_path:
        shutil.copytree(model_path, destination / "model", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        import mlflow
        cfg = json.loads(CONFIG_PATH.read_text())
        cloud = Cloud(cfg)
        with authentication(cloud.client, cfg["host"]):
            downloaded = mlflow.artifacts.download_artifacts(
                artifact_uri="models:/" + acceptance["model_name"] + "/1", dst_path=str(destination / "download"))
            shutil.copytree(downloaded, destination / "model", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        # Download is an ignored build cache; manifest packages only model/.
    # MLflow code-model loading uses the host OS basename. Windows absolute
    # paths in registered metadata otherwise fail when deployed on Linux.
    metadata_path = destination / "model/MLmodel"
    original_metadata = metadata_path.read_bytes()
    metadata = yaml.safe_load(original_metadata)
    entry = metadata["flavors"]["python_function"]["model_code_path"]
    portable_entry = entry.replace("\\", "/").rsplit("/", 1)[-1]
    require(portable_entry == "phase3_model.py", "Unexpected model entry point")
    require((destination / "model" / portable_entry).is_file(), "Model entry point missing")
    metadata["flavors"]["python_function"]["model_code_path"] = portable_entry
    metadata_path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
    adaptation = {"kind": "PORTABLE_MODEL_CODE_PATH_ONLY",
                  "registered_metadata_sha256": digest(original_metadata),
                  "app_metadata_sha256": digest(metadata_path.read_bytes()),
                  "entry_point": portable_entry}
    # One explicitly versioned source adaptation removes an eager database-only
    # dependency. Retain the original model weights and disclose the code delta.
    audit_path = destination / "model/code/audit/database_profile.py"
    original_audit = audit_path.read_bytes().replace(b"\r\n", b"\n")
    source_plan = json.loads((destination / "model/artifacts/inference/pricing_release.json").read_text())
    accepted_audit = next(item for item in source_plan["code"] if item["path"] == "src/audit/database_profile.py")
    require(digest(original_audit) == accepted_audit["sha256"], "Registered audit source drift")
    expected_audit = original_audit.replace(
        b"from typing import Any, Iterable\n\nimport pyodbc\n",
        b"from typing import TYPE_CHECKING, Any, Iterable\n\nif TYPE_CHECKING:\n    import pyodbc\n",
    ).replace(
        b'    raw = raw_connection if raw_connection is not None else os.environ.get(connection_env or "", "")',
        b'    # Database drivers are needed only for an explicit database operation, not\n'
        b'    # for the pure pricing functions imported by the packaged inference model.\n'
        b'    import pyodbc\n\n'
        b'    raw = raw_connection if raw_connection is not None else os.environ.get(connection_env or "", "")',
    )
    updated_audit = expected_audit
    require(updated_audit != original_audit, "Expected database import adaptation missing")
    audit_path.write_bytes(updated_audit)
    adaptation["source_revision"] = {
        "kind": "LAZY_DATABASE_DRIVER_IMPORT_V1", "path": "code/audit/database_profile.py",
        "original_sha256": digest(original_audit), "app_sha256": digest(updated_audit),
        "registered_model_unchanged": True,
    }
    files = {}
    for path in sorted(destination.rglob("*")):
        if path.is_file() and "download" not in path.relative_to(destination).parts:
            files[path.relative_to(destination).as_posix()] = digest(path.read_bytes())
    manifest = {"release_seal": acceptance["release_seal"], "model_name": acceptance["model_name"],
        "model_version": "1", "advisory_only": True, "contexts": 10500, "feature_columns": columns,
        "source_hashes": {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in sources},
        "files": files, "customer_records_included": False, "live_data": False,
        "product_names": names, "product_catalog_sha256": catalog_hash,
        "packaging_adaptation": adaptation,
        "product_mapping": "ID_AND_CATEGORY_AND_BRAND_MATCH_ONLY"}
    (destination / "pricing-manifest.json").write_bytes(packed(manifest))
    return {"status": "PREPARED_PRIVATE", "contexts": 10500, "files": len(files),
            "manifest_sha256": digest(packed(manifest)), "compute_started": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--product-catalog", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.destination, model_path=args.model_path, product_catalog=args.product_catalog), indent=2))
