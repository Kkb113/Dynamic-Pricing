"""Export only business policy projections from local SQL, never credentials.

The export stays in ignored build storage until independent replay verifies it.
It is a newly captured source snapshot, not falsely labelled the original export.
"""
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from phase1 import ROOT, packed, digest, require
from audit.database_profile import connection_string_from_settings, connect_read_only, load_env_file, assert_read_only_sql
from business_rules.rule_loader import load_pricing_rules
from promotions.promotion_loader import load_promotions
from inventory_policy.inventory_loader import load_inventory


def export(env_file, destination):
    destination = Path(destination).resolve()
    require(destination.is_relative_to((ROOT / "build").resolve()) and not destination.exists(), "Unsafe/nonempty snapshot destination")
    settings = {"env_file": str(Path(env_file).resolve()), "server": "localhost",
                "database_key": "SQL_SERVER_DATABASE", "username_key": "SQL_SERVER_USER_NAME",
                "password_key": "SQL_SERVER_PASSWORD"}
    try:
        raw = connection_string_from_settings(settings, ROOT)
        with connect_read_only(None, "ODBC Driver 18 for SQL Server", 15, raw_connection=raw) as db:
            sources = {"rules": load_pricing_rules(db), "promotions": load_promotions(db), "inventory": load_inventory(db)}
    except Exception as exc:
        try:
            import pymssql
            values = load_env_file(Path(env_file))
            connection = pymssql.connect(server="localhost", user=values["SQL_SERVER_USER_NAME"],
                password=values["SQL_SERVER_PASSWORD"], database=values["SQL_SERVER_DATABASE"],
                login_timeout=15, timeout=30, tds_version="7.4", autocommit=False)
            class ReadOnly:
                def rows(self, sql):
                    assert_read_only_sql(sql)
                    cursor = connection.cursor(as_dict=True)
                    cursor.execute(sql)
                    return list(cursor.fetchall())
            try:
                db = ReadOnly()
                sources = {"rules": load_pricing_rules(db), "promotions": load_promotions(db), "inventory": load_inventory(db)}
            finally:
                connection.rollback()
                connection.close()
        except Exception as fallback:
            raise RuntimeError("POLICY_SOURCE_UNAVAILABLE:" + type(fallback).__name__) from None
    require(all(not frame.empty for frame in sources.values()), "Empty business source snapshot")
    destination.mkdir(parents=True)
    files = []
    for name, frame in sources.items():
        path = destination / (name + ".parquet")
        frame.to_parquet(path, index=False)
        files.append({"path": path.name, "rows": len(frame), "sha256": digest(path.read_bytes())})
    manifest = {"schema_version": "pricing.policy_snapshot.v1", "captured_at": datetime.now(UTC).isoformat(),
                "source": "LOCAL_SQL_SELECT_ONLY", "original_export": False, "files": files,
                "replay_verified": False, "contains_customer_or_outcome_rows": False}
    (destination / "manifest.json").write_bytes(packed(manifest))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.env_file, args.destination), indent=2))
