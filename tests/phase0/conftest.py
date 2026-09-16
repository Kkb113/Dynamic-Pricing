from pathlib import Path

import pytest

from app_services.artifact_registry import ArtifactRegistry


@pytest.fixture(scope="session")
def registry() -> ArtifactRegistry:
    root = Path(__file__).resolve().parents[2]
    instance = ArtifactRegistry(root)
    instance.validate_integrity(raise_on_error=True)
    return instance
