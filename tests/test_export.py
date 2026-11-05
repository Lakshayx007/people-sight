"""The downloadable workbook: right sheets, anonymous survey rows (k >= 5, no IDs or names), numbers that reconcile."""
import importlib.util
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "people.duckdb"


@pytest.fixture(scope="module")
def export(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("export07", ROOT / "pipeline" / "07_export_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.OUT = tmp_path_factory.mktemp("export") / "clean.xlsx"
    mod.main()
    return mod


@pytest.fixture(scope="module")
def sheets(export):
    return pd.read_excel(export.OUT, sheet_name=None)


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


def test_sheets_are_named_tables(export):
    wb = load_workbook(export.OUT)
    assert wb.sheetnames[0] == "About"
    expected = {"Survey_Responses", "Survey_Headcount", "Requisitions", "Candidates", "Candidates_Set_Aside", "Recruiters",
                "Cleaning_Log", "Raw_to_Clean", "Metric_Definitions", "Data_Dictionary"}
    assert expected == set(wb.sheetnames[1:])
    for name in expected:
        assert list(wb[name].tables) == [name]


def test_survey_has_no_identifiers(sheets):
    cols = {c.lower() for c in sheets["Survey_Responses"].columns}
    banned = {"employee_id", "employee_name", "response_id", "respondent_key", "comment", "submitted_date", "grade",
              "location", "performance_rating", "compa_band"}
    assert not cols & banned


def test_no_names_anywhere(sheets, con):
    names = {r[0] for r in con.execute("SELECT employee_name FROM v_interviewers").fetchall()}
    for name, df in sheets.items():
        if name == "About":
            continue
        values = set(df.astype(str).stack())
        assert not values & names, name
        assert not any("name" == c.lower() or c.lower().endswith("_name") and c != "agency_name" and c != "Agency Name"
                       for c in df.columns), name


def test_survey_groups_are_at_least_5(export, sheets):
    s = sheets["Survey_Responses"]
    sizes = s.fillna("").groupby(["wave"] + export.SURVEY_QI).size()
    assert sizes.min() >= export.K


def test_survey_reconciles_with_database(sheets, con):
    s = sheets["Survey_Responses"]
    db = con.execute("SELECT wave, count(*) n, sum(is_promoter) p, sum(is_detractor) d FROM v_survey GROUP BY wave").df()
    for r in db.itertuples():
        w = s[s.wave == r.wave]
        assert len(w) == r.n
        assert int(w.is_promoter.sum()) == r.p and int(w.is_detractor.sum()) == r.d


def test_headcount_reconciles(sheets, con):
    h = sheets["Survey_Headcount"]
    db = con.execute("SELECT wave, count(*) inv, sum(CASE WHEN responded THEN 1 ELSE 0 END) resp FROM v_invited GROUP BY wave").df()
    for r in db.itertuples():
        w = h[h.wave == r.wave]
        assert int(w.invited.sum()) == r.inv and int(w.responded.sum()) == r.resp


def test_hiring_and_log_row_counts(sheets, con):
    for sheet, view in [("Requisitions", "v_requisitions"), ("Candidates", "v_candidates"), ("Recruiters", "v_recruiters"),
                        ("Cleaning_Log", "v_dq_log"), ("Raw_to_Clean", "v_reconciliation")]:
        assert len(sheets[sheet]) == con.execute(f"SELECT count(*) FROM {view}").fetchone()[0], sheet


def test_every_column_is_documented(sheets):
    d = sheets["Data_Dictionary"]
    documented = set(zip(d.Sheet, d.Column))
    for name, df in sheets.items():
        if name in ("About", "Metric_Definitions", "Data_Dictionary"):
            continue
        for c in df.columns:
            assert (name, c) in documented, f"{name}.{c}"
    assert d.Meaning.notna().all()


def test_k_anonymise_tops_up_small_group(export):
    df = pd.DataFrame({"wave": ["Apr"] * 12, "thread": ["A"] * 11 + ["B"], "function": ["X"] * 12,
                       "tenure_band": ["1-2y"] * 12, "manager_status": ["Same manager"] * 12, "exited_after_wave": [False] * 12})
    out, dropped = export.k_anonymise(df, export.SURVEY_QI, export.SURVEY_QI_HIDE_ORDER, k=5)
    assert dropped == 0 and len(out) == 12
    assert out.groupby(["wave"] + export.SURVEY_QI).size().min() >= 5
    assert (out.thread == export.HIDDEN).sum() == 5
