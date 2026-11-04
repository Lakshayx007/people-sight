"""
db.py
-----
One read-only DuckDB connection for the process; one cursor per request.
Results come back as JSON-safe lists of dicts (NaN/NaT -> None, dates -> ISO strings, numpy -> Python).
"""
from __future__ import annotations

import json
import math
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "people.duckdb"
_con: duckdb.DuckDBPyConnection | None = None


def connect(path: Path = DB_PATH) -> None:
    global _con
    if _con is None:
        if not path.exists():
            raise FileNotFoundError(f"{path} not found — run the pipeline (pipeline/02..04) first")
        _con = duckdb.connect(str(path), read_only=True)


def close() -> None:
    global _con
    if _con is not None:
        _con.close()
        _con = None


@contextmanager
def cursor():
    if _con is None:
        connect()
    cur = _con.cursor()
    try:
        yield cur
    finally:
        cur.close()


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()[:10] if isinstance(v, datetime) and v.time() == datetime.min.time() else v.isoformat()
    if hasattr(v, "item"):          # numpy scalar
        return _clean(v.item())
    return v


def query(sql: str, params: dict | None = None) -> list[dict]:
    with cursor() as cur:
        cur.execute(sql, params or {})
        cols = [d[0] for d in cur.description]
        return [{c: _clean(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def scalar(sql: str, params: dict | None = None):
    with cursor() as cur:
        return _clean(cur.execute(sql, params or {}).fetchone()[0])


def annotate(sql: str, params: dict) -> str:
    """Prefix the SQL with its parameter values as a comment, so the text shown in 'Show SQL' is exactly what ran."""
    head = f"-- params: {json.dumps(params, default=str)}\n" if params else ""
    return head + sql.strip()


def query_rows(sql: str, params: dict | None = None) -> list[tuple]:
    """Plain tuples (for internal lookups such as the Ask-the-Data schema)."""
    with cursor() as cur:
        return cur.execute(sql, params or {}).fetchall()
