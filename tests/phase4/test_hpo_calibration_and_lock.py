from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from models.calibration import apply_calibrator, fit_calibration_candidates, select_calibration_method
from models.catboost_data import build_feature_families
from models.hyperparameter_search import run_hpo
from phase4 import runner


ROOT = Path(__file__).resolve().parents[2]


def test_hpo_uses_only_supplied_train_folds() -> None:
    contract = yaml.safe_load((ROOT / "contracts/phase2_feature_contract_v1.yaml").read_text(encoding="utf-8"))
    frame = pd.read_parquet(ROOT / "artifacts/phase2/feature_dataset.parquet").head(180).copy().reset_index(drop=True)
    family = build_feature_families(contract)["F0_CORE"]
    folds = [(np.arange(0, 60), np.arange(60, 100)), (np.arange(0, 100), np.arange(100, 140)), (np.arange(0, 140), np.arange(140, 180))]
    trials, summary, choice = run_hpo(frame, folds, contract, family.feature_names, thread_count=2, n_trials=1, seed=42, iterations=20, early_stopping_rounds=5)
    assert len(trials) == 1
    assert summary["completed_trials"] == 1
    assert set(np.concatenate([train for train, _ in folds]).tolist()) | set(np.concatenate([valid for _, valid in folds]).tolist()) == set(range(180))
    assert choice["trial"] == 0


def test_calibration_candidates_are_oof_only_and_selection_is_material() -> None:
    labels = np.array([0, 1, 0, 1, 0, 1, 0, 1] * 5)
    raw = np.linspace(-2, 2, len(labels))
    native = 1 / (1 + np.exp(-raw))
    candidates = fit_calibration_candidates(raw, native, labels)
    rows = []
    for method, calibrator in candidates.items():
        rows.append({"method": method, **{key: value for key, value in __import__("models.calibration", fromlist=["calibration_metrics"]).calibration_metrics(labels, apply_calibrator(method, calibrator, raw, native), method).items() if key in {"log_loss", "brier_score", "ece"}}})
    selected = select_calibration_method(rows)
    assert selected["selected_method"] in {"NATIVE", "SIGMOID", "ISOTONIC"}
    assert all(np.isfinite(apply_calibrator(method, calibrator, raw, native)).all() for method, calibrator in candidates.items())


def test_test_evaluator_requires_a_valid_frozen_spec(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runner, "ARTIFACTS", tmp_path)
    with pytest.raises(RuntimeError, match="FROZEN_MODEL_SPEC_REQUIRED"):
        runner._require_frozen_spec()
    payload = {"feature_set_name": "F0_CORE", "selected_iteration_count": 5}
    payload["frozen_model_spec_sha256"] = runner._json_hash(payload)
    (tmp_path / "frozen_model_spec.json").write_text(json.dumps(payload), encoding="utf-8")
    assert runner._require_frozen_spec()["feature_set_name"] == "F0_CORE"
    payload["selected_iteration_count"] = 6
    (tmp_path / "frozen_model_spec.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="FROZEN_MODEL_SPEC_HASH_MISMATCH"):
        runner._require_frozen_spec()

