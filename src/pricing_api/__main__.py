"""Run the loopback-only FastAPI app with ``python -m pricing_api``."""

from __future__ import annotations

import uvicorn

from .config import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run("pricing_api.app:app", host=settings.host, port=settings.port, reload=False, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    main()
