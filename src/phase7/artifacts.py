"""Small deterministic writers used by the Phase 7 runner."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from validation.artifacts import json_default, sha256_file, write_json


def write_frame(path: Path, frame: pd.DataFrame) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return sha256_file(path)


def write_phase7_json(path: Path, payload: Any) -> str:
    write_json(path, payload)
    return sha256_file(path)


def write_csv(path: Path, frame: pd.DataFrame) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return sha256_file(path)


def compute_environment() -> dict[str, Any]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "phase7_read_only_sql": True,
        "advisory_only": True,
        "auto_writeback": False,
    }


__all__ = ["compute_environment", "write_csv", "write_frame", "write_phase7_json"]
