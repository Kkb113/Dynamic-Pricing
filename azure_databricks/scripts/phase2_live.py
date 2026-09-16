"""Deploy Phase 2 to existing SQL only; explicit one-window cost approval required."""
from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import requests
from databricks.sdk.errors import NotFound
from databricks.sdk.service.catalog import PermissionsChange, Privilege

from phase1 import (ROOT, CONFIG_PATH, Cloud, audit, digest, packed, require,
                    make_plan, verify_published, RemoteFiles, workload, write_once)
from phase2 import build_plan, identifier, BUSINESS_COLUMNS, MONEY_COLUMNS, compatible_parquet

WAREHOUSE = "77cfc492a3539c60"
CATALOG = "intellify_databricks_demo"
MARKER = "Dynamic pricing Phase 2 governed frozen lakehouse"


def automation(cloud, method, suffix, body=None):
    token = cloud.az_json(["account", "get-access-token", "--resource", "https://management.azure.com/"])["accessToken"]
    url = ("https://management.azure.com/subscriptions/" + cloud.config["subscription_id"] +
           "/resourceGroups/Databricks/providers/Microsoft.Automation/automationAccounts/retail-hp-poc-shutdown" +
           suffix + "?api-version=2024-10-23")
    r = requests.request(method, url, json=body, headers={"Authorization": "Bearer " + token}, timeout=30)
    require(200 <= r.status_code < 300, "Shutdown controller HTTP " + str(r.status_code))
    return r.json() if r.content else {}


def arm(cloud, deadline):
    job = str(uuid.uuid4())
    automation(cloud, "PUT", "/jobs/" + job, {"properties": {
        "runbook": {"name": "retail-hp-stop-demo"}, "parameters": {"DeadlineUnix": str(deadline)}}})
    for _ in range(24):
        state = automation(cloud, "GET", "/jobs/" + job)["properties"]["status"]
        require(state not in {"Failed", "Stopped", "Suspended"}, "Shutdown controller failed")
        streams = automation(cloud, "GET", "/jobs/" + job + "/streams")
        if any(x["properties"].get("summary") == "CONTROLLER_ARMED" for x in streams.get("value", [])):
            return job
        time.sleep(5)
    raise RuntimeError("No armed controller; compute must remain stopped")


class SQL:
    def __init__(self, client, deadline):
        self.client, self.deadline, self.count = client, deadline, 0

    def run(self, statement):
        require(time.time() < self.deadline - 120, "Validation window nearly expired")
        print("SQL operation", self.count + 1, flush=True)
        self.count += 1
        result = self.client.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE, statement=statement, wait_timeout="50s")
        started = time.monotonic()
        while result.status.state.value in {"PENDING", "RUNNING"}:
            if time.monotonic() - started > 120 or time.time() >= self.deadline - 60:
                self.client.statement_execution.cancel_execution(result.statement_id)
                raise RuntimeError("SQL cancelled at deadline")
            time.sleep(2)
            result = self.client.statement_execution.get_statement(result.statement_id)
        require(result.status.state.value == "SUCCEEDED", "SQL failed: " + str(result.status.error))
        require(not result.manifest or not result.manifest.truncated, "Truncated reconciliation")
        return result.result.data_array if result.result else []


def schema(client, sql, name, owner):
    full = CATALOG + "." + name
    try:
        existing = client.schemas.get(full)
        require(existing.comment == MARKER and existing.owner == owner, "Unrecognized pricing schema")
    except NotFound:
        client.schemas.create(name=name, catalog_name=CATALOG, comment=MARKER)
        client.schemas.update(full, owner=owner)
    # Disable inherited automatic paid maintenance before any table is created.
    sql.run("ALTER SCHEMA " + full + " DISABLE PREDICTIVE OPTIMIZATION")
    grants = client.grants.get("schema", full)
    for assignment in grants.privilege_assignments or []:
        require(assignment.principal in {owner, "retail_hp_engineers", "retail_hp_viewers",
                    "6972ee85-f9e7-455b-9f93-74e1b0d9a99e"} and
                all(p.value == "USE_SCHEMA" for p in assignment.privileges or []), "Unexpected pricing schema grants")


