"""
sql_common.py
-------------
Shared pieces for the metric modules.

Every metric function takes a filter as a (sql_fragment, params) pair — exactly what
filters.build_where() returns in Phase 5 — and returns (sql, params) with DuckDB named
parameters ($name). The fragment uses bare column names that exist in the view it is applied to.
"""
from __future__ import annotations

Where = tuple[str, dict]
ALL: Where = ("TRUE", {})
MIN_N = 5            # small-n suppression threshold for survey segments (Hard rule 4)
LOW_RESPONSE_PCT = 50  # segments below this response rate get low_response = true (UI badge "Low response, read with caution")
AS_OF = "2026-10-31"
FY_MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]


def merge(*parts: dict) -> dict:
    """Merge param dicts; the same name must carry the same value."""
    out: dict = {}
    for p in parts:
        for k, v in p.items():
            if k in out and out[k] != v:
                raise ValueError(f"parameter clash: {k}")
            out[k] = v
    return out


def ident(name: str, allowed: dict | list | set) -> str:
    """Whitelist a column / dimension name before it is put into SQL text."""
    if name not in allowed:
        raise ValueError(f"not allowed: {name!r}")
    return name
