# Dynamic Pricing — Phase 1

This repository implements the read-only data audit, ML contract, and leakage analysis for Phase 1. It does not train a model or write to SQL Server.

Create the ignored `.env` file with `SQL_SERVER_DATABASE`, `SQL_SERVER_USER_NAME`, and `SQL_SERVER_PASSWORD`. The local default SQL Server instance is configured as `localhost`. Then run:

```powershell
$env:PYTHONPATH = "src"
python -m audit.validation_runner
```

The audit adds the installed ODBC Driver 18 name when the configuration omits it and normalizes boolean ODBC options. Credentials are never printed or written to artifacts.

The validation runner executes pytest first, writes machine-derived test evidence bound to the current source-tree hash, and only then runs the live read-only audit. Running the audit with missing or stale test evidence produces a blocked result.
