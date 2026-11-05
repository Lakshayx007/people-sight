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
    return pd.read_excel(export.OUT, sheet_name=["Survey Responses", "Survey Headcount", "Requisitions", "Candidates",
                                                 "Recruiters"])


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


SURVEY = "Survey Responses"
HEADCOUNT = "Survey Headcount"


def test_sheets_and_tables(export):
    wb = load_workbook(export.OUT)
    assert wb.sheetnames == ["Survey Responses", "Survey Headcount", "Requisitions", "Candidates", "Recruiters",
                             "How It Was Cleaned"]
    tables = {t for ws in wb for t in ws.tables}
    assert tables == {"Survey_Responses", "Survey_Headcount", "Requisitions", "Candidates", "Recruiters", "Cleaning_Notes"}


def test_every_header_has_a_note(export):
    wb = load_workbook(export.OUT)
    for name in wb.sheetnames[:-1]:
        for cell in wb[name][1]:
            assert cell.comment and cell.comment.text.strip(), f"{name}.{cell.value}"
            assert "v_" not in cell.comment.text, f"{name}.{cell.value}"


def test_survey_has_no_identifiers(sheets):
    cols = {c.lower() for c in sheets[SURVEY].columns}
    for banned in ["employee", "name", "response id", "respondent", "comment text", "submitted", "grade", "location",
                   "rating", "compa", "ctc"]:
        assert not any(banned in c for c in cols), banned


def test_no_names_anywhere(sheets, con):
    names = {r[0] for r in con.execute("SELECT employee_name FROM v_interviewers").fetchall()}
    for name, df in sheets.items():
        values = set(df.astype(str).stack())
        assert not values & names, name


def test_survey_groups_are_at_least_5(export, sheets):
    s = sheets[SURVEY]
    qi = [export.SURVEY_HEADERS[c][0] for c in export.SURVEY_QI]
    sizes = s.fillna("").groupby(["Survey Wave"] + qi).size()
    assert sizes.min() >= export.K


def test_survey_reconciles_with_database(export, sheets, con):
    s = sheets[SURVEY]
    db = con.execute("SELECT wave, count(*) n, sum(is_promoter) p, sum(is_detractor) d FROM v_survey GROUP BY wave").df()
    for r in db.itertuples():
        w = s[s["Survey Wave"] == export.WAVE_LABEL[r.wave]]
        assert len(w) == r.n
        assert int(w["Promoter (1/0)"].sum()) == r.p and int(w["Detractor (1/0)"].sum()) == r.d


def test_headcount_reconciles(export, sheets, con):
    h = sheets[HEADCOUNT]
    db = con.execute("SELECT wave, count(*) inv, sum(CASE WHEN responded THEN 1 ELSE 0 END) resp FROM v_invited GROUP BY wave").df()
    for r in db.itertuples():
        w = h[h["Survey Wave"] == export.WAVE_LABEL[r.wave]]
        assert int(w.Invited.sum()) == r.inv and int(w.Responded.sum()) == r.resp


def test_hiring_row_counts(sheets, con):
    for sheet, view in [("Requisitions", "v_requisitions"), ("Candidates", "v_candidates"), ("Recruiters", "v_recruiters")]:
        assert len(sheets[sheet]) == con.execute(f"SELECT count(*) FROM {view}").fetchone()[0], sheet


def test_cleaning_notes_cover_the_log(export):
    dq = pd.read_csv(ROOT / "data" / "clean" / "dq_log.csv")
    notes = export.cleaning_notes(dq)          # asserts every data-changing log row is explained
    assert (notes.Records > 0).all()
    for col in ["What we found", "What we did", "Why"]:
        assert notes[col].str.len().gt(3).all()
        assert not notes[col].str.contains(r"—|\b[a-z]+_[a-z]+\b", regex=True).any(), col


def test_k_anonymise_tops_up_small_group(export):
    df = pd.DataFrame({"wave": ["Apr"] * 12, "thread": ["A"] * 11 + ["B"], "function": ["X"] * 12,
                       "tenure_band": ["1-2y"] * 12, "manager_status": ["Same manager"] * 12, "exited_after_wave": [False] * 12})
    out, dropped = export.k_anonymise(df, export.SURVEY_QI, export.SURVEY_QI_HIDE_ORDER, k=5)
    assert dropped == 0 and len(out) == 12
    assert out.groupby(["wave"] + export.SURVEY_QI).size().min() >= 5
    assert (out.thread == export.HIDDEN).sum() == 5
