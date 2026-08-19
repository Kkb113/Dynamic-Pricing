from pathlib import Path

from app_services.artifact_registry import ArtifactIntegrityError, ArtifactRegistry


def test_all_required_artifacts_found_and_hashes_match(registry: ArtifactRegistry):
    result = registry.validate_integrity()
    assert result["status"] == "PASS", result
    assert result["major_blockers"] == []


def test_wrong_hash_rejected(registry: ArtifactRegistry):
    broken = ArtifactRegistry(registry.root)
    broken._expected_hashes = lambda: {broken.paths.phase7_manifest: "wrong"}  # type: ignore[method-assign]
    result = broken.validate_integrity()
    assert result["status"] == "BLOCKED"
    assert result["hash_mismatches"]


def test_missing_manifest_is_blocked(tmp_path: Path):
    result = ArtifactRegistry(tmp_path).validate_integrity()
    assert result["status"] == "BLOCKED"
    assert "artifacts/phase8/phase8_manifest.json" in result["missing"]
