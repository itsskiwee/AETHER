from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS = REPO_ROOT / "configs"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def base_config_path() -> Path:
    return CONFIGS / "base.yaml"


@pytest.fixture(scope="session")
def demo_config_path() -> Path:
    return CONFIGS / "demo.yaml"


@pytest.fixture(scope="session")
def scenarios_dir() -> Path:
    return CONFIGS / "scenarios"
