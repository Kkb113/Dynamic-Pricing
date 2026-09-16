"""Local Phase 3 packaging and acceptance; never starts cloud compute."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
import subprocess
import os
from pathlib import Path

from phase1 import ROOT, CONFIG_PATH, make_plan, packed, digest, require
from pricing_mlflow.pipeline import PricingPipeline, VERSION, clean
import numpy as np
import pandas as pd

INFERENCE_FILES = (
    "contracts/phase2_feature_contract_v1.yaml",
    "artifacts/phase4/models/purchase_catboost.cbm",
    "artifacts/phase4/frozen_model_spec.json",
    "artifacts/phase5/models/quantity_estimator_metadata.json",
    "artifacts/phase6/frozen_optimizer_spec.json",
    "artifacts/phase7/frozen_business_policy_spec.json",
)


def plan():
    config = json.loads(CONFIG_PATH.read_text())
    sealed = make_plan(ROOT, config)
    files = [{"path": p, "sha256": digest((ROOT / p).read_bytes()), "bytes": (ROOT / p).stat().st_size}
             for p in INFERENCE_FILES]
    code = [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p.read_bytes().replace(b"\r\n", b"\n"))}
            for p in sorted((ROOT / "src").rglob("*.py"))]
    return {"schema_version": VERSION, "source_release": sealed["release_id"],
            "model_name": config["catalog"] + ".pricing_ml.pricing_decision_pipeline",
            "experiment": "/Shared/dynamic-pricing/phase3-pricing",
            "files": files, "code": code, "package_bytes": sum(x["bytes"] for x in files),
            "contains_row_level_data": False, "compute_started": False,
            "dedicated_endpoint": False, "advisory_only": True, "automatic_writeback": False,
            "signature": {"input": {"request_json": "string"}, "output": {"response_json": "string"}},
            "runtime": "requirements-runtime.lock + mlflow-skinny==3.16.0 + pyodbc==5.3.0",
            "policy_snapshot_status": "ORIGINAL_RULE_AND_PROMOTION_ROWS_NOT_IN_IMMUTABLE_RELEASE"}


def inference_bundle(destination):
    destination = Path(destination)
    require(not destination.exists(), "Bundle destination already exists")
    destination.mkdir(parents=True)
    for p in INFERENCE_FILES:
        target = destination / p
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / p, target)
    (destination / "pricing_release.json").write_bytes(packed(plan()))
    require(not list(destination.rglob("*.parquet")), "Dataset embedded in inference package")
    return destination


def request(context, **extra):
    return {"schema_version": VERSION, "context": clean(context.to_dict("records")),
            "rules": [], "promotions": [], "inventory": [], "mode": "HISTORICAL_POLICY_MODE", **extra}


def example(pipeline=None):
    pipeline = pipeline or PricingPipeline(ROOT)
    columns = list(pipeline.scorer.feature_names) + ["PricingDecisionID", "DecisionTime", "ProductID", "StoreID", "CostPrice"]
    context = pd.read_parquet(ROOT / "artifacts/phase8/validation_factual_backtest.parquet", columns=list(dict.fromkeys(columns))).head(1)
    return pd.DataFrame({"request_json": [json.dumps(request(context), allow_nan=False)]})


def validate_local():
    started = time.perf_counter()
    pipeline = PricingPipeline(ROOT)
    result = {"status": "PASS", "compute_started": False, "no_training": True, "splits": {}}
    columns = list(dict.fromkeys([*pipeline.scorer.feature_names, "PricingDecisionID", "DecisionTime", "ProductID", "StoreID", "CostPrice"]))
    for split in ("validation", "test"):
        context = pd.read_parquet(ROOT / f"artifacts/phase8/{split}_factual_backtest.parquet", columns=columns)
        require(len(context) == 5250, "Replay row count mismatch")
        baseline = pd.read_parquet(ROOT / f"artifacts/phase6/{split}_recommendations.parquet").set_index("PricingDecisionID")
        outputs = []
        for offset in range(0, len(context), 500):
            scored = pipeline.score(request(context.iloc[offset:offset + 500]))
            outputs.extend(scored["model_recommendations"])
            print(f"{split}: {min(offset + 500, len(context))}/5250", flush=True)
        actual = pd.DataFrame(outputs).set_index("PricingDecisionID").loc[baseline.index]
        prices = int(actual.ModelOptimalCandidatePrice.ne(baseline.ModelOptimalCandidatePrice).sum())
        deltas = {key: float(np.max(np.abs(actual[key].to_numpy(float) - baseline[key].to_numpy(float))))
                  for key in ("recommended_expected_units", "recommended_expected_revenue", "recommended_expected_gross_profit")}
        require(prices == 0 and max(deltas.values()) <= 1e-8, "Frozen optimizer replay mismatch")
        result["splits"][split] = {"rows": len(actual), "exact_price_mismatches": prices,
                                    "max_absolute_deltas": deltas, "economic_tolerance": 1e-8}
    input_example = example(pipeline)
    first = pipeline.predict(input_example)
    second = pipeline.predict(pd.concat([input_example, input_example], ignore_index=True))
    require(first.response_json.iloc[0] == second.response_json.iloc[0] == second.response_json.iloc[1], "Adapter parity")
    result.update({"batch_interactive_identical": True, "seconds": time.perf_counter() - started,
                   "business_replay": "PENDING_ORIGINAL_IMMUTABLE_RULE_PROMOTION_INVENTORY_PROJECTIONS",
                   "registry_roundtrip": "NOT_RUN", "champion_promoted": False,
                   "phase_complete": False})
    return result


def save_package(saved):
    import mlflow
    from mlflow.models import ModelSignature
    from mlflow.types import Schema, ColSpec
    signature = ModelSignature(Schema([ColSpec("string", "request_json")]),
                               Schema([ColSpec("string", "response_json")]))
    input_example = example()
    with tempfile.TemporaryDirectory(dir=ROOT / "build") as folder:
        temporary = Path(folder)
        bundle = inference_bundle(temporary / "inference")
        # Copy only source files, never local caches, datasets, or credentials.
        code = temporary / "code/src"
        for p in (ROOT / "src").rglob("*.py"):
            target = code / p.relative_to(ROOT / "src")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(p.read_bytes().replace(b"\r\n", b"\n"))
        dependencies = [line.strip() for line in (ROOT / "requirements-runtime.lock").read_text().splitlines()
                        if line.strip() and not line.startswith("#")]
        dependencies += ["mlflow-skinny==3.16.0", "pyodbc==5.3.0"]
        mlflow.pyfunc.save_model(path=str(saved), python_model=str(ROOT / "azure_databricks/scripts/phase3_model.py"),
            artifacts={"inference_release": str(bundle)}, code_paths=[str(p) for p in sorted(code.iterdir())],
            signature=signature, input_example=input_example, pip_requirements=dependencies,
            metadata={"release_contract": VERSION, "dataset_embedded": False, "advisory_only": True})
    return input_example


def validate_package():
    expected = PricingPipeline(ROOT).predict(example()).response_json.iloc[0]
    with tempfile.TemporaryDirectory(dir=ROOT / "build") as folder:
        temporary = Path(folder)
        saved = temporary / "model"
        input_example = save_package(saved)
        sample = temporary / "input.json"
        sample.write_text(input_example.to_json(orient="records"))
        child = """import sys,time,json,hashlib,psutil,pandas as pd,mlflow
