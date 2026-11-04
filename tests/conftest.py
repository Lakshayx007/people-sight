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


@pytest.fixture(scope="session")
def rec(enps):  # depends on enps so employees.parquet exists first
    _ensure("03_clean_recruitment.py", ["requisitions.parquet", "candidates.parquet", "recruiters.parquet", "people_directory.parquet"])
    return {
        "req": pd.read_parquet(CLEAN / "requisitions.parquet"),
        "cand": pd.read_parquet(CLEAN / "candidates.parquet"),
        "excl": pd.read_parquet(CLEAN / "candidates_excluded.parquet"),
        "rc": pd.read_parquet(CLEAN / "recruiters.parquet"),
        "pdir": pd.read_parquet(CLEAN / "people_directory.parquet"),
        "dq": pd.read_csv(CLEAN / "dq_log.csv"),
        "recon": pd.read_csv(CLEAN / "reconciliation.csv"),
    }


@pytest.fixture(scope="session")
def db(rec):
    import duckdb
    if not (ROOT / "data" / "people.duckdb").exists():
        subprocess.run([sys.executable, str(ROOT / "pipeline" / "04_build_db.py")], check=True)
    sys.path.insert(0, str(ROOT))
    con = duckdb.connect(str(ROOT / "data" / "people.duckdb"), read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="session")
def q(db):
    def run(fn, *a, **k):
        sql, params = fn(*a, **k)
        return db.execute(sql, params).df()
    return run
