import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
CLEAN = ROOT / "data" / "clean"


def _ensure(script: str, outputs: list[str]):
    if not all((CLEAN / o).exists() for o in outputs):
        subprocess.run([sys.executable, str(ROOT / "pipeline" / script)], check=True)


@pytest.fixture(scope="session")
def enps():
    _ensure("02_clean_enps.py", ["employees.parquet", "survey_responses.parquet", "pay_bands.parquet"])
    return {
        "emp": pd.read_parquet(CLEAN / "employees.parquet"),
        "resp": pd.read_parquet(CLEAN / "survey_responses.parquet"),
        "bands": pd.read_parquet(CLEAN / "pay_bands.parquet"),
        "dq": pd.read_csv(CLEAN / "dq_log.csv"),
        "recon": pd.read_csv(CLEAN / "reconciliation.csv"),
    }
