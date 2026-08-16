from __future__ import annotations

import hashlib
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import pyodbc

READ_ONLY_SQL = re.compile(r"^\s*(SELECT|WITH|DECLARE|SET\s+TRANSACTION\s+ISOLATION\s+LEVEL)\b", re.I)
FORBIDDEN_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER|CREATE|EXEC(?:UTE)?|GRANT|REVOKE|BACKUP|RESTORE|DBCC|BULK\s+INSERT|SHUTDOWN)\b", re.I)
SELECT_INTO_SQL = re.compile(r"\bSELECT\b[\s\S]*?\bINTO\b", re.I)


def assert_read_only_sql(sql: str) -> None:
    scrubbed = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    scrubbed = re.sub(r"'(?:''|[^'])*'", "''", scrubbed)
    if FORBIDDEN_SQL.search(scrubbed) or SELECT_INTO_SQL.search(scrubbed) or not READ_ONLY_SQL.search(scrubbed):
        raise ValueError("Phase 1 permits read-only SELECT/metadata statements only")


def normalize_odbc_connection(raw: str, driver: str) -> str:
    if not raw:
        raise RuntimeError("Missing SQL Server connection configuration; configure it without committing secrets")
    tokens: list[str] = []
    has_driver = False
    for token in raw.split(";"):
        if not token.strip() or "=" not in token:
            continue
        key, value = token.split("=", 1)
        key_l = key.strip().lower()
        has_driver |= key_l == "driver"
        if key_l in {"encrypt", "trustservercertificate"}:
            v = value.strip().lower()
            value = "yes" if v in {"true", "1", "yes"} else "no" if v in {"false", "0", "no"} else value
        tokens.append(f"{key}={value}")
    if not has_driver:
        tokens.insert(0, f"Driver={{{driver}}}")
    return ";".join(tokens)


def sanitized_server_identity(raw: str) -> str:
    match = re.search(r"(?i)(?:^|;)\s*server\s*=\s*([^;]+)", raw)
    value = match.group(1).strip() if match else "unknown"
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()[:12]


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise RuntimeError(f"Missing environment file: {path.name}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def connection_string_from_settings(settings: dict[str, Any], project_root: Path) -> str:
    values = load_env_file(project_root / settings["env_file"])
    required = [settings["database_key"], settings["username_key"], settings["password_key"]]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError("Missing required SQL configuration keys: " + ", ".join(missing))
    return ";".join([
        f"Server={settings.get('server', 'localhost')}",
        f"Database={values[settings['database_key']]}",
        f"UID={values[settings['username_key']]}",
        f"PWD={values[settings['password_key']]}",
        "Encrypt=no", "TrustServerCertificate=yes",
    ])


class ReadOnlyConnection:
    def __init__(self, connection: pyodbc.Connection):
        self.connection = connection

    def execute(self, sql: str, params: Iterable[Any] = ()):  # pyodbc cursor
        assert_read_only_sql(sql)
        return self.connection.cursor().execute(sql, *tuple(params))

    def rows(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        cur = self.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def row(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        values = self.rows(sql, params)
        return values[0] if values else None


@contextmanager
def connect_read_only(connection_env: str | None, driver: str, timeout: int = 15, *, raw_connection: str | None = None):
    raw = raw_connection if raw_connection is not None else os.environ.get(connection_env or "", "")
    conn_str = normalize_odbc_connection(raw, driver)
    conn = pyodbc.connect(conn_str, timeout=timeout, attrs_before={101: 1}, autocommit=False)
    wrapped = ReadOnlyConnection(conn)
    try:
        yield wrapped
    finally:
        conn.rollback()
        conn.close()


def database_profile(db: ReadOnlyConnection, schema: str = "dbo") -> dict[str, Any]:
    tables = db.rows("""
        SELECT t.TABLE_NAME AS table_name, COUNT(c.COLUMN_NAME) AS column_count
        FROM INFORMATION_SCHEMA.TABLES t
        JOIN INFORMATION_SCHEMA.COLUMNS c ON c.TABLE_SCHEMA=t.TABLE_SCHEMA AND c.TABLE_NAME=t.TABLE_NAME
        WHERE t.TABLE_SCHEMA=? AND t.TABLE_TYPE='BASE TABLE'
        GROUP BY t.TABLE_NAME ORDER BY t.TABLE_NAME
    """, [schema])
    for table in tables:
        name = table["table_name"].replace("]", "]]" )
        table["row_count"] = db.row(f"SELECT COUNT_BIG(*) AS n FROM [{schema}].[{name}]")["n"]
    return {"database": db.row("SELECT DB_NAME() AS database_name")["database_name"], "schema": schema,
            "table_count": len(tables), "column_count": sum(x["column_count"] for x in tables),
            "row_count": sum(x["row_count"] for x in tables), "tables": tables}


def schema_columns(db: ReadOnlyConnection, schema: str = "dbo") -> list[dict[str, Any]]:
    return db.rows("""
        SELECT TABLE_NAME AS source_table, COLUMN_NAME AS column_name, DATA_TYPE AS data_type,
               IS_NULLABLE AS is_nullable, ORDINAL_POSITION AS ordinal_position
        FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? ORDER BY TABLE_NAME, ORDINAL_POSITION
    """, [schema])
