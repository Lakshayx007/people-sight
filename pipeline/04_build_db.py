"""
04_build_db.py
--------------
Build data/people.duckdb from data/clean/*.parquet + dq_log.csv + reconciliation.csv.

Base tables (t_*) hold the cleaned data; the app and Ask the Data read ONLY the v_* views.
Every view column carries a COMMENT (used for the Ask-the-Data schema prompt).

Survey anonymity: neither t_survey nor v_survey stores an Employee ID or name. Each respondent gets a
pseudonymous respondent_key (stable across waves, so the panel works); the flags needed for cross-dataset
analysis (is_interviewer, is_hiring_manager, exit outcome) are attached here, before the ID is dropped.

Run:  python pipeline/04_build_db.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CLEAN_DIR, ROOT, WAVES  # noqa: E402

DB = ROOT / "data" / "people.duckdb"
KEY_SALT = "porter-people-analytics-2026"
FY_START = pd.Timestamp("2026-04-01")

# ── load cleaned data ────────────────────────────────────────────────────────
emp = pd.read_parquet(CLEAN_DIR / "employees.parquet")
resp = pd.read_parquet(CLEAN_DIR / "survey_responses.parquet")
req = pd.read_parquet(CLEAN_DIR / "requisitions.parquet")
cand = pd.read_parquet(CLEAN_DIR / "candidates.parquet")
rec = pd.read_parquet(CLEAN_DIR / "recruiters.parquet")
pdir = pd.read_parquet(CLEAN_DIR / "people_directory.parquet")
bands = pd.read_parquet(CLEAN_DIR / "pay_bands.parquet")
dq = pd.read_csv(CLEAN_DIR / "dq_log.csv")
recon = pd.read_csv(CLEAN_DIR / "reconciliation.csv")

interviewers = set(pdir.loc[pdir.is_interviewer, "employee_id"])
managers = set(pdir.loc[pdir.is_hiring_manager, "employee_id"])
emp_i = emp.set_index("employee_id")


def rkey(eid: str) -> str:
    return "R" + hashlib.sha256((KEY_SALT + eid).encode()).hexdigest()[:10]


# Every attribute the survey can be sliced by. v_survey and v_invited carry ALL of these with identical names,
# so one filter fragment works on numerator and denominator.
SLICE_COLS = ["company", "thread", "function", "job_family", "grade", "grade_num", "location", "location_type",
              "tenure_band", "performance_rating", "compa_band", "manager_status", "joined_between_waves", "joined_this_fy",
              "is_interviewer", "is_hiring_manager", "invited_both_waves", "responded_both_waves", "exited_after_wave",
              "exit_type_after_wave", "regrettable_after_wave"]

# ── survey (valid responses only, no ID, no name) ────────────────────────────
s = resp[resp.is_valid].copy()
s["respondent_key"] = s.employee_id.map(rkey)
s["is_interviewer"] = s.employee_id.isin(interviewers)
s["is_hiring_manager"] = s.employee_id.isin(managers)
s["joined_this_fy"] = s.employee_id.map(emp_i.date_of_joining) >= FY_START
s["submitted_date"] = s.submitted_on.dt.normalize()
both_inv = set(emp.loc[emp.active_on_apr_open & emp.active_on_oct_open, "employee_id"])
s["invited_both_waves"] = s.employee_id.isin(both_inv)
s["responded_both_waves"] = s.in_panel
s["exit_type_after_wave"] = s.exit_type.where(s.exited_after_wave).astype(object).where(lambda x: x.notna(), None)
s["regrettable_after_wave"] = s.exited_after_wave & s.is_regrettable_exit.astype("boolean").fillna(False).astype(bool)
s["q1"] = s.q1_clean.astype(int)
for g, col in [("Promoter", "is_promoter"), ("Passive", "is_passive"), ("Detractor", "is_detractor")]:
    s[col] = (s.nps_group == g).astype(int)
SURVEY_COLS = ["wave", "respondent_key", "submitted_date", "q1", "nps_group", "is_promoter", "is_passive", "is_detractor",
               "q2", "q3", "q4", "q5", "q6", "comment", "comment_theme"] + SLICE_COLS
t_survey = s[SURVEY_COLS].reset_index(drop=True)
assert not any(c in t_survey.columns for c in ("employee_id", "employee_name", "response_id"))

# ── invited population (one row per employee per wave, no ID) ────────────────
responded = set(zip(s.employee_id, s.wave))
rows = []
for w in WAVES:
    k = w.lower()
    sub = emp[emp[f"active_on_{k}_open"]].copy()
    sub["wave"] = w
    sub["tenure_band"] = sub[f"tenure_band_{k}"]
    sub["responded"] = [(i, w) in responded for i in sub.employee_id]
    rows.append(sub)
inv = pd.concat(rows, ignore_index=True)
inv["is_interviewer"] = inv.employee_id.isin(interviewers)
inv["is_hiring_manager"] = inv.employee_id.isin(managers)
inv["joined_this_fy"] = inv.date_of_joining >= FY_START
inv["invited_both_waves"] = inv.employee_id.isin(both_inv)
both_resp = set(s.loc[s.responded_both_waves, "employee_id"])
inv["responded_both_waves"] = inv.employee_id.isin(both_resp)
close = inv.wave.map(lambda w: WAVES[w]["close"])
inv["exited_after_wave"] = (inv.date_of_exit.notna() & (inv.date_of_exit > close)) | (inv.exit_date_unknown & (inv.wave == "Apr"))
inv["exit_type_after_wave"] = inv.exit_type.where(inv.exited_after_wave).astype(object).where(lambda x: x.notna(), None)
inv["regrettable_after_wave"] = inv.exited_after_wave & inv.is_regrettable_exit.astype("boolean").fillna(False).astype(bool)
INVITED_COLS = ["wave"] + SLICE_COLS + ["responded"]
t_invited = inv[INVITED_COLS].reset_index(drop=True)
assert int(t_invited.responded.sum()) == len(t_survey)
# survey rows must carry the same slice values as the matching invited row
_chk = s.merge(inv[["employee_id", "wave"] + SLICE_COLS], on=["employee_id", "wave"], suffixes=("", "_inv"))
assert len(_chk) == len(s)
for _c in SLICE_COLS:
    a, b = _chk[_c], _chk[_c + "_inv"]
    assert ((a == b) | (a.isna() & b.isna())).all(), _c

# ── employees (no name) ──────────────────────────────────────────────────────
t_employees = emp.drop(columns=["employee_name", "annual_ctc_raw"])
t_employees["is_interviewer"] = t_employees.employee_id.isin(interviewers)
t_employees["is_hiring_manager"] = t_employees.employee_id.isin(managers)

# ── build ────────────────────────────────────────────────────────────────────
DB.parent.mkdir(parents=True, exist_ok=True)
tmp = DB.with_suffix(".tmp.duckdb")
if tmp.exists():
    tmp.unlink()
con = duckdb.connect(str(tmp))
for name, df in [("t_survey", t_survey), ("t_invited", t_invited), ("t_employees", t_employees), ("t_requisitions", req),
                 ("t_candidates", cand), ("t_recruiters", rec), ("t_people_directory", pdir), ("t_pay_bands", bands),
                 ("t_dq_log", dq), ("t_reconciliation", recon)]:
    con.register("df_view", df)
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM df_view")
    con.unregister("df_view")

VIEWS = {
"v_survey": ("""
    SELECT wave, respondent_key, CAST(submitted_date AS DATE) AS submitted_date, q1, nps_group, is_promoter, is_passive,
           is_detractor, q2, q3, q4, q5, q6, comment, comment_theme, """ + ", ".join(SLICE_COLS) + """
    FROM t_survey""",
    "Valid eNPS survey responses (one per respondent per wave). Anonymous: no Employee ID or name, so it cannot be "
    "joined to HRMS or hiring data; every slicing attribute is precomputed on the row. tenure_band is at the wave open "
    "date; manager_status is a cohort label (same in both waves); other attributes are the current HRMS values."),
"v_invited": ("SELECT * FROM t_invited",
    "Invited population: one row per employee active on a wave's open date (the response-rate denominator). "
    "Same segment column names as v_survey so the same filters apply. No ID or name."),
"v_employees": ("""
    SELECT employee_id, company, thread, function, job_family, designation, grade, grade_num, location, location_type,
           CAST(date_of_joining AS DATE) AS date_of_joining, reporting_manager_id,
           CAST(manager_effective_from AS DATE) AS manager_effective_from, manager_status, manager_changed_literal,
           joined_between_waves, performance_rating, annual_ctc, ctc_flag, band_mid, compa_ratio, compa_band,
           employment_status, is_exited, CAST(date_of_exit AS DATE) AS date_of_exit, exit_date_unknown, exit_month,
           exit_type, exit_classification, is_regrettable_exit, tenure_days, tenure_band_asof,
           active_on_apr_open, active_on_oct_open, tenure_band_apr, tenure_band_oct, is_interviewer, is_hiring_manager
    FROM t_employees""",
    "One row per employee on the rolls 01-Apr-2026..31-Oct-2026 (cleaned HRMS). No names. Not linkable to survey answers."),
"v_requisitions": ("""
    SELECT req_id, CAST(req_raised_on AS DATE) AS req_raised_on, raised_month, thread, function, job_family, designation,
           grade, grade_num, location, position_type, replaced_employee_id, replaced_in_master,
           CAST(replaced_exit_date AS DATE) AS replaced_exit_date, replaced_exit_type, replaced_exit_classification,
           replaced_is_regrettable, days_exit_to_req, criticality, criticality_derived, criticality_mismatch,
           hiring_manager_id, recruiter, recruiter_id, sla_days, sla_expected, sla_mismatch, req_status, budgeted_max_ctc,
           hired_candidate_id, hire_status, hire_source, CAST(offer_accepted_on AS DATE) AS offer_accepted_on,
           CAST(hire_actual_doj AS DATE) AS hire_actual_doj, ttf_days, is_filled, sla_met, age_days_as_of_31oct,
           is_open, open_breached, sla_status_system, sla_status_recomputed, sla_status_mismatch, had_backout
    FROM t_requisitions""",
    "One row per requisition raised 01-Apr-2026..15-Oct-2026 with hire, TTF and SLA fields (recomputed SLA is authoritative)."),
"v_candidates": ("""
    SELECT c.candidate_id, c.req_id, c.source_clean AS source, c.agency_name,
           CAST(c.applied_on AS DATE) AS applied_on, CAST(c.shortlisted_on AS DATE) AS shortlisted_on,
           CAST(c.screening_done_on AS DATE) AS screening_done_on, CAST(c.r1_interview_date AS DATE) AS r1_interview_date,
           CAST(c.r1_feedback_submitted_on AS DATE) AS r1_feedback_submitted_on, CAST(c.r2_interview_date AS DATE) AS r2_interview_date,
           CAST(c.offer_released_on AS DATE) AS offer_released_on, CAST(c.offer_response_on AS DATE) AS offer_response_on,
           CAST(c.expected_doj AS DATE) AS expected_doj, CAST(c.actual_doj AS DATE) AS actual_doj,
           c.r1_interviewer_id, c.r1_result, c.r2_result, c.offered_ctc, c.current_ctc, c.expected_ctc_num AS expected_ctc,
           c.notice_days, c.offer_status, c.candidate_status, c.stage_reached,
           c.reached_applied, c.reached_shortlisted, c.reached_screening_done, c.reached_r1_interview, c.reached_r1_select,
           c.reached_r2_interview, c.reached_offer_released, c.reached_offer_accepted, c.reached_joined, c.stage_dates_invalid,
           c.days_applied_to_shortlisted, c.days_shortlisted_to_screening, c.days_screening_to_r1, c.days_r1_to_r2,
           c.days_r2_to_offer, c.days_offer_to_response, c.days_response_to_join, c.r1_feedback_days,
           c.is_offer_accepted, c.is_offer_declined, c.is_backed_out, c.is_joined, c.joining_due,
           c.offer_to_expected_ratio, c.offer_to_budget_ratio, c.is_hire, c.agency_fee_inr,
           r.thread, r.function, r.job_family, r.grade, r.grade_num, r.location, r.position_type, r.criticality,
           r.req_status, r.recruiter, r.raised_month, r.sla_days, r.ttf_days AS req_ttf_days, r.sla_met AS req_sla_met
    FROM t_candidates c JOIN t_requisitions r USING (req_id)""",
    "One row per candidate application (36 orphans with no requisition excluded), with the requisition's attributes "
    "so the same hiring filters apply."),
"v_recruiters": ("SELECT recruiter_id, recruiter_name AS recruiter, monthly_offer_target, status FROM t_recruiters",
    "TA recruiters and their monthly accepted-offer targets."),
"v_interviewers": ("""
    SELECT employee_id, employee_name, thread, function, designation, grade, location, hiring_role, is_interviewer,
           is_hiring_manager
    FROM t_people_directory""",
    "People_Directory: employees who interview and/or act as hiring managers (lookup for R1 Interviewer ID and "
    "Hiring Manager ID). The only view with names; it has no survey data."),
"v_dq_log": ("SELECT * FROM t_dq_log", "Every data-cleaning rule applied by the pipeline, with rows affected and assumptions."),
"v_reconciliation": ("SELECT * FROM t_reconciliation", "Row counts in -> each exclusion -> rows out, per sheet."),
}

COMMENTS = {
# shared segment columns
"wave": "Survey wave: 'Apr' (open 06-Apr-2026) or 'Oct' (open 05-Oct-2026)",
"company": "Legal entity: 'Porter' or 'SmartShift Info Marketing Services Pvt Ltd'",
"thread": "Business unit: Intracity, Intercity, Enterprise, Packers & Movers, Geo Expansion, Central",
"function": "Type of work, e.g. Operations, Sales, Engineering, Customer Support",
"job_family": "'Tech' (Engineering, Product, Data & Analytics, Design & Research) or 'Non-Tech'",
"grade": "Grade TBA (trainee), G1 (junior) .. G10 (senior)",
"grade_num": "Grade as a number: TBA = 0, G1 = 1 .. G10 = 10 (use for ordering / ranges)",
"location": "Work location; 'Bengaluru HO' is head office, 'Bengaluru' is the city office",
"location_type": "'HO' (Bengaluru HO) or 'City'",
"tenure_band": "Tenure at the wave open date: <6m, 6-12m, 1-2y, 2-4y, 4y+",
"performance_rating": "FY25-26 rating: Game Changer, High Impact Player, Solid Performer, Needs Improvement, Below Expectations, Not Rated - New Joiner",
"compa_band": "Annual CTC / band mid (2026-04-01 bands): 'Below' (<0.90), 'At' (0.90-1.10), 'Above' (>1.10), 'Unknown' (no CTC)",
"manager_status": "'Changed manager' (current manager effective 18-Apr..04-Oct-2026, after joining), 'New joiner (first manager)' (effective date = joining date in that window), 'Same manager'",
"joined_between_waves": "Joined after the April wave opened and on/before 05-Oct-2026",
"joined_this_fy": "Date of joining on/after 01-Apr-2026",
"is_interviewer": "Employee is an R1 interviewer in People_Directory",
"is_hiring_manager": "Employee is a hiring manager in People_Directory",
"is_exited": "Employment status Exited as of 31-Oct-2026",
"exit_type": "Voluntary or Involuntary (exited employees only)",
"exit_classification": "Regrettable or Non-Regrettable (exited employees only, HRBP tag)",
"is_regrettable_exit": "Exited and tagged Regrettable",
# survey
"respondent_key": "Anonymous respondent key (same person = same key in both waves). Not linkable to Employee ID",
"submitted_date": "Date the response was submitted",
"q1": "Q1 likelihood to recommend Porter as a place to work, 0-10 (eNPS question)",
"nps_group": "Promoter (Q1 9-10), Passive (7-8), Detractor (0-6)",
"is_promoter": "1 if Q1 is 9-10 else 0. eNPS = 100 * (avg(is_promoter) - avg(is_detractor))",
"is_passive": "1 if Q1 is 7-8 else 0",
"is_detractor": "1 if Q1 is 0-6 else 0",
"q2": "Q2 'My manager gives me regular, useful feedback' 1-5 (blank = not answered). Favourable = 4-5",
"q3": "Q3 'I am paid fairly for the work I do' 1-5. Favourable = 4-5",
"q4": "Q4 'My workload is manageable' 1-5. Favourable = 4-5",
"q5": "Q5 'I had the onboarding, tools and training I needed' 1-5. Favourable = 4-5",
"q6": "Q6 'I can see a clear growth path for myself at Porter' 1-5. Favourable = 4-5",
"comment": "Optional free-text comment (blank if none)",
"comment_theme": "Comment theme: Manager, Pay, Growth, Workload, Onboarding, Positive (blank if no comment)",
"invited_both_waves": "Employee was active on both wave open dates (invited to April and October)",
"responded_both_waves": "Employee gave a valid response in BOTH waves (panel)",
"exited_after_wave": "Employee exited after this wave closed and by 31-Oct-2026",
"exit_type_after_wave": "Voluntary / Involuntary if exited after this wave, else blank",
"regrettable_after_wave": "Exited after this wave and tagged Regrettable",
"responded": "Invited employee gave a valid response in this wave",
# employees
"employee_id": "Employee ID (EMP + 5 digits)",
"designation": "Job title",
"date_of_joining": "Date of joining",
"reporting_manager_id": "Employee ID of the current reporting manager",
"manager_effective_from": "Date the employee started reporting to the current manager",
"manager_changed_literal": "Backup only (not for charts): current manager effective 18-Apr..04-Oct-2026, any joining date",
"annual_ctc": "Annual fixed CTC in INR (7 monthly values x12, see ctc_flag)",
"ctc_flag": "'ok', 'missing', 'corrected_monthly_x12', 'out_of_band'",
"band_mid": "Pay band midpoint (INR) for the employee's job family and grade, 2026-04-01 band set",
"compa_ratio": "annual_ctc / band_mid",
"employment_status": "Active or Exited as of 31-Oct-2026",
"date_of_exit": "Last working day (blank if active or exit date unknown)",
"exit_date_unknown": "Exited but no exit date recorded (treated as exited before the October wave)",
"exit_month": "Exit month YYYY-MM",
"tenure_days": "Days from joining to exit or 31-Oct-2026",
"tenure_band_asof": "Tenure band as of 31-Oct-2026",
"active_on_apr_open": "Active on 06-Apr-2026 (invited to the April wave)",
"active_on_oct_open": "Active on 05-Oct-2026 (invited to the October wave)",
"tenure_band_apr": "Tenure band on 06-Apr-2026",
"tenure_band_oct": "Tenure band on 05-Oct-2026",
# requisitions
"req_id": "Requisition ID (REQ_ + number)",
"req_raised_on": "Date the requisition was approved and opened",
"raised_month": "Month the requisition was raised, YYYY-MM",
"position_type": "'New' (additional headcount) or 'Replacement' (backfill)",
"replaced_employee_id": "Employee being backfilled (Replacement only)",
"replaced_in_master": "Replaced employee found in Employee_Master (false = left before 01-Apr-2026)",
"replaced_exit_date": "Exit date of the replaced employee",
"replaced_exit_type": "Exit type of the replaced employee",
"replaced_exit_classification": "Regrettable / Non-Regrettable tag of the replaced employee",
"replaced_is_regrettable": "Replaced employee was a regrettable exit",
"days_exit_to_req": "Days from the replaced employee's exit to the req being raised (negative = raised before exit)",
"criticality": "'Critical' (Tech G6+ or Non-Tech G8+) or 'Non-Critical'; blanks filled from the rule",
"criticality_derived": "Criticality from the rule",
"criticality_mismatch": "Recorded criticality differs from the rule",
"hiring_manager_id": "Employee ID of the hiring manager (see v_interviewers)",
"recruiter": "TA recruiter who owns the requisition (Recruiters sheet name)",
"recruiter_id": "Recruiter ID (TA01..TA08)",
"sla_days": "Time-to-fill target: 30 (TBA-G2), 45 (G3-G5), 60 (G6+)",
"sla_expected": "SLA days from the grade rule",
"sla_mismatch": "Recorded SLA days differ from the grade rule",
"req_status": "Open, Offer Accepted (hire yet to join), Closed - Joined, On Hold, Archived (cancelled)",
"budgeted_max_ctc": "Maximum annual CTC approved for the role (INR)",
"hired_candidate_id": "Candidate who filled the req (accepted, not backed out)",
"hire_status": "'Joined' or 'Yet to Join' (blank if not filled)",
"hire_source": "Source of the hired candidate",
"offer_accepted_on": "Date the hired candidate accepted (Offer Response On)",
"hire_actual_doj": "Hired candidate's actual joining date",
"ttf_days": "Time to fill in days = offer_accepted_on - req_raised_on (filled reqs only)",
"is_filled": "Req has a hired candidate (joined or yet to join)",
"sla_met": "ttf_days <= sla_days (filled reqs only)",
"age_days_as_of_31oct": "Days from req_raised_on to 31-Oct-2026",
"is_open": "req_status = 'Open'",
"open_breached": "Open req with age_days_as_of_31oct > sla_days",
"sla_status_system": "SLA status as computed by the ATS (kept for comparison only)",
"sla_status_recomputed": "Authoritative SLA status: Within SLA / Breached (filled), Open - Within SLA / Open - Breached (open); blank for On Hold / Archived",
"sla_status_mismatch": "System SLA status differs from the recomputed status",
"had_backout": "A candidate on this req accepted and then backed out",
# candidates
"candidate_id": "Candidate application ID",
"source": "Sourcing channel: Naukri, LinkedIn, Employee Referral, Careers Page, Internal (IJP), Agency",
"agency_name": "Agency name (agency-sourced only)",
"applied_on": "Date applied", "shortlisted_on": "Date shortlisted", "screening_done_on": "Date screening completed",
"r1_interview_date": "Round 1 interview date", "r1_feedback_submitted_on": "Date the R1 interviewer submitted feedback",
"r2_interview_date": "Round 2 interview date", "offer_released_on": "Offer date", "offer_response_on": "Date the candidate accepted/declined",
"expected_doj": "Planned joining date (may be after 31-Oct-2026)", "actual_doj": "Actual joining date",
"r1_interviewer_id": "Employee ID of the R1 interviewer (see v_interviewers)",
"r1_result": "Select, Reject or Pending Feedback", "r2_result": "Select or Reject",
"offered_ctc": "Annual CTC offered (INR)", "current_ctc": "Candidate's current annual CTC (INR)",
"expected_ctc": "Candidate's expected annual CTC (INR)", "notice_days": "Notice period in days (1 month = 30)",
"offer_status": "Accepted or Declined (blank if no offer)",
"candidate_status": "Current status, e.g. Rejected - Profile, Joined, Offer Declined, Not Joined - Backed Out",
"stage_reached": "Furthest funnel stage: Applied, Shortlisted, Screening Done, R1 Interview, R1 Select, R2 Interview, Offer Released, Offer Accepted, Joined",
"reached_applied": "Reached Applied", "reached_shortlisted": "Reached Shortlisted", "reached_screening_done": "Reached Screening Done",
"reached_r1_interview": "Reached R1 Interview", "reached_r1_select": "R1 result Select", "reached_r2_interview": "Reached R2 Interview",
"reached_offer_released": "Offer released", "reached_offer_accepted": "Offer accepted (incl. later backed out)", "reached_joined": "Joined",
"stage_dates_invalid": "Shortlisted before Applied: excluded from stage-time metrics",
"days_applied_to_shortlisted": "Days Applied -> Shortlisted (blank if missing / invalid order)",
"days_shortlisted_to_screening": "Days Shortlisted -> Screening Done",
"days_screening_to_r1": "Days Screening Done -> R1 Interview",
"days_r1_to_r2": "Days R1 Interview -> R2 Interview",
"days_r2_to_offer": "Days R2 Interview -> Offer Released",
"days_offer_to_response": "Days Offer Released -> Offer Response",
"days_response_to_join": "Days Offer Response -> Actual DOJ",
"r1_feedback_days": "R1 feedback turnaround = r1_feedback_submitted_on - r1_interview_date (days)",
"is_offer_accepted": "Offer accepted (includes candidates who later backed out)",
"is_offer_declined": "Offer declined",
"is_backed_out": "Accepted, then did not join",
"is_joined": "Candidate joined",
"joining_due": "Accepted offer with expected_doj <= 31-Oct-2026 (joining-rate denominator)",
"offer_to_expected_ratio": "offered_ctc / expected_ctc",
"offer_to_budget_ratio": "offered_ctc / requisition budgeted_max_ctc",
"is_hire": "This candidate is the req's hired candidate",
"agency_fee_inr": "8.33% x offered_ctc for agency-sourced candidates who joined, else 0",
"req_ttf_days": "Time to fill of the candidate's requisition",
"req_sla_met": "The candidate's requisition was filled within SLA (filled reqs only)",
# recruiters / interviewers
"monthly_offer_target": "Accepted offers expected per recruiter per month",
"status": "Recruiter status",
"employee_name": "Interviewer / hiring manager name",
"hiring_role": "'Interviewer', 'Hiring Manager' or 'Interviewer & Hiring Manager'",
# dq / reconciliation
"dataset": "eNPS or Recruitment", "sheet": "Source sheet", "column": "Source column", "issue": "Data-quality issue found",
"rows_affected": "Rows affected (0 = check passed)", "treatment": "What the pipeline did", "assumption": "Assumption behind the treatment",
"step": "Pipeline step", "order": "Step order within the sheet", "rows": "Rows after the step", "change": "Change in rows vs previous step",
"note": "Note",
}

for v, (sql, desc) in VIEWS.items():
    con.execute(f"CREATE VIEW {v} AS {sql}")
    con.execute(f"COMMENT ON VIEW {v} IS '{desc.replace(chr(39), chr(39) * 2)}'")
    cols = [r[0] for r in con.execute(f"DESCRIBE {v}").fetchall()]
    missing = [c for c in cols if c not in COMMENTS]
    assert not missing, f"{v}: no comment for {missing}"
    for c in cols:
        con.execute(f'COMMENT ON COLUMN {v}."{c}" IS \'{COMMENTS[c].replace(chr(39), chr(39) * 2)}\'')

summary = con.execute("""
    SELECT view_name, (SELECT count(*) FROM duckdb_columns() c WHERE c.table_name = v.view_name) AS n_cols
    FROM duckdb_views() v WHERE NOT internal AND view_name LIKE 'v\\_%' ESCAPE '\\' ORDER BY view_name""").fetchall()
counts = {v: con.execute(f"SELECT count(*) FROM {v}").fetchone()[0] for v, _ in summary}
con.close()
tmp.replace(DB)
print(f"Built {DB.relative_to(ROOT)}")
for v, n in summary:
    print(f"  {v:<17} {counts[v]:>6} rows  {n:>3} columns (all commented)")
