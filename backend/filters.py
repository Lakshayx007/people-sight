"""
filters.py
----------
The ONE place where filter state becomes SQL (Hard rule 3).

build_where(filters, dataset) -> (sql_fragment, params)

  dataset "survey"        -> fragment for v_survey AND v_invited (identical column names)
  dataset "requisitions"  -> fragment for v_requisitions
  dataset "candidates"    -> fragment for v_candidates (carries the requisition's attributes + source)

Every filter is multi-select (a list of values; empty / missing = no filter) and always parameterised:
`list_contains($thread, thread)`. Column names come from the whitelists below, never from the request.
"""
from __future__ import annotations

import re
from typing import Any

# filter key -> column, per dashboard
ENPS_FILTERS = {
    "wave": "wave", "thread": "thread", "function": "function", "job_family": "job_family", "grade": "grade",
    "location": "location", "location_type": "location_type", "company": "company", "tenure_band": "tenure_band",
    "performance_rating": "performance_rating", "compa_band": "compa_band", "manager_status": "manager_status",
}
HIRING_FILTERS = {
    "thread": "thread", "function": "function", "grade": "grade", "location": "location", "recruiter": "recruiter",
    "source": "source", "position_type": "position_type", "criticality": "criticality", "req_status": "req_status",
}
HIRING_RANGE = {"raised_month_from": ">=", "raised_month_to": "<="}
DATASETS = {"survey": "enps", "requisitions": "hiring", "candidates": "hiring"}
MAX_VALUES = 200
_MONTH = re.compile(r"\d{4}-\d{2}")


class FilterError(ValueError):
    """Raised for unknown keys or malformed values (the API turns it into HTTP 400)."""


def allowed_keys(dashboard: str) -> set[str]:
    return set(ENPS_FILTERS) if dashboard == "enps" else set(HIRING_FILTERS) | set(HIRING_RANGE)


def normalise(filters: dict[str, Any] | None, dashboard: str) -> dict[str, Any]:
    """Validate and clean a filter dict: drop empties, reject unknown keys, coerce values to strings."""
    out: dict[str, Any] = {}
    for key, val in (filters or {}).items():
        if key not in allowed_keys(dashboard):
            raise FilterError(f"unknown filter '{key}' for {dashboard}")
        if val is None or val == "" or val == []:
            continue
        if key in HIRING_RANGE:
            if not isinstance(val, str) or not _MONTH.fullmatch(val):
                raise FilterError(f"{key} must be 'YYYY-MM'")
            out[key] = val
            continue
        vals = val if isinstance(val, list) else [val]
        if len(vals) > MAX_VALUES or not all(isinstance(v, (str, int, float, bool)) for v in vals):
            raise FilterError(f"{key} must be a list of up to {MAX_VALUES} values")
        out[key] = [str(v) for v in vals]
    return out


def build_where(filters: dict[str, Any] | None, dataset: str) -> tuple[str, dict]:
    """Return a parameterised WHERE fragment (no 'WHERE' keyword) and its params for one dataset."""
    if dataset not in DATASETS:
        raise FilterError(f"unknown dataset '{dataset}'")
    dash = DATASETS[dataset]
    f = normalise(filters, dash)
    clauses, params = [], {}
    cols = ENPS_FILTERS if dash == "enps" else HIRING_FILTERS
    for key, col in cols.items():
        if key not in f:
            continue
        pname = f"f_{key}"
        if dataset == "requisitions" and key == "source":
            # a requisition matches a source if it received at least one applicant from it
            clauses.append(f"req_id IN (SELECT req_id FROM v_candidates WHERE list_contains(${pname}, source))")
        else:
            clauses.append(f"list_contains(${pname}, {col})")
        params[pname] = f[key]
    if dash == "hiring":
        for key, op in HIRING_RANGE.items():
            if key in f:
                clauses.append(f"raised_month {op} $f_{key}")
                params[f"f_{key}"] = f[key]
    return (" AND ".join(clauses) if clauses else "TRUE"), params
