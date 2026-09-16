"""Governed MLflow registration and identity load; no compute startup or endpoint."""
from __future__ import annotations
import argparse
import json
import os
import tempfile
import time
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from phase1 import ROOT, CONFIG_PATH, Cloud, audit, packed, digest, require, RemoteFiles, write_once, workload
from phase3 import plan, save_package, example, PricingPipeline


@contextmanager
def authentication(client, host):
    values = {"DATABRICKS_HOST": host, "DATABRICKS_CONFIG_FILE": os.devnull,
              "MLFLOW_TRACKING_URI": "databricks", "MLFLOW_REGISTRY_URI": "databricks-uc",
              "MLFLOW_USE_DATABRICKS_SDK_MODEL_ARTIFACTS_REPO_FOR_UC": "True"}
    if client.config.token:
        values.update(DATABRICKS_TOKEN=client.config.token, DATABRICKS_AUTH_TYPE="pat")
    else:
        values.update(DATABRICKS_CLIENT_ID=client.config.client_id,
                      DATABRICKS_CLIENT_SECRET=client.config.client_secret, DATABRICKS_AUTH_TYPE="oauth-m2m")
    keys = set(values) | {"DATABRICKS_TOKEN", "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET", "DATABRICKS_AUTH_TYPE"}
    previous = {key: os.environ.get(key) for key in keys}
    for key in keys:
        os.environ.pop(key, None)
    os.environ.update(values)
    try:
        yield
    finally:
        for key in keys:
            os.environ.pop(key, None)
            if previous[key] is not None:
                os.environ[key] = previous[key]


def acceptance():
    local = json.loads((ROOT / "azure_databricks/evidence/phase_03/local_replay.json").read_text())
    business = json.loads((ROOT / "azure_databricks/evidence/phase_03/business_replay.json").read_text())
    package = json.loads((ROOT / "azure_databricks/evidence/phase_03/package_roundtrip.json").read_text())
    require(local["status"] == business["status"] == package["status"] == "PASS", "Local acceptance incomplete")
    require(all(not x["mismatches"] for x in business["splits"].values()), "Business parity incomplete")
    linux = json.loads((ROOT / "azure_databricks/evidence/phase_03/linux_ci.json").read_text())
    require(linux["conclusion"] == "success", "Linux CI must pass before registration")
    policy = ROOT / "artifacts/azure_databricks/phase3/policy"
    manifest = json.loads((policy / "manifest.json").read_text())
    require(manifest["replay_verified"] and manifest["acceptance_sha256"] == digest(packed(business)), "Policy acceptance drift")
    for item in manifest["files"]:
        require(item["path"] in {"rules.parquet", "promotions.parquet", "inventory.parquet"}, "Unsafe policy path")
        require(digest((policy / item["path"]).read_bytes()) == item["sha256"], "Sealed policy drift")
    return policy, manifest


def isolated_load(client, host, uri, sample):
    with tempfile.TemporaryDirectory(dir=ROOT / "build") as folder:
        path = Path(folder) / "input.json"
        path.write_text(sample.to_json(orient="records"))
        child = """import sys,json,hashlib,pandas as pd,mlflow
from databricks.sdk import WorkspaceClient
mlflow.set_registry_uri('databricks-uc')
actor=WorkspaceClient().current_user.me().id
model=mlflow.pyfunc.load_model(sys.argv[1])
result=model.predict(pd.DataFrame(json.load(open(sys.argv[2])))).response_json.iloc[0]
print(json.dumps({'actor':str(actor),'sha256':hashlib.sha256(result.encode()).hexdigest()}))
"""
        with authentication(client, host):
            result = subprocess.run([sys.executable, "-c", child, uri, str(path)],
                cwd=folder, capture_output=True, text=True, timeout=180)
        if result.returncode:
            return {"denied": "PERMISSION_DENIED" in result.stderr or "403" in result.stderr,
                    "load_failed": True}
        return json.loads(result.stdout.strip().splitlines()[-1])


