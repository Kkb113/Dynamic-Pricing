"""Build and validate the immutable Phase 0 transfer inventory."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


EXCLUDED_PARTS = frozenset({
    ".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
    ".phase2-run-tmp", ".phase4-runtime", ".test-tmp",
})
EXCLUDED_NAMES = frozenset({".env", ".env.local", ".env.production"})
CANONICAL_TEXT_SUFFIXES = frozenset({
    ".css", ".html", ".json", ".lock", ".md", ".py", ".toml", ".ts",
    ".tsx", ".txt", ".yaml", ".yml",
})

CRITICAL_RUNTIME_PATHS = (
    "contracts/phase2_feature_contract_v1.yaml",
    "contracts/pricing_runtime_contract_v1.yaml",
    "config/explanation_feature_labels.yaml",
    "artifacts/phase2/feature_dataset.parquet",
    "artifacts/phase3/split_assignments.parquet",
    "artifacts/phase4/models/purchase_catboost.cbm",
    "artifacts/phase4/frozen_model_spec.json",
    "artifacts/phase5/models/quantity_estimator_metadata.json",
    "artifacts/phase5/models/conditional_quantity_mean.json",
    "artifacts/phase5/frozen_quantity_spec.json",
    "artifacts/phase6/frozen_optimizer_spec.json",
    "artifacts/phase6/validation_candidate_surface.parquet",
    "artifacts/phase6/validation_recommendations.parquet",
    "artifacts/phase7/phase7_manifest.json",
    "artifacts/phase7/frozen_business_policy_spec.json",
    "artifacts/phase7/validation_business_decisions.parquet",
    "artifacts/phase7/test_business_decisions.parquet",
    "artifacts/phase7/current_inventory_business_decisions.parquet",
    "artifacts/phase8/phase8_manifest.json",
    "artifacts/phase8/frozen_evaluation_spec.json",
    "artifacts/phase8/validation_factual_backtest.parquet",
    "artifacts/phase8/test_factual_metrics.json",
    "artifacts/phase8/test_scenario_summary.json",
)


class ReleaseManifestError(RuntimeError):
    """The local tree cannot be sealed as a transfer release."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_bytes(path: Path) -> tuple[bytes, str]:
    """Return deterministic bytes and the hashing mode used by the manifest.

    Git may materialize text files with CRLF on Windows and LF on Linux. Release
    integrity therefore hashes UTF-8 text in canonical LF form while preserving
    exact bytes for model, Parquet, and other binary artifacts.
    """

    raw = path.read_bytes()
    if path.suffix.lower() not in CANONICAL_TEXT_SUFFIXES:
        return raw, "raw_bytes"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw, "raw_bytes"
    canonical = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return canonical, "canonical_utf8_lf"


def manifest_digest(path: Path) -> tuple[str, int, str]:
    content, mode = _manifest_bytes(path)
    return hashlib.sha256(content).hexdigest(), len(content), mode


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if result.returncode:
        return "unavailable"
    return result.stdout.strip()


def _safe(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return not any(part in EXCLUDED_PARTS for part in relative.parts) and path.name not in EXCLUDED_NAMES and not path.name.startswith(".env.")


def _iter_group(root: Path, directory: str, suffixes: tuple[str, ...]) -> Iterable[Path]:
    base = root / directory
    if not base.exists():
        return ()
    return (path for path in base.rglob("*") if path.is_file() and path.suffix in suffixes and _safe(path, root))


def transfer_paths(root: Path) -> list[Path]:
    """Return the allowlisted runtime/reproducibility dependency closure."""

    paths: set[Path] = {root / item for item in CRITICAL_RUNTIME_PATHS}
    for directory, suffixes in (
        ("src", (".py",)),
        ("config", (".yaml", ".yml", ".json")),
        ("contracts/application", (".json", ".yaml", ".md")),
        ("frontend/src", (".ts", ".tsx", ".css")),
        ("frontend", (".json", ".html", ".ts", ".yaml")),
    ):
        paths.update(_iter_group(root, directory, suffixes))
    for name in ("pyproject.toml", "requirements-runtime.lock", "requirements-test.lock"):
        paths.add(root / name)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


@dataclass(frozen=True)
class ReleaseManifest:
    payload: dict[str, Any]

    @property
    def status(self) -> str:
        return str(self.payload["status"])

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_release_manifest(root: Path, *, require_clean: bool = True) -> ReleaseManifest:
    root = root.resolve()
    candidates = transfer_paths(root)
    missing = [path.relative_to(root).as_posix() for path in candidates if not path.is_file()]
    unsafe = [path.relative_to(root).as_posix() for path in candidates if not _safe(path, root)]
    entries = []
    for path in candidates:
        if not path.is_file() or not _safe(path, root):
            continue
        digest, canonical_bytes, hash_mode = manifest_digest(path)
        entries.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": canonical_bytes,
            "sha256": digest,
            "hash_mode": hash_mode,
        })
    tree_status = _git(root, "status", "--porcelain", "--untracked-files=all")
    dirty = tree_status not in {"", "unavailable"}
    blockers = []
    if missing:
        blockers.append("MISSING_TRANSFER_DEPENDENCIES")
    if unsafe:
        blockers.append("UNSAFE_TRANSFER_PATH")
    if require_clean and dirty:
        blockers.append("SOURCE_TREE_NOT_CLEAN")
    payload = {
        "schema_version": "pricing.release.manifest.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "PASS" if not blockers else "BLOCKED",
        "release_mode": "HISTORICAL_SNAPSHOT_POC",
        "source_commit": _git(root, "rev-parse", "HEAD"),
        "source_branch": _git(root, "branch", "--show-current"),
        "source_tree_clean": not dirty,
        "currency_status": "UNVERIFIED_SOURCE_UNIT",
        "inventory_snapshot_date": "2025-12-31",
        "advisory_only": True,
        "missing": missing,
        "unsafe": unsafe,
        "blockers": blockers,
        "file_count": len(entries),
        "total_bytes": sum(item["bytes"] for item in entries),
        "files": entries,
        "excluded": sorted(EXCLUDED_PARTS | EXCLUDED_NAMES),
    }
    manifest = ReleaseManifest(payload)
    if blockers and require_clean:
        raise ReleaseManifestError(json.dumps(payload, sort_keys=True))
    return manifest


def verify_release_manifest(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    mismatches: list[dict[str, str]] = []
    missing: list[str] = []
    for item in payload.get("files", []):
        relative = str(item["path"])
        path = root.resolve() / relative
        if not path.is_file():
            missing.append(relative)
            continue
        if item.get("hash_mode") == "canonical_utf8_lf":
            actual, _, _ = manifest_digest(path)
        else:
            actual = sha256_file(path)
        if actual != item.get("sha256"):
            mismatches.append({"path": relative, "expected": str(item.get("sha256")), "actual": actual})
    return {
        "status": "PASS" if not missing and not mismatches else "BLOCKED",
        "missing": missing,
        "hash_mismatches": mismatches,
        "verified_files": len(payload.get("files", [])) - len(missing) - len(mismatches),
    }


__all__ = [
    "CRITICAL_RUNTIME_PATHS",
    "ReleaseManifest",
    "ReleaseManifestError",
    "build_release_manifest",
    "manifest_digest",
    "sha256_file",
    "transfer_paths",
    "verify_release_manifest",
]
