import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def clean_dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A small seeded dataset with no injected anomalies (identity holds exactly)."""
    from arbiter_datagen.generate import generate_dataset

    out = tmp_path_factory.mktemp("clean")
    generate_dataset(scenario="d2c", records=60, seed=42, out_dir=out, difficulty="easy")
    return out


@pytest.fixture(scope="session")
def adversarial_dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A seeded dataset with the labeled adversarial anomaly catalog."""
    from arbiter_datagen.generate import generate_dataset

    out = tmp_path_factory.mktemp("adversarial")
    generate_dataset(scenario="d2c", records=200, seed=42, out_dir=out, difficulty="normal")
    return out


@pytest.fixture(scope="session")
def spec_path() -> Path:
    return REPO / "specs" / "razorpay-settlement.yaml"


@pytest.fixture
def cli():
    def _run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "arbiter_engine.cli", *args],
            capture_output=True,
            text=True,
            cwd=REPO,
        )

    return _run
