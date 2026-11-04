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
    if is_blank(g):
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


# ── data-quality log + reconciliation (shared by 02 and 03) ──────────────────
DQ_COLUMNS = ["dataset", "sheet", "column", "issue", "rows_affected", "treatment", "assumption"]
RECON_COLUMNS = ["dataset", "sheet", "step", "order", "rows", "change", "note"]


class DQLog:
    """Collects cleaning decisions for one dataset, then writes them into
    data/clean/dq_log.csv and reconciliation.csv, replacing only that dataset's
    earlier rows so each script can be re-run on its own."""

    def __init__(self, dataset: str):
        self.dataset = dataset
        self.rows: list[dict] = []
        self.recon: list[dict] = []

    def log(self, sheet, column, issue, rows_affected, treatment, assumption=""):
        self.rows.append(dict(dataset=self.dataset, sheet=sheet, column=column, issue=issue,
                              rows_affected=int(rows_affected), treatment=treatment, assumption=assumption))

    def step(self, sheet, step, rows, note=""):
        prev = [r for r in self.recon if r["sheet"] == sheet]
        change = "" if not prev else int(rows) - prev[-1]["rows"]
        self.recon.append(dict(dataset=self.dataset, sheet=sheet, step=step, order=len(prev) + 1,
                               rows=int(rows), change=change, note=note))

    def _merge(self, path: Path, new: list[dict], cols: list[str]):
        old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=cols)
        old = old[old["dataset"] != self.dataset]
        out = pd.concat([old, pd.DataFrame(new, columns=cols)], ignore_index=True)
        out.to_csv(path, index=False)
        return out

    def write(self):
        CLEAN_DIR.mkdir(parents=True, exist_ok=True)
        self._merge(CLEAN_DIR / "dq_log.csv", self.rows, DQ_COLUMNS)
        self._merge(CLEAN_DIR / "reconciliation.csv", self.recon, RECON_COLUMNS)


def tenure_band(doj: pd.Series, on: pd.Timestamp) -> pd.Series:
    """Tenure band at date `on`: <6m, 6-12m, 1-2y, 2-4y, 4y+ (calendar months/years)."""
    out = pd.Series(pd.NA, index=doj.index, dtype="object")
    ok = doj.notna() & (doj <= on)
    edges = [(on - pd.DateOffset(months=6), "<6m"), (on - pd.DateOffset(years=1), "6-12m"),
             (on - pd.DateOffset(years=2), "1-2y"), (on - pd.DateOffset(years=4), "2-4y")]
    rest = ok.copy()
    for edge, label in edges:
        hit = rest & (doj > edge)
        out[hit] = label
        rest &= ~hit
    out[rest] = "4y+"
    return out


TENURE_BANDS = ["<6m", "6-12m", "1-2y", "2-4y", "4y+"]
COMPA_BANDS = ["Below", "At", "Above", "Unknown"]


# ── shared categorical rules ─────────────────────────────────────────────────
THREADS = ["Intracity", "Intercity", "Enterprise", "Packers & Movers", "Geo Expansion", "Central"]
_THREAD_KEY = {"intracity": "Intracity", "intercity": "Intercity", "enterprise": "Enterprise",
               "packers&movers": "Packers & Movers", "packersandmovers": "Packers & Movers",
               "p&m": "Packers & Movers", "geoexpansion": "Geo Expansion", "central": "Central"}


def thread_clean(v):
    """'Intra City', 'InterCity', 'P&M', 'Geo-Expansion', 'central ' -> one of THREADS (None if unknown)."""
    if is_blank(v):
        return None
    return _THREAD_KEY.get(re.sub(r"[\s\-]", "", str(v).strip().lower()))
