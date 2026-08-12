import pytest

from audit.database_profile import (assert_read_only_sql, connection_string_from_settings,
                                    normalize_odbc_connection, sanitized_server_identity)


@pytest.mark.parametrize("sql", ["INSERT INTO x VALUES (1)", "UPDATE x SET a=1", "DELETE FROM x", "MERGE x USING y ON 1=1 WHEN MATCHED THEN UPDATE SET a=1", "DROP TABLE x", "CREATE TABLE x(a int)", "EXEC p"])
def test_mutating_sql_is_rejected(sql):
    with pytest.raises(ValueError): assert_read_only_sql(sql)


@pytest.mark.parametrize("sql", ["SELECT * FROM x", "WITH x AS (SELECT 1 a) SELECT * FROM x"])
def test_select_sql_is_allowed(sql):
    assert_read_only_sql(sql)


def test_connection_normalization_does_not_disclose_or_change_credentials():
    result = normalize_odbc_connection("Server=s;Database=d;User ID=u;Password=secret;Encrypt=True", "ODBC Driver 18 for SQL Server")
    assert "Password=secret" in result
    assert "Encrypt=yes" in result
    assert result.startswith("Driver={ODBC Driver 18 for SQL Server};")


def test_server_identity_is_hashed():
    result = sanitized_server_identity("Server=my-private-host;Database=d")
    assert result.startswith("sha256:") and "my-private-host" not in result


def test_discrete_dotenv_sql_settings_use_odbc_uid_pwd(tmp_path):
    (tmp_path / ".env").write_text("DB=db\nUSER=user\nPASS=secret\n", encoding="utf-8")
    settings={"env_file":".env","server":"localhost","database_key":"DB","username_key":"USER","password_key":"PASS"}
    result=connection_string_from_settings(settings,tmp_path)
    assert "Server=localhost" in result and "Database=db" in result
    assert "UID=user" in result and "PWD=secret" in result


def test_missing_dotenv_key_fails_actionably(tmp_path):
    (tmp_path / ".env").write_text("DB=db\n", encoding="utf-8")
    settings={"env_file":".env","server":"localhost","database_key":"DB","username_key":"USER","password_key":"PASS"}
    with pytest.raises(RuntimeError,match="Missing required SQL configuration keys"):
        connection_string_from_settings(settings,tmp_path)