def apply(output):
    import mlflow
    from mlflow import MlflowClient
    from databricks.sdk.errors import NotFound, PermissionDenied
    from databricks.sdk.service.catalog import PermissionsChange, Privilege
    policy, manifest = acceptance()
    spec = plan()
    cfg = json.loads(CONFIG_PATH.read_text())
    cloud = Cloud(cfg)
    before = audit(cloud)
    require(before["app_state"] == "STOPPED" and not before["clusters"] and
            all(x["state"] == "STOPPED" for x in before["warehouses"]), "Unexpected active compute")
    ledger = ROOT / "build/phase3-registration.json"
    require(not ledger.exists(), "Registration already attempted; inspect existing release instead of duplicating it")
    seal = digest(packed({"model": spec, "policy": manifest}))
    root = "/Volumes/" + cfg["catalog"] + "/" + cfg["volumes"]["runtime"].replace(".", "/") + "/phase3/" + seal
    store = RemoteFiles(cloud.client)
    for item in manifest["files"]:
        write_once(store, root + "/policy/" + item["path"], (policy / item["path"]).read_bytes())
    write_once(store, root + "/policy/manifest.json", packed(manifest))
    result = {"status": "FAILED", "release_seal": seal, "policy_root": root + "/policy",
              "compute_started": False, "dedicated_endpoint_created": False, "model_name": spec["model_name"]}
    try:
        with authentication(cloud.client, cfg["host"]):
            mlflow.set_tracking_uri("databricks")
            mlflow.set_registry_uri("databricks-uc")
            mlflow.set_experiment(spec["experiment"])
            client = MlflowClient()
            existing = list(client.search_model_versions("name='" + spec["model_name"] + "'"))
            require(not existing, "First-release command refuses to replace existing model versions")
            with tempfile.TemporaryDirectory(dir=ROOT / "build") as folder:
                saved = Path(folder) / "model"
                sample = save_package(saved)
                with mlflow.start_run(run_name="phase3-frozen-pricing-" + seal[:12]) as run:
                    mlflow.set_tags({"pricing.release_seal": seal, "pricing.source_release": spec["source_release"],
                        "pricing.advisory_only": "true", "pricing.policy_manifest": digest(packed(manifest)),
                        "pricing.no_retraining": "true", "pricing.data_embedded": "false"})
                    mlflow.log_artifacts(str(saved), "pricing")
                    for evidence in ("local_replay.json", "business_replay.json", "package_roundtrip.json", "linux_ci.json"):
                        mlflow.log_artifact(str(ROOT / "azure_databricks/evidence/phase_03" / evidence), "acceptance")
                    mlflow.log_dict(spec, "acceptance/release_manifest.json")
                    version = mlflow.register_model("runs:/" + run.info.run_id + "/pricing", spec["model_name"])
                    result.update(run_id=run.info.run_id, model_version=str(version.version))
                    ledger.write_bytes(packed(result))
            uri = "models:/" + spec["model_name"] + "/" + str(version.version)
            expected = PricingPipeline(ROOT).predict(sample).response_json.iloc[0]
            require(mlflow.pyfunc.load_model(uri).predict(sample).response_json.iloc[0] == expected, "Registered model parity failed")
            result["operator_registered_load_identical"] = True
        cloud.client.registered_models.update(spec["model_name"], comment="Frozen advisory pricing; accepted synthetic snapshots; no automatic writeback.")
        cloud.client.grants.update("function", spec["model_name"], changes=[
            PermissionsChange(principal=cfg["app_application_id"], add=[Privilege.EXECUTE])])
        principals = {p.application_id: p for p in cloud.client.service_principals.list()}
        checks = {}
        with workload(cloud.client, principals[cfg["app_application_id"]], cfg["host"]) as runtime:
            actual = isolated_load(runtime, cfg["host"], uri, sample)
            checks["app_registered_load_identical"] = actual.get("sha256") == digest(expected.encode())
            checks["authenticated_as_actual_app"] = actual.get("actor") == str(principals[cfg["app_application_id"]].id)
            checks["app_policy_read_identical"] = RemoteFiles(runtime).read(root + "/policy/manifest.json") == packed(manifest)
            effective = cloud.client.grants.get_effective("function", spec["model_name"], principal=cfg["app_application_id"])
            rights = {p.privilege.value for a in effective.privilege_assignments or [] for p in a.privileges or []}
            checks["app_model_no_write"] = not rights.intersection({"OWN", "MANAGE", "ALL_PRIVILEGES"})
        with workload(cloud.client, principals[cfg["negative_test_application_id"]], cfg["host"]) as negative:
            denied = isolated_load(negative, cfg["host"], uri, sample)
            checks["lower_privilege_registered_load_denied"] = denied.get("denied", False)
            try:
                negative.registered_models.get(spec["model_name"])
                # Metadata discoverability is not equivalent to model execution permission.
            except PermissionDenied:
                pass
            try:
                RemoteFiles(negative).read(root + "/policy/manifest.json")
                checks["lower_privilege_policy_denied"] = False
            except PermissionDenied:
                checks["lower_privilege_policy_denied"] = True
        require(all(checks.values()), "Runtime identity acceptance failed")
        result["identity_checks"] = checks
        cloud.client.registered_models.set_alias(spec["model_name"], "Champion", int(version.version))
        aliases = cloud.client.registered_models.get(spec["model_name"], include_aliases=True).aliases or []
        require(any(x.alias_name == "Champion" and x.version_num == int(version.version) for x in aliases), "Alias readback failed")
        # First-release rollback withholds availability; no duplicate model version is needed.
        cloud.client.registered_models.delete_alias(spec["model_name"], "Champion")
        aliases = cloud.client.registered_models.get(spec["model_name"], include_aliases=True).aliases or []
        require(not any(x.alias_name == "Champion" for x in aliases), "First-release rollback failed")
        cloud.client.registered_models.set_alias(spec["model_name"], "Champion", int(version.version))
        result["first_release_rollback_tested"] = True
        result.update(status="PASS", champion_promoted=True, first_release_rollback="DELETE_CHAMPION_ALIAS_TO_WITHHOLD_UNVALIDATED_AVAILABILITY",
                      credentials_revoked=True)
        cloud.client.registered_models.update(spec["model_name"], owner=cfg["owner_group"])
    finally:
        if result["status"] != "PASS" and result.get("model_version"):
            aliases = cloud.client.registered_models.get(spec["model_name"], include_aliases=True).aliases or []
            if any(x.alias_name == "Champion" for x in aliases):
                cloud.client.registered_models.delete_alias(spec["model_name"], "Champion")
        # This command never starts compute; do not mutate unrelated resources.
        after = audit(cloud)
        result["final_compute_stopped"] = after["app_state"] == "STOPPED" and not after["clusters"] and all(x["state"] == "STOPPED" for x in after["warehouses"])
        result["retail_unchanged"] = all(before[k] == after[k] for k in ("catalog_grants", "retail_schema_grants", "app_configuration_sha256", "azure_resources"))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(packed(result))
    require(result["final_compute_stopped"] and result["retail_unchanged"], "Final safety acceptance failed")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.output), indent=2))