t=time.perf_counter(); model=mlflow.pyfunc.load_model(sys.argv[1]); startup=time.perf_counter()-t
frame=pd.DataFrame(json.load(open(sys.argv[2]))); result=model.predict(frame).response_json.iloc[0]
print(json.dumps({'sha256':hashlib.sha256(result.encode()).hexdigest(),'startup_seconds':startup,'rss_bytes':psutil.Process().memory_info().rss}))
"""
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        outcome = subprocess.run([sys.executable, "-c", child, str(saved), str(sample)],
            cwd=temporary, env=env, capture_output=True, text=True, timeout=90)
        require(outcome.returncode == 0, "Clean-process MLflow load failed: " + outcome.stderr[-1500:])
        measurement = json.loads(outcome.stdout.strip().splitlines()[-1])
        require(measurement["sha256"] == digest(expected.encode()), "MLflow roundtrip parity failed")
        require(measurement["rss_bytes"] < 1_500_000_000 and measurement["startup_seconds"] < 60, "Runtime envelope failed")
        return {"status": "PASS", "clean_process_roundtrip_identical": True, "runtime": measurement,
                "dataset_embedded": False, "registry_roundtrip": "NOT_RUN", "cloud_compute_started": False}


def validate_business(snapshot):
    snapshot = Path(snapshot).resolve()
    require(snapshot.is_relative_to((ROOT / "build").resolve()) or snapshot == (ROOT / "artifacts/azure_databricks/phase3/policy").resolve(), "Unrecognized policy capture path")
    manifest = json.loads((snapshot / "manifest.json").read_text())
    require(manifest["schema_version"] == "pricing.policy_snapshot.v1", "Snapshot schema mismatch")
    sources = {}
    for name in ("rules", "promotions", "inventory"):
        entry = next(x for x in manifest["files"] if x["path"] == name + ".parquet")
        path = snapshot / entry["path"]
        require(digest(path.read_bytes()) == entry["sha256"], "Policy capture hash mismatch")
        sources[name] = pd.read_parquet(path)
        require(len(sources[name]) == entry["rows"], "Policy capture count mismatch")
    pipeline = PricingPipeline(ROOT)
    columns = list(dict.fromkeys([*pipeline.scorer.feature_names, "PricingDecisionID", "DecisionTime", "ProductID", "StoreID", "CostPrice"]))
    results = {}
    for split in ("validation", "test", "current_inventory"):
        context = pd.read_parquet(ROOT / f"artifacts/phase8/{'test' if split == 'current_inventory' else split}_factual_backtest.parquet", columns=columns)
        current = split == "current_inventory"
        if current:
            context = context.sort_values(["ProductID", "StoreID", "Channel", "DecisionTime", "PricingDecisionID"], kind="mergesort").drop_duplicates(["ProductID", "StoreID", "Channel"], keep="last")
            age = (sources["inventory"].SnapshotDate.max().normalize() - pd.to_datetime(context.DecisionTime).dt.normalize()).dt.days
            context = context.loc[age.between(0, 30)]
        baseline = pd.read_parquet(ROOT / f"artifacts/phase7/{split}_business_decisions.parquet").set_index("PricingDecisionID").sort_index()
        require(len(context) == (1829 if current else 5250), "Business replay context count mismatch")
        outputs = []
        for offset in range(0, len(context), 500):
            chunk = context.iloc[offset:offset + 500]
            # Select only relevant product/store inventory to keep requests bounded.
            inventory = sources["inventory"]
            pairs = pd.MultiIndex.from_frame(chunk[["ProductID", "StoreID"]].drop_duplicates())
            inventory = inventory.loc[pd.MultiIndex.from_frame(inventory[["ProductID", "StoreID"]]).isin(pairs)] if current else inventory.iloc[:0]
            payload = request(chunk, rules=clean(sources["rules"].to_dict("records")),
                promotions=clean(sources["promotions"].to_dict("records")), inventory=clean(inventory.to_dict("records")),
                mode="CURRENT_INVENTORY_MODE" if current else "HISTORICAL_POLICY_MODE")
            outputs.extend(pipeline.score(payload)["decisions"])
            print(f"business {split}: {min(offset + 500, len(context))}/{len(context)}", flush=True)
        actual = pd.DataFrame(outputs).set_index("PricingDecisionID").sort_index()
        require(actual.index.equals(baseline.index), "Business replay identity mismatch")
        mismatches = {}
        for col in baseline.columns:
            require(col in actual, "Business output missing: " + col)
            a, b = actual[col], baseline[col]
            if pd.api.types.is_numeric_dtype(b) and not pd.api.types.is_bool_dtype(b):
                same = np.isclose(pd.to_numeric(a).to_numpy(float), b.to_numpy(float), atol=0 if "Price" in col else 1e-8, rtol=0, equal_nan=True)
            else:
                same = np.array([clean(x) == clean(y) for x, y in zip(a, b)])
            if not same.all():
                mismatches[col] = int((~same).sum())
        results[split] = {"rows": len(actual), "compared_columns": len(baseline.columns), "mismatches": mismatches}
        require(not mismatches, "Business replay mismatch: " + json.dumps(mismatches))
    return {"status": "PASS", "splits": results, "policy_capture": manifest, "capture_equivalence_verified": True,
            "economic_tolerance": 1e-8, "price_tolerance": 0, "cloud_compute_started": False,
            "registry_roundtrip": "NOT_RUN", "champion_promoted": False, "phase_complete": False}


def seal_policy(snapshot):
    snapshot = Path(snapshot).resolve()
    evidence = json.loads((ROOT / "azure_databricks/evidence/phase_03/business_replay.json").read_text())
    manifest = json.loads((snapshot / "manifest.json").read_text())
    require(evidence["status"] == "PASS" and evidence["policy_capture"] == manifest, "Capture has not passed full replay")
    destination = ROOT / "artifacts/azure_databricks/phase3/policy"
    destination.mkdir(parents=True, exist_ok=True)
    for item in manifest["files"]:
        require(item["path"] in {"rules.parquet", "promotions.parquet", "inventory.parquet"}, "Unsafe policy path")
        data = (snapshot / item["path"]).read_bytes()
        require(digest(data) == item["sha256"], "Policy capture changed")
        target = destination / item["path"]
        require(not target.exists() or target.read_bytes() == data, "Sealed policy collision")
        if not target.exists():
            target.write_bytes(data)
    seal = {**manifest, "replay_verified": True, "acceptance_sha256": digest(packed(evidence)),
            "source_release": plan()["source_release"]}
    target = destination / "manifest.json"
    require(not target.exists() or target.read_bytes() == packed(seal), "Policy manifest collision")
    if not target.exists():
        target.write_bytes(packed(seal))
    return seal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["plan", "validate-local", "validate-package", "validate-business", "seal-policy"])
    parser.add_argument("--policy-snapshot", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.action in {"validate-business", "seal-policy"}:
        require(args.policy_snapshot is not None, "Policy snapshot required")
        result = validate_business(args.policy_snapshot) if args.action == "validate-business" else seal_policy(args.policy_snapshot)
    else:
        result = plan() if args.action == "plan" else validate_local() if args.action == "validate-local" else validate_package()
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_bytes(packed(result))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
