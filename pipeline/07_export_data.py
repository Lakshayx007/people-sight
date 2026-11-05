"""
07_export_data.py
-----------------
Writes the downloadable workbook data/export/People_Sight_Clean_Data.xlsx from data/people.duckdb (v_* views only),
for anyone who wants to rebuild the dashboards in Power BI, Excel or another BI tool.

Sheets (each one is an Excel table, so Power BI lists it by name under Get data > Excel workbook):
  About               what the file is, sheet list with row counts, privacy rules, how to use it in Power BI
  Survey_Responses    one row per valid survey response, anonymised (see below)
  Survey_Headcount    people invited and people who responded, per wave and segment (response-rate denominator)
  Requisitions        one row per job opening, cleaned, with time to fill and SLA
  Candidates          one row per application, cleaned, with stage dates, stage times and offer outcome
  Candidates_Set_Aside applications that matched no opening, as received, with the reason
  Recruiters          recruiter list and monthly offer targets
  Cleaning_Log        every cleaning check: column, issue, rows affected, treatment, assumption
  Raw_to_Clean        row counts from raw sheet to clean table, step by step
  Metric_Definitions  how each dashboard metric is calculated from these columns
  Data_Dictionary     every column of every data sheet with its meaning

Survey anonymity. The file is downloadable, so row-level survey data gets stronger protection than the dashboard:
  - no Employee ID, name, response ID, respondent key, submission date or comment text;
  - only five describing columns: thread, function, tenure_band, manager_status, exited_after_wave;
  - k-anonymity with k = 5: within each wave every combination of those columns covers at least 5 responses. Where a
    combination is smaller, the least important column is replaced by HIDDEN for those rows (tenure band first, thread
    last) until every group has at least 5. Rows that still cannot reach 5 get every column hidden, topped up from the largest group, so no response is dropped.
  - performance rating, compa band, grade and location are not exported at row level (on the dashboard they are shown
    only as groups of 5 or more).
Hiring sheets name recruiters only (as the dashboard does); candidates, interviewers and hiring managers are IDs.
No employee master or employee salaries are exported.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import AS_OF, ROOT  # noqa: E402

DB = ROOT / "data" / "people.duckdb"
OUT = ROOT / "data" / "export" / "People_Sight_Clean_Data.xlsx"
K = 5
HIDDEN = "Hidden (group under 5)"
# describing columns kept on survey rows, in the order they are hidden (first = hidden first)
SURVEY_QI_HIDE_ORDER = ["tenure_band", "manager_status", "exited_after_wave", "function", "thread"]
SURVEY_QI = ["thread", "function", "tenure_band", "manager_status", "exited_after_wave"]
SURVEY_COLS = ["wave", "q1", "nps_group", "is_promoter", "is_passive", "is_detractor", "q2", "q3", "q4", "q5", "q6",
               "comment_theme"] + SURVEY_QI
HEADCOUNT_DIMS = ["wave", "thread", "function", "tenure_band", "manager_status"]

ACCENT = "2563EB"
HEAD_FILL = PatternFill("solid", fgColor="1E3A8A")
HEAD_FONT = Font(bold=True, color="FFFFFF")


# ── survey anonymisation ─────────────────────────────────────────────────────
def k_anonymise(df: pd.DataFrame, qi: list[str], hide_order: list[str], k: int = K) -> tuple[pd.DataFrame, int]:
    """Local recoding: hide one column at a time on rows whose (wave + qi) group is smaller than k."""
    d = df.copy()
    for c in qi:
        d[c] = d[c].map(lambda v: "Yes" if v is True else "No" if v is False else ("Unknown" if pd.isna(v) else str(v)))

    def small() -> pd.Series:
        return d.groupby(["wave"] + qi, dropna=False)["wave"].transform("size") < k

    for col in hide_order:
        s = small()
        if not s.any():
            break
        d.loc[s, col] = HIDDEN
    # Rows still in a group under k have every column hidden. Top that group up to k by fully hiding rows taken from
    # the largest group in the same wave (complementary suppression), so no response is ever dropped.
    for wave in d.loc[small(), "wave"].unique():
        short = k - int((small() & (d.wave == wave)).sum())
        sizes = d[d.wave == wave].groupby(qi).size().sort_values(ascending=False)
        donor = sizes.index[0]
        assert sizes.iloc[0] - short >= k
        mask = (d.wave == wave) & (d[qi].apply(tuple, axis=1) == donor)
        d.loc[d[mask].index[:short], qi] = HIDDEN
    s = small()
    assert not s.any()
    return d, int(s.sum())


def survey_sheets(con) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    raw = con.execute(f"SELECT {', '.join(SURVEY_COLS)} FROM v_survey").df()
    shuffled = raw.sample(frac=1, random_state=11).reset_index(drop=True)   # row order carries no information
    survey, dropped = k_anonymise(shuffled, SURVEY_QI, SURVEY_QI_HIDE_ORDER)
    survey = survey.sort_values(["wave", "thread", "function"], kind="stable").reset_index(drop=True)
    survey.insert(0, "response_row", range(1, len(survey) + 1))
    headcount = con.execute(f"""
        SELECT {', '.join(HEADCOUNT_DIMS)}, count(*) AS invited, sum(CASE WHEN responded THEN 1 ELSE 0 END) AS responded
        FROM v_invited GROUP BY ALL ORDER BY {', '.join(HEADCOUNT_DIMS)}""").df()
    return survey, headcount, dropped


# ── definitions and dictionary ───────────────────────────────────────────────
SURVEY_DICT = {
    "response_row": "Row number in this file (rows are in no meaningful order; not an ID)",
    "thread": f"Business thread. '{HIDDEN}' where showing it would identify a group under 5",
    "function": f"Function. '{HIDDEN}' where showing it would identify a group under 5",
    "tenure_band": f"Tenure at the wave open date: <6m, 6-12m, 1-2y, 2-4y, 4y+. '{HIDDEN}' where needed",
    "manager_status": f"Changed manager / New joiner (first manager) / Same manager. '{HIDDEN}' where needed",
    "exited_after_wave": f"Yes if the person left Porter after this wave closed (by 31-Oct-2026). '{HIDDEN}' where needed",
}
HEADCOUNT_DICT = {
    "wave": "Survey wave: Apr or Oct",
    "thread": "Business thread", "function": "Function",
    "tenure_band": "Tenure at the wave open date", "manager_status": "Changed manager / New joiner (first manager) / Same manager",
    "invited": "Employees active on the wave open date (invited to the survey)",
    "responded": "Of those, people with a valid response",
}
SET_ASIDE_DICT_NOTE = "Column as received in the raw Candidates sheet"

METRICS = [
    ("eNPS", "Survey_Responses",
     "% Promoters minus % Detractors, x 100, one decimal. Base = valid responses in the group.",
     "eNPS = DIVIDE(SUM(Survey_Responses[is_promoter]) - SUM(Survey_Responses[is_detractor]), COUNTROWS(Survey_Responses)) * 100"),
    ("Response rate", "Survey_Headcount",
     "People with a valid response / people active on the wave open date, same segment.",
     "Response rate = DIVIDE(SUM(Survey_Headcount[responded]), SUM(Survey_Headcount[invited]))"),
    ("Driver % favourable", "Survey_Responses",
     "Share answering 4 or 5 on Q2-Q6, among people who answered that question.",
     "Q2 favourable = DIVIDE(COUNTROWS(FILTER(Survey_Responses, Survey_Responses[q2] >= 4)), COUNT(Survey_Responses[q2]))"),
    ("Small-group rule", "Survey_Responses",
     "Do not show eNPS or a score for a group with fewer than 5 responses.",
     "IF(COUNTROWS(Survey_Responses) < 5, BLANK(), [eNPS])"),
    ("Time to fill (TTF)", "Requisitions",
     "Offer accepted date of the hired candidate minus the date the opening was raised, in days (filled openings).",
     "Median TTF = MEDIAN(Requisitions[ttf_days])"),
    ("Filled within SLA", "Requisitions",
     "Share of filled openings with TTF <= SLA days (30 for TBA-G2, 45 for G3-G5, 60 for G6+).",
     "Within SLA = DIVIDE(COUNTROWS(FILTER(Requisitions, Requisitions[sla_met] = TRUE())), COUNTROWS(FILTER(Requisitions, Requisitions[is_filled] = TRUE())))"),
    ("Open past SLA", "Requisitions",
     "Open openings whose age on 31-Oct-2026 exceeds their SLA days.",
     "Open past SLA = COUNTROWS(FILTER(Requisitions, Requisitions[open_breached] = TRUE()))"),
    ("Offer acceptance", "Candidates",
     "Accepted / (Accepted + Declined) offers.",
     "Offer acceptance = DIVIDE(COUNTROWS(FILTER(Candidates, Candidates[is_offer_accepted])), COUNTROWS(FILTER(Candidates, Candidates[is_offer_accepted] || Candidates[is_offer_declined])))"),
    ("Joining rate", "Candidates",
     "Joined / accepted offers whose expected joining date is on or before 31-Oct-2026.",
     "Joining rate = DIVIDE(COUNTROWS(FILTER(Candidates, Candidates[joining_due] && Candidates[is_joined])), COUNTROWS(FILTER(Candidates, Candidates[joining_due])))"),
    ("Stage time", "Candidates",
     "Median days between two consecutive stage dates (rows with both dates in the right order).",
     "Median screening to R1 = MEDIAN(Candidates[days_screening_to_r1])"),
    ("R1 feedback turnaround", "Candidates",
     "R1 feedback submitted date minus R1 interview date, in days.",
     "Median R1 feedback = MEDIAN(Candidates[r1_feedback_days])"),
    ("Agency fee", "Candidates",
     "8.33% of offered CTC for agency-sourced candidates who joined.",
     "Agency fees = SUM(Candidates[agency_fee_inr])"),
]


def view_comments(con, view: str) -> dict[str, str]:
    rows = con.execute("SELECT column_name, comment FROM duckdb_columns() WHERE table_name = ?", [view]).fetchall()
    return {c: (m or "") for c, m in rows}


# ── workbook writing ─────────────────────────────────────────────────────────
def to_cell(v):
    if v is None or (not isinstance(v, (list, dict, str)) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime().date()
    if hasattr(v, "item") and not isinstance(v, str):   # numpy scalar -> python
        return v.item()
    return v


def write_table(wb: Workbook, name: str, df: pd.DataFrame, widths: dict[str, int] | None = None) -> None:
    ws = wb.create_sheet(name)
    ws.append(list(df.columns))
    for row in df.itertuples(index=False):
        ws.append([to_cell(v) for v in row])
    for i, col in enumerate(df.columns, start=1):
        cell = ws.cell(row=1, column=i)
        cell.font, cell.fill = HEAD_FONT, HEAD_FILL
        cell.alignment = Alignment(vertical="center")
        letter = get_column_letter(i)
        if widths and col in widths:
            w = widths[col]
        else:
            sample = [len(str(col))] + [len(str(x)) for x in df[col].head(200) if x is not None]
            w = min(max(sample) + 2, 48)
        ws.column_dimensions[letter].width = max(w, 9)
        if pd.api.types.is_datetime64_any_dtype(df[col]) or df[col].map(lambda x: isinstance(x, date)).any():
            for c in ws[letter][1:]:
                c.number_format = "dd-mmm-yyyy"
    if widths:
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    ref = f"A1:{get_column_letter(len(df.columns))}{max(len(df) + 1, 2)}"
    tab = Table(displayName=name, ref=ref)
    tab.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(tab)
    ws.freeze_panes = "A2"


def write_about(ws, sheets: list[tuple[str, int, str]], dropped: int, hidden_share: dict[str, float]) -> None:
    ws.title = "About"
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 96
    ws["A1"] = "People Sight: clean data"
    ws["A1"].font = Font(bold=True, size=18, color="0F172A")
    ws["A2"] = (f"Porter employee pulse surveys (April and October 2026) and hiring data, cleaned and ready for Power BI or "
                f"Excel. Data as of {AS_OF:%d-%b-%Y}. Sample (synthetic) case data. Generated {date.today():%d-%b-%Y}.")
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.merge_cells("A2:C2")
    ws.row_dimensions[2].height = 32

    r = 4
    ws.cell(r, 1, "Sheet").font = HEAD_FONT
    ws.cell(r, 2, "Rows").font = HEAD_FONT
    ws.cell(r, 3, "What it holds").font = HEAD_FONT
    ws.cell(r, 3).alignment = Alignment(indent=1)
    for c in range(1, 4):
        ws.cell(r, c).fill = HEAD_FILL
    for name, n, desc in sheets:
        r += 1
        ws.cell(r, 1, name).font = Font(bold=True, color=ACCENT)
        ws.cell(r, 1).hyperlink = f"#'{name}'!A1"
        ws.cell(r, 2, n).number_format = "#,##0"
        ws.cell(r, 3, desc).alignment = Alignment(wrap_text=True, vertical="top", indent=1)

    def section(title: str, lines: list[str]) -> None:
        nonlocal r
        r += 2
        ws.cell(r, 1, title).font = Font(bold=True, size=13, color="0F172A")
        for line in lines:
            r += 1
            ws.cell(r, 1, line).alignment = Alignment(wrap_text=True, vertical="top")
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
            ws.row_dimensions[r].height = 15.5 * max(1, -(-len(line) // 120))

    kept = ", ".join(f"{c} {v:.0%}" for c, v in hidden_share.items())
    section("Privacy", [
        "The file holds no employee records or employee salaries. Survey rows have no name, Employee ID, response ID, "
        "submission date or comment text, so a survey answer cannot be traced to a person.",
        f"Every combination of wave, thread, function, tenure band, manager status and exit flag covers at least {K} "
        f"responses. Where a combination was smaller, the least important column shows '{HIDDEN}' on those rows.",
        f"Share of survey rows where each column is shown: {kept}. "
        + ("No response is left out, so company-wide numbers match the dashboard exactly." if not dropped
           else f"{dropped} responses could not be grouped safely and are left out."),
        "Splits by thread, function, tenure or manager status can differ slightly from the dashboard, which works on the "
        "full data and hides only groups under 5. Use the dashboard for the official segment figures.",
        "Performance rating, compa band, grade and location are not exported for survey rows. On the hiring sheets, "
        "candidates, interviewers and hiring managers appear by ID only; recruiters are named, as on the Hiring dashboard.",
    ])
    section("Use it in Power BI", [
        "1. Home > Get data > Excel workbook, choose this file, tick the tables you need (each sheet is a named table).",
        "2. Relationships: Candidates[req_id] to Requisitions[req_id] (many to one); Requisitions[recruiter_id] to "
        "Recruiters[recruiter_id]. Survey tables do not link to hiring tables, by design.",
        "3. Create the measures on the Metric_Definitions sheet (DAX given), and keep the small-group rule for survey visuals.",
        "4. Cleaning_Log and Raw_to_Clean show every change made to the raw spreadsheets and why.",
    ])


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    survey, headcount, dropped = survey_sheets(con)
    req = con.execute("SELECT * FROM v_requisitions ORDER BY req_id").df()
    cand = con.execute("SELECT * FROM v_candidates ORDER BY req_id, candidate_id").df()
    rec = con.execute("SELECT * FROM v_recruiters ORDER BY recruiter_id").df()
    dq = con.execute("SELECT * FROM v_dq_log ORDER BY dataset, sheet, \"column\"").df()
    recon = con.execute("SELECT * FROM v_reconciliation ORDER BY dataset, sheet, \"order\"").df()
    comments = {v: view_comments(con, v) for v in ["v_survey", "v_invited", "v_requisitions", "v_candidates", "v_recruiters", "v_dq_log",
                                                   "v_reconciliation"]}
    con.close()

    aside = pd.read_parquet(ROOT / "data" / "clean" / "candidates_excluded.parquet")
    aside = aside.drop(columns=["candidate_id", "req_id"]).rename(columns={"exclusion_reason": "Reason set aside"})
    for c in aside.columns:
        if aside[c].dtype == object:
            aside[c] = aside[c].map(lambda v: v if v is None or isinstance(v, (str, int, float)) else str(v))

    metrics = pd.DataFrame(METRICS, columns=["Metric", "Sheet", "Definition", "Power BI measure (DAX)"])

    dictionary = []
    for sheet, df, desc in [("Survey_Responses", survey, {**comments["v_survey"], **SURVEY_DICT}),
                            ("Survey_Headcount", headcount, {**comments["v_invited"], **HEADCOUNT_DICT}),
                            ("Requisitions", req, comments["v_requisitions"]), ("Candidates", cand, comments["v_candidates"]),
                            ("Recruiters", rec, comments["v_recruiters"]), ("Cleaning_Log", dq, comments["v_dq_log"]),
                            ("Raw_to_Clean", recon, comments["v_reconciliation"])]:
        for c in df.columns:
            assert desc.get(c), f"{sheet}.{c} has no description"
            dictionary.append((sheet, c, desc[c]))
    for c in aside.columns:
        dictionary.append(("Candidates_Set_Aside", c, "Why the row was set aside" if c == "Reason set aside"
                           else SET_ASIDE_DICT_NOTE))
    dictionary = pd.DataFrame(dictionary, columns=["Sheet", "Column", "Meaning"])

    sheets = [
        ("Survey_Responses", survey, "One row per valid survey response, anonymised (see Privacy below)."),
        ("Survey_Headcount", headcount, "People invited and people who responded, per wave and segment. Use for response rate."),
        ("Requisitions", req, "One row per job opening: grade, recruiter, status, time to fill, SLA and backfill details."),
        ("Candidates", cand, "One row per application: source, stage dates, days per stage, offer and joining outcome."),
        ("Candidates_Set_Aside", aside, "Applications that matched no job opening, as received, with the reason. Not used in any metric."),
        ("Recruiters", rec, "Recruiters and their monthly offer targets."),
        ("Cleaning_Log", dq, "Every cleaning check: what was found, how many rows, what was done and the assumption behind it."),
        ("Raw_to_Clean", recon, "Row counts from each raw sheet to the clean table, step by step."),
        ("Metric_Definitions", metrics, "How each dashboard metric is calculated, with a ready-made Power BI measure."),
        ("Data_Dictionary", dictionary, "The meaning of every column on every sheet."),
    ]

    wb = Workbook()
    shown = {c: float((survey[c] != HIDDEN).mean()) for c in SURVEY_QI}
    write_about(wb.active, [(n, len(df), d) for n, df, d in sheets], dropped, shown)
    wide = {
        "Cleaning_Log": {"dataset": 12, "sheet": 18, "column": 22, "issue": 48, "rows_affected": 14, "treatment": 52, "assumption": 52},
        "Metric_Definitions": {"Metric": 22, "Sheet": 18, "Definition": 60, "Power BI measure (DAX)": 90},
        "Data_Dictionary": {"Sheet": 22, "Column": 30, "Meaning": 100},
        "Raw_to_Clean": {"dataset": 12, "sheet": 20, "step": 50, "order": 8, "rows": 10, "change": 10, "note": 60},
    }
    for name, df, _ in sheets:
        write_table(wb, name, df, wide.get(name))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp.xlsx")
    wb.save(tmp)
    tmp.replace(OUT)

    print(f"Wrote {OUT.relative_to(ROOT) if OUT.is_relative_to(ROOT) else OUT}")
    for name, df, _ in sheets:
        print(f"  {name:<22} {len(df):>6} rows")
    print(f"  survey rows left out for anonymity: {dropped}; shown share: "
          + ", ".join(f"{c} {v:.0%}" for c, v in shown.items()))


if __name__ == "__main__":
    main()