def materialize(client, sql, name, query, seal, owner):
    """Write-once publication; reruns compare complete multisets, never overwrite."""
    try:
        existing = client.tables.get(name)
        require(existing.comment == MARKER and existing.owner == owner and
                existing.properties.get("pricing.contract_seal") == seal,
                "Existing table belongs to a different contract: " + name)
    except NotFound:
        sql.run("CREATE TABLE " + name + " USING DELTA COMMENT '" + MARKER +
                "' TBLPROPERTIES ('pricing.contract_seal'='" + seal +
                "', 'delta.appendOnly'='true') AS " + query)
        sql.run("ALTER TABLE " + name + " OWNER TO " + identifier(owner))
    expected = "SELECT * FROM (" + query + ") AS expected_rows"
    diff = sql.run("SELECT count(*) FROM ((SELECT * FROM " + name + " EXCEPT ALL " + expected +
                   ") UNION ALL (" + expected + " EXCEPT ALL SELECT * FROM " + name + "))")
    require(int(diff[0][0]) == 0, "Published table content mismatch: " + name)
    return int(sql.run("SELECT count(*) FROM " + name)[0][0])


def grant_select(client, full_name, principals):
    for principal in principals:
        client.grants.update("schema", ".".join(full_name.split(".")[:2]), changes=[
            PermissionsChange(principal=principal, add=[Privilege.USE_SCHEMA])])
        client.grants.update("table", full_name, changes=[
            PermissionsChange(principal=principal, add=[Privilege.SELECT])])


def object_snapshot(client):
    objects = {}
    for name in ("pricing_silver", "pricing_gold"):
        try:
            objects.update({t.full_name: t.table_id for t in client.tables.list(CATALOG, name)})
        except NotFound:
            pass  # Expected on the first deployment, before schema creation.
    return objects


