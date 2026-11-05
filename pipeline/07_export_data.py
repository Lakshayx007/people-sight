"""
07_export_data.py
-----------------
Writes data/export/People_Sight_Clean_Data.xlsx from data/people.duckdb and the cleaning log: the clean data and a
plain account of how it was cleaned, for anyone at Porter who wants to work with it in Excel or Power BI.

Sheets (each one is also a named Excel table, so Power BI lists it under Get data > Excel workbook):
  Survey Responses   one row per valid survey response, anonymised (below)
  Survey Headcount   people invited and people who responded, per wave and group (for response rates)
  Requisitions       one row per job opening
  Candidates         one row per application
  Recruiters         recruiters and monthly offer targets
  How It Was Cleaned what was wrong in the raw spreadsheets, what we did and why, with the records affected
Column meanings sit in a note on each header cell.

Survey anonymity. Row-level survey data leaves the dashboard here, so it gets stronger protection:
  - no Employee ID, name, response ID, respondent key, submission date or comment text;
  - only five describing columns: thread, function, tenure band, manager status, left after the survey;
  - k-anonymity, k = 5: within each wave every combination of those columns covers at least 5 responses. Where it does
    not, the least important column is hidden on those rows (tenure band first, thread last); any rows still short get
    every column hidden and the group is topped up from the largest group, so no response is dropped.
Hiring sheets name recruiters only (as the dashboard does); candidates, interviewers and hiring managers are IDs.
No employee master or employee salaries are exported.

Every count in "How It Was Cleaned" is summed from data/clean/dq_log.csv at run time; the build fails if a note no
longer matches the log or a data-changing log row has no note.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import AS_OF, CLEAN_DIR, ROOT  # noqa: E402

DB = ROOT / "data" / "people.duckdb"
OUT = ROOT / "data" / "export" / "People_Sight_Clean_Data.xlsx"
K = 5
HIDDEN = "Hidden (group under 5)"
SURVEY_QI = ["thread", "function", "tenure_band", "manager_status", "exited_after_wave"]
SURVEY_QI_HIDE_ORDER = ["tenure_band", "manager_status", "exited_after_wave", "function", "thread"]
SURVEY_COLS = ["wave", "q1", "nps_group", "is_promoter", "is_passive", "is_detractor", "q2", "q3", "q4", "q5", "q6",
               "comment_theme"] + SURVEY_QI
HEADCOUNT_DIMS = ["wave", "thread", "function", "tenure_band", "manager_status"]
WAVE_LABEL = {"Apr": "April 2026", "Oct": "October 2026"}

HEAD_FILL = PatternFill("solid", fgColor="1E3A8A")
HEAD_FONT = Font(bold=True, color="FFFFFF")
INK = "0F172A"


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


def survey_tables(con) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = con.execute(f"SELECT {', '.join(SURVEY_COLS)} FROM v_survey").df()
    shuffled = raw.sample(frac=1, random_state=11).reset_index(drop=True)   # row order carries no information
    survey, dropped = k_anonymise(shuffled, SURVEY_QI, SURVEY_QI_HIDE_ORDER)
    assert dropped == 0
    survey = survey.sort_values(["wave", "thread", "function"], kind="stable").reset_index(drop=True)
    headcount = con.execute(f"""
        SELECT {', '.join(HEADCOUNT_DIMS)}, count(*) AS invited, sum(CASE WHEN responded THEN 1 ELSE 0 END) AS responded
        FROM v_invited GROUP BY ALL ORDER BY {', '.join(HEADCOUNT_DIMS)}""").df()
    for df in (survey, headcount):
        df["wave"] = df["wave"].map(WAVE_LABEL)
    return survey, headcount


# ── headers and their notes ──────────────────────────────────────────────────
SURVEY_HEADERS = {
    "wave": ("Survey Wave", "April 2026 (06-17 Apr) or October 2026 (05-16 Oct)"),
    "q1": ("Q1 Recommend Porter (0-10)", "How likely are you to recommend Porter as a place to work? 0 = not at all, 10 = extremely likely"),
    "nps_group": ("NPS Group", "Promoter (9-10), Passive (7-8) or Detractor (0-6) on Q1"),
    "is_promoter": ("Promoter (1/0)", "1 if Promoter. eNPS = % Promoters - % Detractors"),
    "is_passive": ("Passive (1/0)", "1 if Passive"),
    "is_detractor": ("Detractor (1/0)", "1 if Detractor"),
    "q2": ("Q2 Manager Feedback (1-5)", "My manager gives me regular, useful feedback. 1 = strongly disagree, 5 = strongly agree. Blank = not answered"),
    "q3": ("Q3 Fair Pay (1-5)", "I am paid fairly for the work I do. Blank = not answered"),
    "q4": ("Q4 Workload (1-5)", "My workload is manageable. Blank = not answered"),
    "q5": ("Q5 Onboarding & Tools (1-5)", "I had the onboarding, tools and training I needed. Blank = not answered"),
    "q6": ("Q6 Growth Path (1-5)", "I can see a clear growth path for myself at Porter. Blank = not answered"),
    "comment_theme": ("Comment Theme", "Theme of the comment: Manager, Pay, Growth, Workload, Onboarding or Positive. Blank = no comment"),
    "thread": ("Thread", f"Business thread. Shows '{HIDDEN}' where it would point to fewer than 5 people"),
    "function": ("Function", f"Function. Shows '{HIDDEN}' where it would point to fewer than 5 people"),
    "tenure_band": ("Tenure Band", f"Time at Porter on the survey's opening day: <6m, 6-12m, 1-2y, 2-4y, 4y+. Shows '{HIDDEN}' where needed"),
    "manager_status": ("Manager Status", f"Changed manager between the surveys, New joiner (first manager), or Same manager. Shows '{HIDDEN}' where needed"),
    "exited_after_wave": ("Left Porter After Survey", f"Yes if the person left Porter after this survey closed (up to 31-Oct-2026). Shows '{HIDDEN}' where needed"),
}
HEADCOUNT_HEADERS = {
    "wave": SURVEY_HEADERS["wave"],
    "thread": ("Thread", "Business thread"),
    "function": ("Function", "Function"),
    "tenure_band": ("Tenure Band", "Time at Porter on the survey's opening day"),
    "manager_status": ("Manager Status", "Changed manager / New joiner (first manager) / Same manager"),
    "invited": ("Invited", "Employees working at Porter on the survey's opening day"),
    "responded": ("Responded", "Of those, people with a valid response. Response rate = Responded / Invited"),
}
ACRONYMS = {"id": "ID", "ctc": "CTC", "sla": "SLA", "ttf": "TTF", "doj": "DOJ", "r1": "R1", "r2": "R2", "inr": "(INR)",
            "ijp": "IJP", "hr": "HR"}
SMALL = {"to", "of", "and", "or", "in", "a", "the"}
SPECIAL = {"age_days_as_of_31oct": "Age in Days (31-Oct-2026)", "grade_num": "Grade Number", "req_ttf_days": "Req TTF Days",
           "req_sla_met": "Req SLA Met", "replaced_is_regrettable": "Replaced Regrettable Exit", "sla_days": "SLA Days", "ttf_days": "TTF Days"}


def title(col: str) -> str:
    if col in SPECIAL:
        return SPECIAL[col]
    words = col.split("_")
    if words[0] == "is" and len(words) > 1:
        words = words[1:]
    out = []
    for i, w in enumerate(words):
        out.append(ACRONYMS.get(w) or (w if (w in SMALL and i) else w.capitalize()))
    return " ".join(out)


def tidy_note(text: str, names: dict[str, str]) -> str:
    """Database comment -> header note: drop view references, say column names the way the headers do."""
    text = re.sub(r"\s*\(see v_\w+\)", "", text or "").replace("Employee_Master", "the employee list")
    text = text.replace("v_requisitions", "Requisitions").replace("v_candidates", "Candidates")
    text = text.replace("requisition budgeted_max_ctc", "budgeted_max_ctc")
    for col in sorted((c for c in names if "_" in c), key=len, reverse=True):   # only code-style names
        text = re.sub(rf"\b{re.escape(col)}\b", f"[{names[col]}]", text)
    return text.strip()


# ── how it was cleaned ───────────────────────────────────────────────────────
APPROACH = [
    "The original spreadsheets were never edited. Every change below is made by code, so it can be checked and rerun.",
    "Spellings were merged only when they clearly meant the same thing. Nothing was guessed: anything that could not be "
    "verified was flagged or left out of the numbers.",
    "When two versions of a record disagreed, the most recently updated one was kept.",
    f"Survey answers stay anonymous: no names or IDs, and no group of answers smaller than {K}.",
]

E, S, B, R, C = "Employees", "Survey responses", "Pay bands", "Requisitions", "Candidates"
# (area, field, what we found, what we did, why, [(sheet, column, issue prefix), ...] matched against the cleaning log)
NOTES = [
    (E, "Employee ID", "Some IDs had extra spaces or a lowercase 'emp'.", "Trimmed and upper-cased them.",
     "So one person matches across every sheet.", [("Employee_Master", "Employee ID", "Leading/trailing")]),
    (E, "Whole row", "Some employees appeared twice with identical details.", "Kept one copy.",
     "Each person is counted once.", [("Employee_Master", "(all columns)", "Exact duplicate")]),
    (E, "Whole row", "Some employees appeared twice with different details (mostly location).",
     "Kept the version with the latest 'Record Updated On'.", "The latest HR update is the current record.",
     [("Employee_Master", "Employee ID", "Same ID, different")]),
    (E, "Thread", "The same thread was typed many ways ('InterCity', 'Inter City', 'P&M', 'Geo-Expansion').",
     "Merged into the six threads: Intracity, Intercity, Enterprise, Packers & Movers, Geo Expansion, Central.",
     "Otherwise one team shows up as several.", [("Employee_Master", "Thread", "Spelling")]),
    (E, "Grade", "Grades written as 'g1', 'Grade 3', '4' or 'Trainee'.", "Standardised to TBA and G1 to G10.",
     "Grades can be compared and sorted.", [("Employee_Master", "Grade", "Variants")]),
    (E, "Location", "Cities spelled differently ('BLR - HO', 'Bangalore HO', 'Hyd', 'MUMBAI', 'Calcutta').",
     "Standardised city names. Bengaluru head office kept separate from the Bengaluru city office.",
     "Head office and city teams work differently, so they stay apart.",
     [("Employee_Master", "Location", "Spelling")]),
    (E, "Location", "Delhi, New Delhi and Gurugram used for the same region.", "Merged into Delhi NCR.",
     "They are one operating region.", [("Employee_Master", "Location", "Delhi")]),
    (E, "Location", "Some rows just said 'BLR', which could mean head office or city office.",
     "Used the Location Type column: all were City, so Bengaluru city office.", "Location Type settles it without guessing.",
     [("Employee_Master", "Location", "Ambiguous")]),
    (E, "Location Type", "Blank on some rows.", "Filled: HO for Bengaluru HO, City for everyone else.",
     "That is the rule every other row follows.", [("Employee_Master", "Location Type", "Blank")]),
    (E, "Employment Status", "Written as 'ACTIVE', 'Active ' or 'EXITED'.", "Standardised to Active or Exited.",
     "Consistent status for headcount.", [("Employee_Master", "Employment Status", "Case")]),
    (E, "Dates", "Joining and exit dates came in several formats (31/03/2025, 2025-03-31, 31-Mar-25).",
     "Converted to real dates.", "DD/MM/YYYY read day first, the Indian convention.",
     [("Employee_Master", "Date of Joining", "Mixed formats"), ("Employee_Master", "Date of Exit", "Mixed formats")]),
    (E, "Employment Status", "Marked Active but with an exit date and exit type filled in.", "Set to Exited.",
     "Exit date, type and classification all agree; the status had not been updated.",
     [("Employee_Master", "Employment Status", "'Active' but")]),
    (E, "Date of Exit", "Marked Exited but with no exit date.",
     "Kept as Exited with the date unknown, and left out of the October survey's invited list.",
     "One of them already had a replacement hired in July, so they had left before October.",
     [("Employee_Master", "Employment Status", "'Exited' status kept")]),
    (E, "Performance Rating", "'New Joiner' label, or blank for people who joined after 01-Jan-2026.",
     "Both set to 'Not Rated - New Joiner'.", "Recent joiners are not rated yet.",
     [("Employee_Master", "Performance Rating FY25-26", "'New Joiner'"),
      ("Employee_Master", "Performance Rating FY25-26", "Blank for joiners")]),
    (E, "Annual CTC", "Salaries typed as '4,48,000', '2.96 LPA', '8.44 L' or '3.64 Lakhs'.",
     "Converted to rupees (1 lakh = 100,000).", "Needed to compare pay with the pay band.",
     [("Employee_Master", "Annual CTC (INR)", "Indian-comma"), ("Employee_Master", "Annual CTC (INR)", "Lakh")]),
    (E, "Annual CTC", "A few salaries were about one twelfth of the pay band.", "Multiplied by 12 and flagged.",
     "A monthly salary had been entered in the annual field.", [("Employee_Master", "Annual CTC (INR)", "Value < 0.5x")]),
    (E, "Annual CTC", "Blank for some employees.", "Left blank; their pay position shows as Unknown.",
     "No salary was invented.", [("Employee_Master", "Annual CTC (INR)", "Blank")]),
    (E, "Manager change", "HR records only the current manager and the date they took over.",
     "'Changed manager' when that date falls between the two surveys and after the person joined.",
     "A new joiner getting their first manager is not a manager change, so they are a separate group.",
     [("Employee_Master", "Manager Effective From", "manager_status: 'Changed manager'")]),
    (B, "Effective From", "Two sets of pay bands (April 2025 and April 2026).", "Used the April 2026 set.",
     "It was in force on both survey dates and on 31-Oct-2026.", [("Pay_Bands", "Effective From", "Two band sets")]),
    (S, "Employee ID", "Some IDs had extra spaces or a lowercase 'emp'.", "Trimmed and upper-cased them.",
     "So each answer matches its employee.", [("eNPS_Responses", "Employee ID", "Leading/trailing")]),
    (S, "Survey Wave", "Eight spellings of the two survey rounds ('April'26', 'apr 2026', 'Oct-2026').",
     "Standardised to April 2026 and October 2026, checked against the submission date.", "Two rounds, two labels.",
     [("eNPS_Responses", "Survey Wave", "8 spellings")]),
    (S, "Q1", "Some scores typed as '7/10'.", "Kept the number.", "Same answer, different format.",
     [("eNPS_Responses", "Q1", "'x/10'")]),
    (S, "Q1", "Blank, or outside 0 to 10 (-1, 11, 12).", "Response left out of all survey numbers.",
     "Without a valid Q1 there is no eNPS answer, and every survey number should use the same base.",
     [("eNPS_Responses", "Q1", "Q1 blank"), ("eNPS_Responses", "Q1", "Q1 outside")]),
    (S, "Q2 to Q6", "Some questions skipped.", "Left blank and left out of that question only.",
     "The rest of the person's answers still count.",
     [("eNPS_Responses", f"Q{i}", "Blank answer") for i in range(2, 7)]),
    (S, "Employee ID", "Test entries (TEST001, TEST002, HRTEST).", "Left out.", "Not real employees.",
     [("eNPS_Responses", "Employee ID", "Test IDs")]),
    (S, "Employee ID", "IDs not found in the employee list.", "Left out.",
     "We cannot confirm they were invited or place them in a team.", [("eNPS_Responses", "Employee ID", "Not in")]),
    (S, "Whole response", "The same person answered the same survey twice.", "Kept the later answer.",
     "The last answer is the one they meant.", [("eNPS_Responses", "Response ID", "Same employee")]),
    (S, "Submitted On", "Answers from people who had not joined yet or had already left on the opening day.",
     "Left out.", "Only people invited to the survey count.", [("eNPS_Responses", "Submitted On", "Respondent not active")]),
    (S, "Comments", "Free-text comments repeated a small set of phrases.",
     "Grouped into six themes: Manager, Pay, Growth, Workload, Onboarding, Positive.", "Themes can be counted and compared.",
     [("eNPS_Responses", "Comments (optional)", "")]),
    (S, "Groups", "HR keeps only current details, with no history.",
     "Team, function, grade and location are today's values; tenure is worked out for each survey date.",
     "The closest available picture of each person on the survey date.", [("eNPS_Responses", "(segment attributes)", "")]),
    (R, "Req Raised On", "Some dates typed as text (DD/MM/YYYY).", "Converted to real dates.", "Read day first.",
     [("Requisitions", "Req Raised On", "String dates")]),
    (R, "Thread", "Same spelling problems as the employee list.", "Merged into the same six threads.",
     "Openings and employees use the same team names.", [("Requisitions", "Thread", "Spelling")]),
    (R, "Recruiter", "Short or lowercase names ('Rhea', 'Rhea K', 'rhea kapoor').",
     "Matched to the full names on the Recruiters sheet.", "Each recruiter's work is counted together.",
     [("Requisitions", "Recruiter", "Short")]),
    (R, "Req Status", "Written as 'Closed-Joined', 'Joined', 'OPEN', 'Hold' and so on.",
     "Standardised to Open, Offer Accepted, Closed - Joined, On Hold, Archived.", "Consistent status for open and filled counts.",
     [("Requisitions", "Req Status", "Case")]),
    (R, "Criticality", "Blank on some openings.", "Filled from the rule: Tech G6 and above, or Non-Tech G8 and above.",
     "The rule every other opening follows.", [("Requisitions", "Criticality", "Blank")]),
    (R, "Replaced Employee ID", "Some replaced employees are not in the employee list.", "Exit details left blank.",
     "They left before April 2026, before the employee list starts.", [("Requisitions", "Replaced Employee ID", "Not in")]),
    (R, "Replaced Employee ID", "One replaced employee has no exit date.", "Days from exit to opening left blank.",
     "The gap cannot be measured.", [("Requisitions", "Replaced Employee ID", "Replaced employee in master")]),
    (R, "Req Raised On", "Some replacements were opened before the person's exit date.", "Kept.",
     "Hiring ahead of a known exit is normal.", [("Requisitions", "Req Raised On", "Replacement req")]),
    (R, "SLA Status", "The system says 'Within SLA' on some openings that took longer than their SLA.",
     "Recalculated SLA from the dates and used that everywhere.",
     "No date in the data explains the system's value. Worth checking how the system sets it.",
     [("Requisitions", "SLA Status (System)", "FINDING")]),
    (R, "SLA Status", "Blank on openings On Hold or Archived.", "Left blank.", "There is no SLA clock on those openings.",
     [("Requisitions", "SLA Status (System)", "Blank")]),
    (R, "Filled", "Some candidates accepted an offer and then backed out.",
     "The opening counts as filled only if another candidate accepted or joined.", "A backed-out candidate is not a hire.",
     [("Requisitions", "(derived) is_filled", "Reqs with a backed-out")]),
    (C, "Whole row", "Identical rows appeared more than once.", "Kept one copy.", "Each application is counted once.",
     [("Candidates", "(all columns)", "Exact duplicate")]),
    (C, "Req ID", "Some IDs were missing the 'REQ_' prefix.", "Added it.", "So every application links to its opening.",
     [("Candidates", "Req ID", "Missing")]),
    (C, "Req ID", "Some applications match no opening, even after the fix.", "Left out of this file and all numbers.",
     "They cannot be tied to an opening, and their 'Joined' status has no offer or joining date behind it.",
     [("Candidates", "Req ID", "No matching")]),
    (C, "Source", "Many spellings ('naukri', 'Naukri.com', 'LI', 'Linkedin', 'Website', 'IJP').",
     "Standardised to Naukri, LinkedIn, Employee Referral, Careers Page, Internal (IJP), Agency.",
     "Sources can be compared.", [("Candidates", "Source", "21 spellings")]),
    (C, "Source", "'Vendor' and 'Consultant' entries.", "Counted as Agency.", "Every one of them names an agency.",
     [("Candidates", "Source", "'Vendor'")]),
    (C, "Dates", "Dates in several formats, including Excel serial numbers (e.g. 46209).", "Converted to real dates.",
     "DD/MM/YYYY read day first; serial numbers counted the way Excel does.",
     [("Candidates", None, "Mixed formats")]),
    (C, "Expected CTC", "Some values typed as '5.9 LPA'.", "Converted to rupees.", "Needed to compare offers with expectations.",
     [("Candidates", "Expected CTC (INR)", "'x.x LPA'")]),
    (C, "Notice Period", "Typed as '2 months', '30 days' or 'Immediate'.", "Converted to days (1 month = 30, Immediate = 0).",
     "Notice periods can be compared.", [("Candidates", "Notice Period (Days)", "Text values")]),
    (C, "Candidate Status", "Spelling variants ('Profile Reject', 'R1 Reject', 'joined ').",
     "Standardised to one list of statuses.", "Each outcome is counted once.", [("Candidates", "Candidate Status", "Spelling")]),
    (C, "Shortlisted On", "Shortlist date earlier than the application date.",
     "Kept, but left out of the days-per-stage figures.", "The dates cannot both be right.",
     [("Candidates", "Shortlisted On", "Shortlisted On before")]),
    (C, "R1 Feedback", "Interview held but no feedback date yet.", "Left out of feedback turnaround.",
     "Turnaround cannot be measured until feedback is in.", [("Candidates", "R1 Feedback Submitted On", "R1 interview held")]),
    (C, "Expected DOJ", "Joining dates after 31-Oct-2026.", "Kept.", "These are future joiners, not errors.",
     [("Candidates", "Expected DOJ", "Expected DOJ after")]),
    (C, "Candidate Status", "Accepted offers where the candidate backed out.", "Not counted as hires.",
     "They never joined.", [("Candidates", "Candidate Status", "Accepted offers that backed out")]),
]
# data-changing log rows that need no note of their own (labels and calculations, or covered by a note above)
NO_NOTE = [("Employee_Master", "Manager Effective From", "manager_status: 'New joiner"),
           ("Employee_Master", "Manager Effective From", "manager_status: 'Same manager'"),
           ("Employee_Master", "Manager Effective From", "Literal brief rule"),
           ("Employee_Master", "Date of Exit", "Exited with missing exit date"),
           ("Candidates", "(derived) agency_fee_inr", ""),
           ("Requisitions", "(derived) is_filled", "Refilled reqs")]


def _match(dq: pd.DataFrame, sheet: str, column: str | None, prefix: str) -> pd.Series:
    m = (dq.sheet == sheet) & dq.issue.str.startswith(prefix)
    return m & (dq["column"] == column) if column is not None else m


def cleaning_notes(dq: pd.DataFrame) -> pd.DataFrame:
    changed = (dq.rows_affected > 0) & (dq.treatment != "Validated")
    covered = pd.Series(False, index=dq.index)
    rows = []
    for area, field, found, did, why, keys in NOTES:
        hit = pd.Series(False, index=dq.index)
        for sheet, column, prefix in keys:
            m = _match(dq, sheet, column, prefix)
            assert m.any(), f"no cleaning-log row for note {area} / {field}: {sheet} {column} {prefix!r}"
            hit |= m
        covered |= hit
        rows.append((area, field, found, did, why, int(dq.loc[hit, "rows_affected"].sum())))
    for sheet, column, prefix in NO_NOTE:
        covered |= _match(dq, sheet, column, prefix)
    missing = dq[changed & ~covered]
    assert missing.empty, f"cleaning-log rows with no note: {missing[['sheet', 'column', 'issue']].values.tolist()}"
    return pd.DataFrame(rows, columns=["Data", "Field", "What we found", "What we did", "Why", "Records"])


# ── workbook writing ─────────────────────────────────────────────────────────
def to_cell(v):
    if v is None or (not isinstance(v, (list, dict, str)) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime().date()
    if hasattr(v, "item") and not isinstance(v, str):   # numpy scalar -> python
        return v.item()
    return v


def write_table(ws, df: pd.DataFrame, table: str, notes: dict[str, str] | None = None, start_row: int = 1,
                widths: dict[str, int] | None = None) -> None:
    for j, col in enumerate(df.columns, start=1):
        cell = ws.cell(row=start_row, column=j, value=col)
        cell.font, cell.fill = HEAD_FONT, HEAD_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=bool(widths))
        if notes and notes.get(col):
            cell.comment = Comment(notes[col], "People Sight", width=320, height=110)
    for i, row in enumerate(df.itertuples(index=False), start=start_row + 1):
        for j, v in enumerate(row, start=1):
            c = ws.cell(row=i, column=j, value=to_cell(v))
            if isinstance(c.value, date):
                c.number_format = "dd-mmm-yyyy"
            if widths:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    for j, col in enumerate(df.columns, start=1):
        if widths and col in widths:
            w = widths[col]
        else:
            w = min(max([len(str(col))] + [len(str(x)) for x in df[col].head(300) if x is not None]) + 3, 40)
        ws.column_dimensions[get_column_letter(j)].width = max(w, 10)
    ref = f"A{start_row}:{get_column_letter(len(df.columns))}{start_row + max(len(df), 1)}"
    t = Table(displayName=table, ref=ref)
    t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(t)
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)


NOTE_OVERRIDES = {"recruiter": "Recruiter name", "replaced_in_master": "Replaced employee is in the employee list "
                  "(No = left before 01-Apr-2026)"}
ALL_COLS: list[str] = []   # every exported column, so notes can refer to columns on other sheets


def readable(df: pd.DataFrame, headers: dict[str, tuple[str, str]] | None, comments: dict[str, str] | None):
    """Rename to business-friendly headers and return (frame, header -> note)."""
    names = {c: headers[c][0] if headers and c in headers else title(c) for c in df.columns}
    refs = {**{c: title(c) for c in ALL_COLS}, **names}
    notes = {}
    for c in df.columns:
        if headers and c in headers:
            notes[names[c]] = headers[c][1]
        else:
            notes[names[c]] = NOTE_OVERRIDES.get(c) or tidy_note((comments or {}).get(c, ""), refs)
        assert notes[names[c]], f"no note for column {c}"
    assert len(set(names.values())) == len(names), "duplicate header"
    return df.rename(columns=names), notes


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    survey, headcount = survey_tables(con)
    req = con.execute("SELECT * FROM v_requisitions ORDER BY req_id").df()
    cand = con.execute("SELECT * FROM v_candidates ORDER BY req_id, candidate_id").df()
    rec = con.execute("SELECT * FROM v_recruiters ORDER BY recruiter_id").df()
    comments = {v: dict(con.execute("SELECT column_name, comment FROM duckdb_columns() WHERE table_name = ?", [v]).fetchall())
                for v in ["v_requisitions", "v_candidates", "v_recruiters"]}
    con.close()
    ALL_COLS.extend(list(req.columns) + list(cand.columns) + list(rec.columns))
    notes = cleaning_notes(pd.read_csv(CLEAN_DIR / "dq_log.csv"))

    data_sheets = [
        ("Survey Responses", "Survey_Responses", *readable(survey, SURVEY_HEADERS, None)),
        ("Survey Headcount", "Survey_Headcount", *readable(headcount, HEADCOUNT_HEADERS, None)),
        ("Requisitions", "Requisitions", *readable(req, None, comments["v_requisitions"])),
        ("Candidates", "Candidates", *readable(cand, None, comments["v_candidates"])),
        ("Recruiters", "Recruiters", *readable(rec, None, comments["v_recruiters"])),
    ]

    wb = Workbook()
    wb.remove(wb.active)
    for sheet, table, df, col_notes in data_sheets:
        write_table(wb.create_sheet(sheet), df, table, col_notes)

    ws = wb.create_sheet("How It Was Cleaned")
    ws.sheet_view.showGridLines = False
    ws["A1"] = "How the data was cleaned"
    ws["A1"].font = Font(bold=True, size=16, color=INK)
    ws["A2"] = f"Data as of {AS_OF:%d-%b-%Y} (sample data). Hover over any column header on the other sheets to see what it means."
    ws["A2"].font = Font(italic=True, color="475569")
    for i, line in enumerate(APPROACH, start=4):
        ws.cell(i, 1, line).alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=6)
        ws.row_dimensions[i].height = 15.5 * max(1, -(-len(line) // 150))
    start = 4 + len(APPROACH) + 1
    write_table(ws, notes, "Cleaning_Notes", start_row=start,
                widths={"Data": 18, "Field": 20, "What we found": 46, "What we did": 46, "Why": 46, "Records": 10})
    for r in range(start + 1, start + 1 + len(notes)):
        ws.cell(r, 6).number_format = "#,##0"
        ws.cell(r, 6).alignment = Alignment(vertical="top")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp.xlsx")
    wb.save(tmp)
    tmp.replace(OUT)

    print(f"Wrote {OUT.relative_to(ROOT) if OUT.is_relative_to(ROOT) else OUT}  (built {date.today():%d-%b-%Y})")
    for sheet, _, df, _ in data_sheets:
        print(f"  {sheet:<20} {len(df):>6} rows  {df.shape[1]:>3} columns")
    print(f"  {'How It Was Cleaned':<20} {len(notes):>6} notes")
    print("  survey columns shown: " + ", ".join(f"{c} {(survey[c] != HIDDEN).mean():.0%}" for c in SURVEY_QI))


if __name__ == "__main__":
    main()
