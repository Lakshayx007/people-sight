"""
common.py
---------
Shared constants and parsing helpers used by every pipeline script.
Pure functions only: nothing here reads or writes files.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"
ANALYSIS_DIR = ROOT / "analysis"
ENPS_FILE = RAW_DIR / "eNPS_Data.xlsx"
RECRUIT_FILE = RAW_DIR / "Recruitment_Data.xlsx"

AS_OF = pd.Timestamp("2026-10-31")
WAVES = {
    "Apr": {"open": pd.Timestamp("2026-04-06"), "close": pd.Timestamp("2026-04-17")},
    "Oct": {"open": pd.Timestamp("2026-10-05"), "close": pd.Timestamp("2026-10-16")},
}
TECH_FUNCTIONS = {"Engineering", "Product", "Data & Analytics", "Design & Research"}
EXCEL_SERIAL_ORIGIN = pd.Timestamp("1899-12-30")
NOTES_SHEETS = {"readme", "data_dictionary"}

EMP_ID_RE = re.compile(r"EMP\d{5}")
REQ_ID_RE = re.compile(r"REQ_\d+")

_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%d-%b-%y", "%d-%b-%Y")


def is_blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    if v is pd.NaT:
        return True
    return isinstance(v, str) and v.strip() == ""


def parse_date(v) -> pd.Timestamp:
    """Parse one raw cell: datetime, 'YYYY-MM-DD', 'DD/MM/YYYY' (day-first),
    'DD-Mon-YY', or an Excel serial number (days since 1899-12-30)."""
    if is_blank(v):
        return pd.NaT
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(v)
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
        return EXCEL_SERIAL_ORIGIN + pd.Timedelta(days=float(v)) if 20000 < v < 80000 else pd.NaT
    s = str(v).strip()
    if re.fullmatch(r"\d{5}(\.0+)?", s):
        return EXCEL_SERIAL_ORIGIN + pd.Timedelta(days=float(s))
    for fmt in _DATE_FORMATS:
        try:
            return pd.Timestamp(datetime.strptime(s, fmt))
        except ValueError:
            continue
    return pd.NaT


def date_format_of(v) -> str:
    """Label the raw format of a date cell (for logging/profiling)."""
    if is_blank(v):
        return "blank"
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return "datetime"
    s = str(v).strip()
    if isinstance(v, (int, float, np.integer, np.floating)) or re.fullmatch(r"\d{5}(\.0+)?", s):
        return "excel serial"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return "YYYY-MM-DD"
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", s):
        return "DD/MM/YYYY"
    if re.fullmatch(r"\d{1,2}-[A-Za-z]{3}-\d{2,4}", s):
        return "DD-Mon-YY"
    return "other"


def norm_emp_id(v):
    """Strip spaces and upper-case an employee ID. Blank stays None."""
    return None if is_blank(v) else str(v).strip().upper()


def norm_req_id(v):
    """Strip, upper-case and add the REQ_ prefix when it is missing."""
    if is_blank(v):
        return None
    s = str(v).strip().upper()
    if isinstance(v, float) and float(v).is_integer():
        s = str(int(v))
    return s if s.startswith("REQ_") else f"REQ_{s}"


def norm_grade(v):
    """'g1', 'Grade 3', '4', 'G10' -> 'G1'..'G10'; 'TBA'/'Trainee' -> 'TBA'. Unknown -> None."""
    if is_blank(v):
        return None
    s = str(v).strip().lower()
    if s in {"tba", "trainee"}:
        return "TBA"
    m = re.fullmatch(r"(?:g|grade\s*)?(\d{1,2})", s)
    return f"G{int(m.group(1))}" if m else None


def grade_num(g):
    """'TBA' -> 0, 'G7' -> 7."""
    if g is None:
        return None
    return 0 if g == "TBA" else int(g[1:])


def parse_inr(v):
    """INR amount: int, '4,48,000', '2.96 LPA', '8.44 L', '3.64 Lakhs' (lakh = 100,000)."""
    if is_blank(v):
        return np.nan
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().lower().replace(",", "")
    m = re.fullmatch(r"([\d.]+)\s*(lpa|lakhs?|lacs?|l)?", s)
    if not m:
        return np.nan
    x = float(m.group(1))
    return x * 100_000 if m.group(2) else x


def job_family(function) -> str:
    return "Tech" if str(function).strip() in TECH_FUNCTIONS else "Non-Tech"


def active_on(doj: pd.Series, exit_date: pd.Series, d: pd.Timestamp) -> pd.Series:
    """Active on date D = joined on/before D and (no exit or exit on/after D)."""
    return (doj <= d) & (exit_date.isna() | (exit_date >= d))
