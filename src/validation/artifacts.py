from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    raise TypeError(type(value).__name__)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prediction_fingerprint(frame: pd.DataFrame) -> str:
    ordered = frame.sort_values([column for column in ["DecisionTime", "PricingDecisionID"] if column in frame], kind="mergesort")
    digest = hashlib.sha256()
    digest.update(json.dumps(list(ordered.columns), separators=(",", ":")).encode())
    for row in ordered.itertuples(index=False, name=None):
        digest.update(json.dumps(list(row), default=json_default, separators=(",", ":")).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def model_fingerprint(path: Path) -> str:
    return sha256_file(path)