def deploy(cloud, sql, plan):
    client, cfg = cloud.client, cloud.config
    seal = digest(packed({"plan": plan, "deployment_contract": "pricing.lakehouse.deploy.v1"}))
    owner = cfg["owner_group"]
    for name in ("pricing_silver", "pricing_gold"):
        schema(client, sql, name, owner)
    counts, tables = {}, {}
    for item in plan["tables"]:
        counts[item["name"]] = materialize(client, sql, item["table"], item["query"], seal, owner)
        require(counts[item["name"]] == item["rows"], "Remote row-count mismatch")
        tables[item["name"]] = item["table"]
    suffix = plan["manifest_sha256"][:12]
    for name, source, columns in (
        ("cost_policy_context", "inventory_decisions", ["PricingDecisionID", "ProductID", "StoreID", "Channel",
          "CostPrice", "PricingRuleID", "RuleName", "effective_price_floor", "effective_price_ceiling",
          "InventorySnapshotDate", "AvailableQty", "DecisionTime"]),):
        full = CATALOG + ".pricing_silver." + name + "_" + suffix
        query = "SELECT " + ", ".join(identifier(c) for c in columns) + " FROM " + tables[source]
        counts[name] = materialize(client, sql, full, query, seal, owner)
        tables[name] = full
    lineage = CATALOG + ".pricing_silver.source_lineage_" + suffix
    lineage_query = " UNION ALL ".join("SELECT '" + item["name"] + "' AS dataset, '" +
        item["source"] + "' AS source_path, '" + item["source_sha256"] + "' AS source_sha256, " +
        str(item["rows"]) + " AS expected_rows, '" + plan["release_id"] + "' AS release_id"
        for item in plan["tables"])
    counts["lineage"] = materialize(client, sql, lineage, lineage_query, seal, owner)
    tables["lineage"] = lineage
    f = tables["features"]
    # Matching is on IDs plus category/brand, not names; ambiguity stays visible.
    products_query = f"""SELECT p.ProductID AS product_id,
      CASE WHEN r.product_id IS NOT NULL AND p.CategoryID = r.category_id AND p.BrandID = r.brand_id
        THEN r.product_name ELSE concat('Product ', p.ProductID) END AS product_name,
      p.CategoryID AS category_id, p.BrandID AS brand_id,
      CASE WHEN r.product_id IS NULL THEN 'UNMATCHED'
        WHEN p.CategoryID = r.category_id AND p.BrandID = r.brand_id THEN 'ID_AND_ATTRIBUTES_MATCH'
        ELSE 'ATTRIBUTE_CONFLICT' END AS mapping_status,
      r.source_hash AS retail_source_hash
      FROM (SELECT DISTINCT ProductID, CategoryID, BrandID FROM {f}) p
      LEFT JOIN {CATALOG}.silver.products r ON p.ProductID = r.product_id"""
    products = CATALOG + ".pricing_gold.product_context_" + suffix
    counts["product_context"] = materialize(client, sql, products, products_query, seal, owner)
    mapping = sql.run("SELECT mapping_status, count(*) FROM " + products + " GROUP BY mapping_status")
    require(int(sql.run("SELECT count(*) - count(DISTINCT product_id) FROM " + products)[0][0]) == 0,
            "Ambiguous product mapping")
    # Retail has store IDs in inventory, but no verified store-name dimension.
    stores = CATALOG + ".pricing_gold.store_context_" + suffix
    stores_query = f"""SELECT s.StoreID AS store_id, concat('Store ', s.StoreID) AS store_name,
       'IDENTIFIER_LABEL_ONLY' AS name_status,
       CASE WHEN r.store_id IS NULL THEN 'UNMATCHED' ELSE 'ID_PRESENT_IN_RETAIL_INVENTORY' END AS mapping_status
       FROM (SELECT DISTINCT StoreID FROM {f}) s
       LEFT JOIN (SELECT DISTINCT store_id FROM {CATALOG}.silver.inventory) r ON s.StoreID = r.store_id"""
    counts["store_context"] = materialize(client, sql, stores, stores_query, seal, owner)
    store_mapping = sql.run("SELECT mapping_status, count(*) FROM " + stores + " GROUP BY mapping_status")
    channel_mapping = sql.run(f"""SELECT p.Channel,
       CASE WHEN r.channel IS NULL THEN 'NOT_OBSERVED_IN_RETAIL_CUSTOMER_CHANNELS'
       ELSE 'EXACT_CHANNEL_MATCH' END AS mapping_status
       FROM (SELECT DISTINCT Channel FROM {f}) p
       LEFT JOIN (SELECT DISTINCT preferred_channel AS channel FROM {CATALOG}.silver.customers) r
         ON p.Channel=r.channel ORDER BY p.Channel""")
    public = [products, stores]
    business = []
    for scenario, table in (("validation", tables["validation_decisions"]), ("test", tables["test_decisions"]),
                            ("inventory", tables["inventory_decisions"])):
        cols = ["CAST(d." + identifier(c) + " AS DECIMAL(18,2)) AS " + identifier(c)
                if c in MONEY_COLUMNS else "d." + identifier(c) for c in BUSINESS_COLUMNS]
        business.append("SELECT " + ", ".join(cols) + ", '" + scenario + "' AS scenario, " +
            "p.product_name, s.store_name, 'UNVERIFIED_SOURCE_UNIT' AS currency_status, " +
            "CAST(NULL AS STRING) AS currency_code, 'MODELED_ADVISORY' AS result_kind, '" +
            plan["release_id"] + "' AS release_id, " +
            ", ".join("'" + v + "' AS " + k for k, v in plan["versions"].items()) +
            ", 'FROZEN_HISTORICAL_SNAPSHOT' AS freshness_status FROM " + table + " d LEFT JOIN " + products +
            " p ON d.ProductID=p.product_id LEFT JOIN " + stores + " s ON d.StoreID=s.store_id")
    curated = CATALOG + ".pricing_gold.business_decisions_" + suffix
    counts["business_decisions"] = materialize(client, sql, curated, " UNION ALL ".join(business), seal, owner)
    require(counts["business_decisions"] == 12329, "Curated join changed row count")
    public.append(curated)
    summary = CATALOG + ".pricing_gold.action_summary_" + suffix
    query = ("SELECT scenario, FinalAction AS action, count(*) AS decision_count, " +
             "sum(CASE WHEN manual_review_flag THEN 1 ELSE 0 END) AS review_count, " +
             "min(DecisionTime) AS first_decision_at, max(DecisionTime) AS last_decision_at, " +
             "currency_status, result_kind, release_id FROM " + curated +
             " GROUP BY scenario, FinalAction, currency_status, result_kind, release_id")
    counts["action_summary"] = materialize(client, sql, summary, query, seal, owner)
    public.append(summary)
    views = []
    for source in (curated, summary):
        view = source + "_view"
        query = "SELECT * FROM " + source
        try:
            existing = client.tables.get(view)
            require(existing.comment == MARKER and existing.owner == owner and
                    existing.view_definition.strip() == query, "View definition drift")
        except NotFound:
            sql.run("CREATE VIEW " + view + " COMMENT '" + MARKER + "' AS " + query)
            sql.run("ALTER VIEW " + view + " OWNER TO " + identifier(owner))
        views.append(view)
    public.extend(views)
    # Grants are last: incomplete/raw tables never become business-readable.
    for name in tables.values():
        grant_select(client, name, [cfg["preparation_group"]])
    for name in public:
        grant_select(client, name, [cfg["preparation_group"], cfg["app_application_id"], "retail_hp_viewers"])
    # Verify effective (including inherited) access before reporting publication.
    rights_report = {}
    for name in list(tables.values()) + public:
        rights = client.grants.get_effective("table", name, principal=cfg["app_application_id"])
        require(not rights.next_page_token, "Paginated privileges require explicit review")
        values = {p.privilege.value for a in rights.privilege_assignments or [] for p in a.privileges or []}
        require(not values.intersection({"MODIFY", "ALL_PRIVILEGES", "MANAGE", "OWN"}), "App has write access")
        require(("SELECT" in values) == (name in public), "App data isolation failed")
        rights_report[name] = sorted(values)
    principals = {p.application_id: p for p in client.service_principals.list()}
    with workload(client, principals[cfg["app_application_id"]], cfg["host"]) as app:
        app_sql = SQL(app, sql.deadline)
        require(int(app_sql.run("SELECT count(*) FROM " + curated)[0][0]) == 12329, "App curated read failed")
        try:
            app_sql.run("SELECT count(*) FROM " + tables["features"])
        except RuntimeError as exc:
            require("PERMISSION_DENIED" in str(exc) or "INSUFFICIENT_PERMISSIONS" in str(exc),
                    "Restricted-read test failed for an unrelated reason")
        else:
            raise RuntimeError("App unexpectedly read restricted features")
    return {"counts": counts, "product_mapping": mapping, "store_mapping": store_mapping,
            "channel_mapping": channel_mapping, "contract_seal": seal,
            "app_identity_checks": "CURATED_READ_PASS_RESTRICTED_READ_DENIED", "app_effective_rights": rights_report,
            "restricted_tables": list(tables.values()), "business_tables": public,
            "combined_tools_enabled": False, "store_names": "Identifiers only; no verified source names",
            "status": "DEPLOYED_RECONCILED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-inr", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-window", action="store_true")
    args = parser.parse_args()
    require(args.approved_inr == 250, "Requires explicit approved INR 250 window")
    ledger = ROOT / "build/phase2-window.json"
    require(not ledger.exists() or args.resume_window, "Validation allowance already used; do not silently open another window")
    plan = build_plan()
    cfg = json.loads(CONFIG_PATH.read_text())
    cloud = Cloud(cfg)
    before = audit(cloud)
    require(before["app_state"] == "STOPPED" and not before["clusters"], "Unrelated compute active")
    w = cloud.client.warehouses.get(WAREHOUSE)
    require(w.state.value == "STOPPED" and w.cluster_size == "2X-Small" and w.max_num_clusters == 1
            and w.auto_stop_mins == 1, "Warehouse contract changed")
    release = make_plan(ROOT, cfg)
    if args.resume_window:
        lease = json.loads(ledger.read_text())
        deadline, stop_job = lease["deadline_unix"], lease["stop_job"]
        require(lease["approved_inr"] == 250 and time.time() < deadline - 300, "Original window expired")
        require(automation(cloud, "GET", "/jobs/" + stop_job)["properties"]["status"] == "Running",
                "Original shutdown controller not running")
    else:
        verify_published(RemoteFiles(cloud.client), release)
        deadline = int(time.time()) + 1800
        stop_job = arm(cloud, deadline)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_bytes(packed({"approved_inr": 250, "deadline_unix": deadline, "stop_job": stop_job}))
    store = RemoteFiles(cloud.client)
    for item in plan["tables"]:
        content, _ = compatible_parquet(ROOT / item["original_path"])
        require(digest(content) == item["compatibility_sha256"], "Compatibility content drift")
        write_once(store, item["source"], content)
    result = {"status": "FAILED", "deadline_unix": deadline, "stop_job": stop_job}
    objects_before = object_snapshot(cloud.client)
    try:
        cloud.client.warehouses.start(WAREHOUSE)
        sql = SQL(cloud.client, deadline)
        result.update(deploy(cloud, sql, plan))
        result["sql_operations"] = sql.count
        objects_after = object_snapshot(cloud.client)
        result["objects_created"] = len(objects_after.keys() - objects_before.keys())
        result["existing_object_ids_unchanged"] = all(objects_after.get(k) == v for k, v in objects_before.items())
        require(result["existing_object_ids_unchanged"], "Existing objects were replaced")
    finally:
        cloud.client.warehouses.stop(WAREHOUSE)
        cloud.client.warehouses.wait_get_warehouse_stopped(WAREHOUSE)
        result["warehouse_final_state"] = cloud.client.warehouses.get(WAREHOUSE).state.value
        result["timestamp_utc"] = datetime.now(UTC).isoformat()
        after = audit(cloud)
        result["app_final_state"] = after["app_state"]
        result["predictive_optimization"] = {s: cloud.client.schemas.get(CATALOG + "." + s)
            .effective_predictive_optimization_flag.value.value for s in ("pricing_silver", "pricing_gold")}
        result["retail_unchanged"] = all(before[k] == after[k] for k in
            ("catalog_grants", "retail_schema_grants", "app_configuration_sha256", "azure_resources"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(packed(result))
    require(result["retail_unchanged"], "Unexpected retail change")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
