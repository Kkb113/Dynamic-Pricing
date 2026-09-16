"""Pricing governance and write-once transfer; no compute or SQL execution.

Run from the repository root with Python 3.12 and databricks-sdk==0.81.0.
Authentication uses the operator's Azure CLI session. Secrets never reach disk.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from dynamic_pricing.release import verify_release_manifest

MARKER = "Dynamic pricing migration Phase 1; governed immutable release"
CONFIG_PATH = ROOT / "azure_databricks/config/phase1.json"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def packed(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(relative):
    require(isinstance(relative, str) and bool(relative), "Invalid release path")
    p = PurePosixPath(relative)
    require(not p.is_absolute() and p.as_posix() == relative and
            not any(x in {".", "..", ""} or x.startswith(".") for x in relative.split("/")) and
            not any(x in relative for x in ("\\", ":", "\x00")), "Unsafe release path")
    require(p.parts[0] in {"src", "config", "contracts", "artifacts", "frontend"} or
            relative in {"pyproject.toml", "requirements-runtime.lock", "requirements-test.lock"},
            "Path outside release allowlist")
    return p


def local_bytes(root, item):
    p = safe_path(item["path"])
    source = (root / str(p)).resolve()
    require(source.is_relative_to(root.resolve()), "Release symlink escapes root")
    data = source.read_bytes()
    if item["hash_mode"] == "canonical_utf8_lf":
        data = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode()
    require(len(data) == item["bytes"] and digest(data) == item["sha256"],
            "Local release content mismatch: " + str(p))
    return data


def make_plan(root, config):
    require(config["host"] == "https://adb-7405618180989330.10.azuredatabricks.net" and
            config["catalog"] == "intellify_databricks_demo" and
            config["volumes"] == {"restricted": "pricing_bronze.release_inputs", "runtime": "pricing_ml.release_runtime"} and
            config["compute_start_allowed"] is False, "Unapproved target or compute policy")
    manifest = json.loads((root / config["manifest"]).read_text(encoding="utf-8"))
    require(verify_release_manifest(root, manifest)["status"] == "PASS", "Phase 0 seal failed")
    require(manifest["source_commit"] == config["sealed_source_commit"], "Unexpected sealed source")
    require(digest(packed(manifest)) == config["sealed_manifest_sha256"], "Unapproved manifest revision")
    require(manifest["total_bytes"] == sum(f["bytes"] for f in manifest["files"]) and
            manifest["total_bytes"] <= config["maximum_release_bytes"], "Release size gate failed")
    entries = []
    for item in manifest["files"]:
        safe_path(item["path"])
        # Row-level datasets remain inaccessible to the App principal.
        partition = "restricted" if item["path"].endswith(".parquet") else "runtime"
        entries.append({**item, "partition": partition})
    release_id = "pricing-" + manifest["source_commit"][:12] + "-" + digest(packed(manifest))[:16]
    return {"schema_version": "pricing.transfer.v1", "release_id": release_id,
            "phase0_manifest_sha256": digest(packed(manifest)),
            "source_commit": manifest["source_commit"], "accepted_merge_commit": config["accepted_merge_commit"],
            "total_bytes": manifest["total_bytes"], "file_count": len(entries), "files": entries,
            "roots": {k: "/Volumes/" + config["catalog"] + "/" + v.replace(".", "/") + "/" + release_id
                      for k, v in config["volumes"].items()},
            "compute_started": False, "source_manifest": manifest}


class Cloud:
    def __init__(self, config):
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.core import Config
        self.config = config
        self.az = shutil.which("az") or shutil.which("az.cmd")
        require(self.az, "Azure CLI required")
        account = self.az_json(["account", "show"])
        require(account["id"] == config["subscription_id"] and account["state"] == "Enabled", "Subscription scope mismatch")
        self.workspace = self.az_json(["resource", "show", "--subscription", config["subscription_id"],
            "--resource-group", config["resource_group"], "--name", config["workspace_name"],
            "--resource-type", "Microsoft.Databricks/workspaces"])
        p = self.workspace["properties"]
        require("https://" + p["workspaceUrl"] == config["host"] and str(p["workspaceId"]) == config["workspace_id"] and
                self.workspace["location"] == config["region"], "Workspace scope mismatch")
        token = self.az_json(["account", "get-access-token", "--subscription", config["subscription_id"],
                             "--resource", "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"])["accessToken"]
        self.client = WorkspaceClient(config=Config(host=config["host"], token=token, auth_type="pat",
            config_file=os.devnull, http_timeout_seconds=30, retry_timeout_seconds=30))

    def az_json(self, args):
        result = subprocess.run([self.az, *args, "--output", "json", "--only-show-errors"],
                                capture_output=True, text=True, timeout=90)
        require(result.returncode == 0, "Azure CLI request failed; credentials/output suppressed")
        return json.loads(result.stdout)


def audit(cloud):
    c, cfg = cloud.client, cloud.config
    catalog = c.catalogs.get(cfg["catalog"])
    app = c.apps.get(cfg["app"])
    require(app.service_principal_client_id == cfg["app_application_id"], "App identity changed")
    principals = list(c.service_principals.list())
    negative = [p for p in principals if p.display_name == cfg["negative_test_principal"] and
                p.application_id == cfg["negative_test_application_id"]]
    require(len(negative) == 1 and negative[0].active, "Negative-test identity unavailable")
    group_names = {g.display_name for g in c.groups.list()}
    require({cfg["owner_group"], cfg["preparation_group"]}.issubset(group_names), "Operator role groups missing")
    # Snapshot existing retail ACLs and app configuration to detect accidental changes.
    retail = {}
    for s in c.schemas.list(cfg["catalog"]):
        if not s.name.startswith("pricing_") and s.name != "information_schema":
            retail[s.full_name] = c.grants.get("schema", s.full_name).as_dict()
    resources = cloud.az_json(["resource", "list", "--subscription", cfg["subscription_id"],
                              "--resource-group", cfg["resource_group"]])
    automation = [r for r in resources if r["type"].lower() == "microsoft.automation/automationaccounts"]
    shutdown = []
    for r in automation:
        for kind in ("runbooks", "schedules"):
            data = cloud.az_json(["rest", "--method", "GET", "--url",
                "https://management.azure.com" + r["id"] + "/" + kind + "?api-version=2023-11-01"])
            shutdown.append({"account": r["name"], "kind": kind, "items": [
                {"name": x["name"], "state": x["properties"].get("state"),
                 "enabled": x["properties"].get("isEnabled"), "expiry": x["properties"].get("expiryTime")}
                for x in data.get("value", [])]})
    return {"workspace": cfg["workspace_name"], "catalog_owner": catalog.owner,
            "catalog_grants": c.grants.get("catalog", cfg["catalog"]).as_dict(),
            "retail_schema_grants": retail,
            "app_configuration_sha256": digest(packed({"resources": [r.as_dict() for r in app.resources or []],
                                                       "deployment": app.active_deployment.as_dict() if app.active_deployment else None})),
            "app_state": app.compute_status.state.value,
            "warehouses": [{"name": w.name, "state": w.state.value, "auto_stop_mins": w.auto_stop_mins,
                "size": w.cluster_size, "max_clusters": w.max_num_clusters} for w in c.warehouses.list()],
            "azure_resources": sorted([{"name": r["name"], "type": r["type"]} for r in resources], key=lambda x:x["name"]),
            "shutdown": shutdown, "compute_started": False}


def grant_matrix(cfg):
    owner, prep, app = cfg["owner_group"], cfg["preparation_group"], cfg["app_application_id"]
    matrix = {}
    for partition, name in cfg["volumes"].items():
        schema = cfg["catalog"] + "." + name.split(".")[0]
        volume = cfg["catalog"] + "." + name
        readers = [prep] + ([app] if partition == "runtime" else [])
        matrix[("schema", schema)] = {owner: {"USE_SCHEMA", "CREATE_VOLUME"}, **{p: {"USE_SCHEMA"} for p in readers}}
        matrix[("volume", volume)] = {owner: {"READ_VOLUME", "WRITE_VOLUME"}, **{p: {"READ_VOLUME"} for p in readers}}
    return matrix


def governance(c, cfg, apply=False):
    from databricks.sdk.errors import NotFound
    from databricks.sdk.service.catalog import PermissionsChange, Privilege, VolumeType
    changes = []
    # No catalog grant changes: all required identities already have USE CATALOG.
    actual_catalog = c.grants.get("catalog", cfg["catalog"])
    for a in actual_catalog.privilege_assignments or []:
        require(not any(p.value in {"READ_VOLUME", "WRITE_VOLUME", "ALL_PRIVILEGES"} for p in a.privileges or []),
                "Inherited catalog data grant requires review")
    for partition, name in cfg["volumes"].items():
        schema, volume = name.split(".")
        sf, vf = cfg["catalog"] + "." + schema, cfg["catalog"] + "." + name
        try:
            obj = c.schemas.get(sf)
        except NotFound:
            require(apply, "Missing pricing schema: " + sf)
            obj = c.schemas.create(schema, cfg["catalog"], comment=MARKER)
            changes.append("created:" + sf)
        require(obj.comment == MARKER, "Existing schema not owned by this deployment")
        try:
            obj = c.volumes.read(vf)
        except NotFound:
            require(apply, "Missing pricing volume: " + vf)
            obj = c.volumes.create(cfg["catalog"], schema, volume, VolumeType.MANAGED, comment=MARKER)
            changes.append("created:" + vf)
        require(obj.comment == MARKER and obj.volume_type == VolumeType.MANAGED, "Existing volume contract mismatch")
    for (kind, name), desired in grant_matrix(cfg).items():
        actual = {a.principal: {p.value for p in a.privileges or []} for a in c.grants.get(kind, name).privilege_assignments or []}
        require(all(p in desired and rights <= desired[p] for p, rights in actual.items()), "Unexpected pricing grants: " + name)
        for principal, rights in desired.items():
            missing = rights - actual.get(principal, set())
            if missing:
                require(apply, "Missing pricing privilege: " + name)
                c.grants.update(kind, name, changes=[PermissionsChange(principal=principal, add=[Privilege(x) for x in sorted(missing)])])
                changes.append("granted:" + name + ":" + principal)
        obj = c.schemas.get(name) if kind == "schema" else c.volumes.read(name)
        if obj.owner != cfg["owner_group"]:
            require(apply, "Pricing owner mismatch")
            if kind == "schema":
                c.schemas.update(name, owner=cfg["owner_group"])
            else:
                c.volumes.update(name, owner=cfg["owner_group"])
            changes.append("owner:" + name)
    return {"status": "PASS", "changes": changes}


class RemoteFiles:
    def __init__(self, client):
        self.client = client

    def read(self, path):
        from databricks.sdk.errors import NotFound
        try:
            response = self.client.files.download(path)
        except NotFound:
            return None
        with response.contents as stream:
            return stream.read()

    def create(self, path, data):
        self.client.files.create_directory(path.rsplit("/", 1)[0])
        self.client.files.upload(path, io.BytesIO(data), overwrite=False)


def write_once(store, path, content):
    existing = store.read(path)
    if existing is not None:
        require(existing == content, "Release ID content collision: " + path)
        return False
    # Concurrent identical writers are safe; never replace differing content.
    try:
        store.create(path, content)
    except Exception:
        if store.read(path) != content:
            raise
    require(store.read(path) == content, "Remote readback failed: " + path)
    return True


def reconcile(store, plan):
    def verify_item(item):
        path = plan["roots"][item["partition"]] + "/" + item["path"]
        data = store.read(path)
        if data is None or len(data) != item["bytes"] or digest(data) != item["sha256"]:
            return item["path"]
        return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        errors = [error for error in pool.map(verify_item, plan["files"]) if error]
    require(not errors, "Remote release missing/mismatched files: " + ", ".join(errors))
    return {"status": "PASS", "verified_files": len(plan["files"]), "verified_bytes": plan["total_bytes"]}


def release_pointer(plan):
    return {"schema_version": "pricing.verified.release.v1", "release_id": plan["release_id"],
            "manifest_sha256": plan["phase0_manifest_sha256"], "roots": plan["roots"],
            "files": plan["file_count"], "bytes": plan["total_bytes"]}


def verify_published(store, plan):
    result = reconcile(store, plan)
    for root in plan["roots"].values():
        require(store.read(root + "/_source_manifest.json") == packed(plan["source_manifest"]), "Remote manifest mismatch")
    require(store.read(plan["roots"]["runtime"] + "/_VERIFIED.json") == packed(release_pointer(plan)),
            "Verified release pointer missing/mismatched")
    return result


def transfer(store, root, plan):
    # Validate every local byte before creating anything remotely.
    contents = {i["path"]: local_bytes(root, i) for i in plan["files"]}
    if store.read(plan["roots"]["runtime"] + "/_VERIFIED.json") is not None:
        return {**verify_published(store, plan), "objects_created": 0, "pointer": release_pointer(plan)}
    manifest = packed(plan["source_manifest"])
    created = 0
    for partition in plan["roots"]:
        created += write_once(store, plan["roots"][partition] + "/_source_manifest.json", manifest)
    for item in plan["files"]:
        path = plan["roots"][item["partition"]] + "/" + item["path"]
        created += write_once(store, path, contents[item["path"]])
    result = reconcile(store, plan)
    pointer = release_pointer(plan)
    created += write_once(store, plan["roots"]["runtime"] + "/_VERIFIED.json", packed(pointer))
    return {**result, "objects_created": created, "pointer": pointer}


@contextmanager
def workload(operator, principal, host):
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.core import Config
    credential = operator.service_principal_secrets_proxy.create(str(principal.id), lifetime="3600s")
    try:
        require(credential.id and credential.secret, "Temporary identity credential unavailable")
        yield WorkspaceClient(config=Config(host=host, auth_type="oauth-m2m", client_id=principal.application_id,
              client_secret=credential.secret, config_file=os.devnull, http_timeout_seconds=30, retry_timeout_seconds=30))
    finally:
        operator.service_principal_secrets_proxy.delete(str(principal.id), str(credential.id))


def identity_test(c, cfg, plan):
    from databricks.sdk.errors import PermissionDenied
    principals = {p.application_id: p for p in c.service_principals.list()}
    runtime = principals[cfg["app_application_id"]]
    negative = principals[cfg["negative_test_application_id"]]
    require(runtime.id != negative.id, "Identity separation required")
    checks = {}
    restricted = next(i for i in plan["files"] if i["partition"] == "restricted")
    runtime_item = next(i for i in plan["files"] if i["path"].endswith("purchase_catboost.cbm"))
    restricted_path = plan["roots"]["restricted"] + "/" + restricted["path"]
    with workload(c, runtime, cfg["host"]) as client:
        files = RemoteFiles(client)
        data = files.read(plan["roots"]["runtime"] + "/" + runtime_item["path"])
        checks["actual_app_model_read"] = data is not None and digest(data) == runtime_item["sha256"]
        try:
            files.read(restricted_path)
            checks["app_restricted_input_denied"] = False
        except PermissionDenied:
            checks["app_restricted_input_denied"] = True
        # Inspect effective privileges, including those inherited through groups.
        effective = c.grants.get_effective("volume", cfg["catalog"] + "." + cfg["volumes"]["runtime"],
                                          principal=runtime.application_id)
        require(not effective.next_page_token, "Unexpected paginated identity privileges")
        rights = {p.privilege.value for a in effective.privilege_assignments or [] for p in a.privileges or []}
        checks["app_runtime_no_effective_write"] = "READ_VOLUME" in rights and not rights.intersection(
            {"WRITE_VOLUME", "ALL_PRIVILEGES", "MANAGE", "OWN"})
    with workload(c, negative, cfg["host"]) as client:
        try:
            RemoteFiles(client).read(restricted_path)
            checks["lower_privilege_restricted_read_denied"] = False
        except PermissionDenied:
            checks["lower_privilege_restricted_read_denied"] = True
    require(all(checks.values()), "Identity access acceptance failed")
    return {"status": "PASS", "checks": checks, "temporary_credentials_revoked": True,
            "compute_started": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "inspect", "apply", "verify", "identity-test"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cfg = json.loads(CONFIG_PATH.read_text())
    plan = make_plan(ROOT, cfg)
    if args.command == "plan":
        result = {k: v for k, v in plan.items() if k not in {"files", "source_manifest"}}
        result["partition_counts"] = {p: sum(i["partition"] == p for i in plan["files"]) for p in plan["roots"]}
    else:
        cloud = Cloud(cfg)
        before = audit(cloud)
        result = {"before": before}
        if args.command in {"apply", "verify"}:
            result["governance"] = governance(cloud.client, cfg, apply=args.command == "apply")
            store = RemoteFiles(cloud.client)
            result["transfer"] = transfer(store, ROOT, plan) if args.command == "apply" else verify_published(store, plan)
        elif args.command == "identity-test":
            governance(cloud.client, cfg)
            verify_published(RemoteFiles(cloud.client), plan)
            result["identity"] = identity_test(cloud.client, cfg, plan)
        after = audit(cloud) if args.command != "inspect" else before
        for key in ("catalog_grants", "retail_schema_grants", "app_configuration_sha256", "azure_resources", "shutdown"):
            require(before[key] == after[key], "Unrelated infrastructure drift: " + key)
        result["after"] = after
        result["unrelated_resources_unchanged"] = True
    result.update({"status": "PASS", "command": args.command, "timestamp_utc": datetime.now(UTC).isoformat(),
                   "release_id": plan["release_id"], "compute_started": False})
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(packed(result))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
