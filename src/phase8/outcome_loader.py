"""Read-only, split-scoped Phase 8 outcome loading.

The loader makes the TEST outcome boundary auditable: VALIDATION and TEST are
separate SELECT-only reads, and the TEST query is issued only after the runner
has persisted and hashed the frozen evaluation specification.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from audit.database_profile import (
    assert_read_only_sql,
    connect_read_only,
    connection_string_from_settings,
    load_env_file,
)


OUTCOME_COLUMNS = (
    "PricingDecisionID",
    "PurchasedFlag",
    "QuantityPurchased",
    "ActualRevenue",
    "OutcomeTime",
    "AppliedPrice",
)

_DECISION_ID = re.compile(r"^PDL[A-Za-z0-9_\-]+$")


def validate_decision_ids(ids: Iterable[Any]) -> list[str]:
    """Normalize and validate IDs before placing them in a SQL IN clause."""

    normalized = sorted({str(value) for value in ids if value is not None})
    invalid = [value for value in normalized if not _DECISION_ID.fullmatch(value)]
    if invalid:
        raise ValueError(f"INVALID_PRICING_DECISION_IDS: {invalid[:3]}")
    return normalized


def outcome_select_sql(ids: Iterable[Any]) -> str:
    """Build a SELECT-only chunk query from validated generated decision IDs."""

    values = validate_decision_ids(ids)
    if not values:
        raise ValueError("OUTCOME_QUERY_REQUIRES_IDS")
    literals = ", ".join("'" + value.replace("'", "''") + "'" for value in values)
    columns = ", ".join(f"[{column}]" for column in OUTCOME_COLUMNS)
    sql = (
        f"SELECT {columns} FROM [dbo].[Pricing_Decision_Log] "
        f"WHERE [PricingDecisionID] IN ({literals})"
    )
    assert_read_only_sql(sql)
    return sql


def _settings(env_file: Path, server: str = "localhost") -> dict[str, Any]:
    return {
        "env_file": env_file.name,
        "server": server,
        "database_key": "SQL_SERVER_DATABASE",
        "username_key": "SQL_SERVER_USER_NAME",
        "password_key": "SQL_SERVER_PASSWORD",
        "odbc_driver": "ODBC Driver 18 for SQL Server",
    }


def _pymssql_rows(sql: str, env_file: Path, server: str) -> list[dict[str, Any]]:
    import pymssql  # type: ignore

    values = load_env_file(env_file)
    connection = pymssql.connect(
        server=server,
        user=values["SQL_SERVER_USER_NAME"],
        password=values["SQL_SERVER_PASSWORD"],
        database=values["SQL_SERVER_DATABASE"],
        login_timeout=30,
        timeout=60,
        tds_version="7.4",
    )
    try:
        assert_read_only_sql(sql)
        cursor = connection.cursor(as_dict=True)
        cursor.execute(sql)
        return list(cursor.fetchall())
    finally:
        connection.close()


def load_split_outcomes(
    decision_ids: Iterable[Any],
    *,
    env_file: Path,
    chunk_size: int = 1000,
    server: str = "localhost",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load exactly the requested decision IDs using read-only SQL.

    A connection is opened per split.  This makes the validation and TEST
    reads independently auditable and prevents accidental all-row outcome
    reads before the TEST freeze.
    """

    ids = validate_decision_ids(decision_ids)
    if not ids:
        return pd.DataFrame(columns=list(OUTCOME_COLUMNS)), {
            "status": "EMPTY",
            "rows": 0,
            "query_count": 0,
            "chunk_size": chunk_size,
            "sql_select_only": True,
        }
    rows: list[dict[str, Any]] = []
    queries: list[str] = []
    settings = _settings(env_file, server)
    try:
        raw = connection_string_from_settings(settings, env_file.parent)
        with connect_read_only(None, settings["odbc_driver"], 30, raw_connection=raw) as db:
            for start in range(0, len(ids), chunk_size):
                sql = outcome_select_sql(ids[start : start + chunk_size])
                queries.append(sql)
                rows.extend(db.rows(sql))
        driver = "odbc"
    except Exception as odbc_exc:
        rows = []
        queries = []
        try:
            for start in range(0, len(ids), chunk_size):
                sql = outcome_select_sql(ids[start : start + chunk_size])
                queries.append(sql)
                rows.extend(_pymssql_rows(sql, env_file, server))
            driver = "pymssql_tds"
        except Exception as fallback_exc:
            raise RuntimeError(
                f"OUTCOME_SQL_READ_FAILED: {type(fallback_exc).__name__}: "
                f"{str(fallback_exc).splitlines()[0][:240]}"
            ) from odbc_exc
    frame = pd.DataFrame(rows, columns=list(OUTCOME_COLUMNS))
    return frame, {
        "status": "CONNECTED_READ_ONLY",
        "rows": int(len(frame)),
        "requested_ids": int(len(ids)),
        "query_count": len(queries),
        "chunk_size": chunk_size,
        "driver": driver,
        "sql_select_only": True,
        "query_shapes": [
            {"row_count": sql.count("'") // 2, "has_outcome_columns": True}
            for sql in queries
        ],
    }


def fixture_outcomes(context: pd.DataFrame) -> pd.DataFrame:
    """Create deterministic, explicitly fixture-only outcomes for CI tests."""

    result = context[["PricingDecisionID", "AppliedPrice", "DecisionTime"]].copy()
    result["PurchasedFlag"] = (pd.to_numeric(result["AppliedPrice"], errors="coerce") % 3 < 1).astype(int)
    result["QuantityPurchased"] = result["PurchasedFlag"].astype(int)
    result["ActualRevenue"] = pd.to_numeric(result["AppliedPrice"], errors="coerce") * result["QuantityPurchased"]
    result["OutcomeTime"] = result["DecisionTime"]
    return result[list(OUTCOME_COLUMNS)]


__all__ = [
    "OUTCOME_COLUMNS",
    "fixture_outcomes",
    "load_split_outcomes",
    "outcome_select_sql",
    "validate_decision_ids",
]
