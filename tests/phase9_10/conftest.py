from pathlib import Path

import pytest

from app_services.artifact_registry import ArtifactRegistry


@pytest.fixture(scope="session")
def root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def registry(root: Path) -> ArtifactRegistry:
    return ArtifactRegistry(root)
