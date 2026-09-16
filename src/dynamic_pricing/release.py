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
    ".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache",
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
    if tree_status == "unavailable":
        blockers.append("SOURCE_GIT_UNAVAILABLE")
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
        "source_tree_clean": not dirty and tree_status != "unavailable",
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
    errors: list[str] = []
    entries = payload.get("files", [])
    if not isinstance(entries, list) or not entries:
        return {"status": "BLOCKED", "errors": ["EMPTY_OR_INVALID_INVENTORY"], "missing": [], "hash_mismatches": [], "verified_files": 0}
    if payload.get("schema_version") == "pricing.release.manifest.v1":
        if payload.get("status") != "PASS" or payload.get("source_tree_clean") is not True:
            errors.append("RELEASE_NOT_SEALED")
        if payload.get("file_count") != len(entries):
            errors.append("INVENTORY_COUNT_MISMATCH")
        declared = {item.get("path") for item in entries if isinstance(item, dict)}
        if not set(CRITICAL_RUNTIME_PATHS).issubset(declared):
            errors.append("INCOMPLETE_RUNTIME_INVENTORY")
    seen: set[str] = set()
    verified = 0
    for item in payload.get("files", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            errors.append("INVALID_ENTRY")
            continue
        relative = str(item["path"])
        path = root.resolve() / relative
        if (relative in seen or Path(relative).is_absolute() or ".." in Path(relative).parts
                or not path.resolve().is_relative_to(root.resolve()) or not _safe(path, root.resolve())):
            errors.append("UNSAFE_OR_DUPLICATE_PATH")
            continue
        seen.add(relative)
        if item.get("hash_mode", "raw_bytes") not in {"raw_bytes", "canonical_utf8_lf"}:
            errors.append("UNKNOWN_HASH_MODE")
            continue
        if not path.is_file():
            missing.append(relative)
            continue
        if item.get("hash_mode") == "canonical_utf8_lf":
            actual, size, _ = manifest_digest(path)
        else:
            actual = sha256_file(path)
            size = path.stat().st_size
        if actual != item.get("sha256"):
            mismatches.append({"path": relative, "expected": str(item.get("sha256")), "actual": actual})
        elif size != item.get("bytes"):
            errors.append("SIZE_MISMATCH:" + relative)
        else:
            verified += 1
    return {
        "status": "PASS" if not missing and not mismatches and not errors else "BLOCKED",
        "errors": errors,
        "missing": missing,
        "hash_mismatches": mismatches,
        "verified_files": verified,
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
