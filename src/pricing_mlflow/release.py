"""Canonical inference release bytes; trained model binaries are untouched."""
import hashlib
from pathlib import Path

INFERENCE_FILES = (
    "contracts/phase2_feature_contract_v1.yaml",
    "artifacts/phase4/models/purchase_catboost.cbm",
    "artifacts/phase4/frozen_model_spec.json",
    "artifacts/phase5/models/quantity_estimator_metadata.json",
    "artifacts/phase6/frozen_optimizer_spec.json",
    "artifacts/phase7/frozen_business_policy_spec.json",
)


def release_bytes(path):
    path = Path(path)
    data = path.read_bytes()
    return data.replace(b"\r\n", b"\n") if path.suffix in {".json", ".yaml"} else data


def fingerprint(root):
    digest = hashlib.sha256()
    for name in INFERENCE_FILES:
        digest.update(release_bytes(Path(root) / name))
    return digest.hexdigest()
