"""
03_clean_recruitment.py
-----------------------
Clean the recruitment workbook (Requisitions, Candidates, Recruiters, People_Directory) and
derive the hiring fields. Needs data/clean/employees.parquet from 02_clean_enps.py
(replaced-employee exit details).

Outputs (data/clean/): requisitions.parquet, candidates.parquet, recruiters.parquet,
people_directory.parquet, candidates_excluded.parquet (orphan rows, for traceability).
Every rule -> dq_log.csv; row counts -> reconciliation.csv.
Run:  python pipeline/03_clean_recruitment.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    AS_OF, CLEAN_DIR, EMP_ID_RE, RECRUIT_FILE, REQ_ID_RE, THREADS, DQLog, date_format_of, grade_num,
    is_blank, job_family, norm_emp_id, norm_grade, norm_req_id, parse_date, parse_inr, thread_clean,
)

DS = "Recruitment"
RQ, CD, RC, PD_ = "Requisitions", "Candidates", "Recruiters", "People_Directory"
dq = DQLog(DS)
AGENCY_FEE_RATE = 0.0833

REQ_STATUS = {"open": "Open", "offer accepted": "Offer Accepted", "closed - joined": "Closed - Joined",
              "closed-joined": "Closed - Joined", "joined": "Closed - Joined", "on hold": "On Hold",
              "hold": "On Hold", "archived": "Archived"}
SOURCE = {"naukri": "Naukri", "naukri.com": "Naukri", "linkedin": "LinkedIn", "li": "LinkedIn",
          "employee referral": "Employee Referral", "referral": "Employee Referral", "emp referral": "Employee Referral",
          "careers page": "Careers Page", "career page": "Careers Page", "website": "Careers Page",
          "internal (ijp)": "Internal (IJP)", "ijp": "Internal (IJP)", "internal": "Internal (IJP)",
          "agency": "Agency", "vendor": "Agency", "consultant": "Agency"}
SOURCES = ["Naukri", "LinkedIn", "Employee Referral", "Careers Page", "Internal (IJP)", "Agency"]
CAND_STATUS = ["Applied - Under Review", "Shortlisted", "Screening Cleared", "R1 Cleared", "R1 Feedback Pending",
               "Offer In Approval", "Offer Accepted - Yet to Join", "Joined", "Offer Declined",
               "Not Joined - Backed Out", "Rejected - Profile", "Rejected - Screening", "Rejected - R1",
               "Rejected - R2", "On Hold - Position Filled", "Withdrawn"]
_CS_KEY = {s.lower(): s for s in CAND_STATUS} | {"rejected-profile": "Rejected - Profile", "profile reject": "Rejected - Profile",
                                                 "r1 reject": "Rejected - R1", "declined": "Offer Declined"}
STAGES = ["Applied", "Shortlisted", "Screening Done", "R1 Interview", "R1 Select", "R2 Interview",
          "Offer Released", "Offer Accepted", "Joined"]
DATE_COLS = {"Applied On": "applied_on", "Shortlisted On": "shortlisted_on", "Screening Done On": "screening_done_on",
             "R1 Interview Date": "r1_interview_date", "R1 Feedback Submitted On": "r1_feedback_submitted_on",
             "R2 Interview Date": "r2_interview_date", "Offer Released On": "offer_released_on",
             "Offer Response On": "offer_response_on", "Expected DOJ": "expected_doj", "Actual DOJ": "actual_doj"}
# consecutive dated stages used for stage time (R1 Select has no date of its own)
TRANSITIONS = [("applied_on", "shortlisted_on", "days_applied_to_shortlisted"),
               ("shortlisted_on", "screening_done_on", "days_shortlisted_to_screening"),
               ("screening_done_on", "r1_interview_date", "days_screening_to_r1"),
               ("r1_interview_date", "r2_interview_date", "days_r1_to_r2"),
               ("r2_interview_date", "offer_released_on", "days_r2_to_offer"),
               ("offer_released_on", "offer_response_on", "days_offer_to_response"),
               ("offer_response_on", "actual_doj", "days_response_to_join")]


def changed(before: pd.Series, after: pd.Series) -> int:
    return int((before.astype(str) != after.astype(str)).sum())


def sla_rule(gnum):
    return np.where(gnum <= 2, 30, np.where(gnum <= 5, 45, 60))


def crit_rule(fam: pd.Series, gnum: pd.Series):
    return np.where(((fam == "Tech") & (gnum >= 6)) | ((fam == "Non-Tech") & (gnum >= 8)), "Critical", "Non-Critical")


# ═════════════════════════════════════════════════════════════════════════════
# Recruiters
# ═════════════════════════════════════════════════════════════════════════════
rc_raw = pd.read_excel(RECRUIT_FILE, RC, dtype=object)
dq.step(RC, "rows in (raw)", len(rc_raw))
rc = pd.DataFrame({"recruiter_id": rc_raw["Recruiter ID"].str.strip(), "recruiter_name": rc_raw["Recruiter Name"].str.strip(),
                   "monthly_offer_target": rc_raw["Monthly Offer Target"].astype(int), "status": rc_raw["Status"].str.strip()})
dq.log(RC, "(all)", "Recruiter list checked (unique IDs and names)", int(rc.recruiter_id.duplicated().sum() + rc.recruiter_name.duplicated().sum()), "Validated")
dq.step(RC, "rows out", len(rc))


def recruiter_match(v):
    """Map 'Rhea', 'Rhea K', 'rhea kapoor', 'Divya M' ... to a unique Recruiters-sheet name."""
    toks = str(v).strip().lower().replace(".", "").split()
    hits = []
    for name in rc.recruiter_name:
        first, last = name.lower().split(maxsplit=1)
        if toks and toks[0] == first and (len(toks) == 1 or last.startswith(toks[1])):
            hits.append(name)
    return hits[0] if len(hits) == 1 else None


# ═════════════════════════════════════════════════════════════════════════════
# People_Directory
# ═════════════════════════════════════════════════════════════════════════════
pd_raw = pd.read_excel(RECRUIT_FILE, PD_, dtype=object)
dq.step(PD_, "rows in (raw)", len(pd_raw))
emp = pd.read_parquet(CLEAN_DIR / "employees.parquet").set_index("employee_id")
pdir = pd.DataFrame({
    "employee_id": pd_raw["Employee ID"].map(norm_emp_id), "employee_name": pd_raw["Employee Name"].str.strip(),
    "thread": pd_raw["Thread"].map(thread_clean), "function": pd_raw["Function"].str.strip(),
    "designation": pd_raw["Designation"].str.strip(), "grade": pd_raw["Grade"].map(norm_grade),
    "location": pd_raw["Location"].str.strip(), "hiring_role": pd_raw["Hiring Role"].str.strip()})
pdir["is_interviewer"] = pdir.hiring_role.str.contains("Interviewer")
pdir["is_hiring_manager"] = pdir.hiring_role.str.contains("Hiring Manager")
nf = int((~pdir.employee_id.isin(emp.index)).sum())
dq.log(PD_, "Employee ID", "Directory ID not in Employee_Master", nf, "Validated" if nf == 0 else "Flagged")
dq.log(PD_, "Thread / Grade / Location", "Canonical values check", int(pdir[["thread", "grade"]].isna().any(axis=1).sum()), "Validated")
dq.step(PD_, "rows out", len(pdir))

# ═════════════════════════════════════════════════════════════════════════════
# Requisitions
# ═════════════════════════════════════════════════════════════════════════════
rq_raw = pd.read_excel(RECRUIT_FILE, RQ, dtype=object)
dq.step(RQ, "rows in (raw)", len(rq_raw))
q = pd.DataFrame({"req_id": rq_raw["Req ID"].map(norm_req_id)})
bad = int((~q.req_id.map(lambda v: bool(REQ_ID_RE.fullmatch(v)))).sum()) + int(q.req_id.duplicated().sum())
dq.log(RQ, "Req ID", "Format REQ_ + number and uniqueness", bad, "Validated")

fmt = rq_raw["Req Raised On"].map(date_format_of)
q["req_raised_on"] = rq_raw["Req Raised On"].map(parse_date)
dq.log(RQ, "Req Raised On", "String dates (DD/MM/YYYY)", int((fmt != "datetime").sum()), "Parsed to date", "DD/MM/YYYY strings are day-first (Indian format)")
outside = int(((q.req_raised_on < "2026-04-01") | (q.req_raised_on > "2026-10-15")).sum())
dq.log(RQ, "Req Raised On", "Outside 01-Apr-2026..15-Oct-2026 (README scope)", outside, "Validated")
q["raised_month"] = q.req_raised_on.dt.strftime("%Y-%m")

q["thread"] = rq_raw["Thread"].map(thread_clean)
dq.log(RQ, "Thread", "Spelling variants / trailing spaces (Inter City, Intra City, P&M, Geo-Expansion, central, ...)",
       changed(rq_raw["Thread"], q["thread"]), f"Mapped to 6 canonical threads: {', '.join(THREADS)}")
for raw_c, c in [("Function", "function"), ("Designation", "designation"), ("Location", "location"), ("Position Type", "position_type")]:
    q[c] = rq_raw[raw_c].str.strip()
q["grade"] = rq_raw["Grade"].map(norm_grade)
q["grade_num"] = q.grade.map(grade_num).astype(int)
q["job_family"] = q.function.map(job_family)
dq.log(RQ, "Function / Location / Grade / Position Type", "Canonical values check", int(q[["grade", "thread"]].isna().any(axis=1).sum()), "Validated")

q["recruiter"] = rq_raw["Recruiter"].map(recruiter_match)
nm = int(q.recruiter.isna().sum())
dq.log(RQ, "Recruiter", f"Short / case variants ({', '.join(sorted(set(rq_raw['Recruiter']) - set(rc.recruiter_name)))})",
       int((~rq_raw["Recruiter"].isin(rc.recruiter_name)).sum()), "Mapped to the Recruiters sheet name (first name + optional last-name initial, unique match)")
dq.log(RQ, "Recruiter", "No unique match to the Recruiters sheet", nm, "Validated" if nm == 0 else "Left blank")
q = q.merge(rc[["recruiter_name", "recruiter_id"]], left_on="recruiter", right_on="recruiter_name", how="left").drop(columns="recruiter_name")

q["req_status"] = rq_raw["Req Status"].str.strip().str.lower().map(REQ_STATUS)
dq.log(RQ, "Req Status", "Case / spelling variants (Closed-Joined, closed - joined, Joined, Offer accepted, OPEN, open, Hold)",
       changed(rq_raw["Req Status"], q["req_status"]), "Mapped to Open / Offer Accepted / Closed - Joined / On Hold / Archived", "'Joined' = Closed - Joined")

q["criticality_raw"] = rq_raw["Criticality"].map(lambda v: None if is_blank(v) else str(v).strip())
q["criticality_derived"] = crit_rule(q.job_family, q.grade_num)
q["criticality_mismatch"] = q.criticality_raw.notna() & (q.criticality_raw != q.criticality_derived)
q["criticality"] = q.criticality_raw.fillna(pd.Series(q.criticality_derived, index=q.index))
dq.log(RQ, "Criticality", "Blank", int(q.criticality_raw.isna().sum()), "Filled from rule (Tech G6+ or Non-Tech G8+ = Critical)")
dq.log(RQ, "Criticality", "Recorded value disagrees with rule", int(q.criticality_mismatch.sum()), "Validated (criticality_mismatch flag)")

q["sla_days"] = rq_raw["SLA (Days)"].astype(int)
q["sla_expected"] = sla_rule(q.grade_num)
q["sla_mismatch"] = q.sla_days != q.sla_expected
dq.log(RQ, "SLA (Days)", "Disagrees with grade rule (30 TBA-G2, 45 G3-G5, 60 G6+)", int(q.sla_mismatch.sum()), "Validated (sla_mismatch flag)")

q["replaced_employee_id"] = rq_raw["Replaced Employee ID"].map(norm_emp_id)
q["hiring_manager_id"] = rq_raw["Hiring Manager ID"].map(norm_emp_id)
q["budgeted_max_ctc"] = rq_raw["Budgeted Max CTC (INR)"].astype(float)
q["sla_status_system"] = rq_raw["SLA Status (System)"].map(lambda v: None if is_blank(v) else str(v).strip())
pt_bad = int(((q.position_type == "Replacement") != q.replaced_employee_id.notna()).sum())
dq.log(RQ, "Replaced Employee ID", "Replacement without ID, or New with ID", pt_bad, "Validated")
hm_bad = int((~q.hiring_manager_id.isin(pdir.employee_id)).sum())
dq.log(RQ, "Hiring Manager ID", "Not in People_Directory", hm_bad, "Validated")

# replaced employee (join to cleaned employees)
inm = q.replaced_employee_id.isin(emp.index)
q["replaced_in_master"] = np.where(q.replaced_employee_id.isna(), None, inm)
for src, dst in [("date_of_exit", "replaced_exit_date"), ("exit_type", "replaced_exit_type"),
                 ("exit_classification", "replaced_exit_classification"), ("is_regrettable_exit", "replaced_is_regrettable"),
                 ("thread", "replaced_thread"), ("function", "replaced_function")]:
    q[dst] = q.replaced_employee_id.map(emp[src]).where(inm)
q["replaced_exit_date"] = pd.to_datetime(q["replaced_exit_date"])
q["days_exit_to_req"] = (q.req_raised_on - q.replaced_exit_date).dt.days.astype("Int64")
dq.log(RQ, "Replaced Employee ID", "Not in Employee_Master", int((q.replaced_employee_id.notna() & ~inm).sum()),
       "Exit date / type / regrettable and days_exit_to_req left blank", "Employee left before 01-Apr-2026 (data dictionary)")
rep_nodate = int((inm & q.replaced_exit_date.isna()).sum())
dq.log(RQ, "Replaced Employee ID", "Replaced employee in master but without an exit date", rep_nodate,
       "days_exit_to_req left blank" if rep_nodate else "Validated")
neg_lag = int((q.days_exit_to_req < 0).sum())
dq.log(RQ, "Req Raised On", "Replacement req raised before the replaced employee's exit date", neg_lag,
       "Kept (negative days_exit_to_req = backfill raised ahead of the exit)")

# ═════════════════════════════════════════════════════════════════════════════
# Candidates
# ═════════════════════════════════════════════════════════════════════════════
cd_raw = pd.read_excel(RECRUIT_FILE, CD, dtype=object)
dq.step(CD, "rows in (raw)", len(cd_raw))
exact = cd_raw.duplicated()
dq.log(CD, "(all columns)", "Exact duplicate rows", int(exact.sum()), "Dropped, kept one copy")
c0 = cd_raw[~exact].copy()
dq.step(CD, "drop exact duplicates", len(c0))
c0["candidate_id"] = c0["Candidate ID"].astype(str).str.strip()
c0["req_id"] = c0["Req ID"].map(norm_req_id)
dq.log(CD, "Req ID", "Missing 'REQ_' prefix", int((~c0["Req ID"].astype(str).str.strip().str.upper().str.startswith("REQ_")).sum()), "Added prefix")
orphan = ~c0.req_id.isin(q.req_id)
dq.log(CD, "Req ID", f"No matching requisition after prefix fix (all candidate IDs C690xxx; Req IDs {c0.loc[orphan, 'req_id'].min()}..{c0.loc[orphan, 'req_id'].max()}; includes "
       f"{int(c0.loc[orphan, 'Candidate Status'].str.strip().str.lower().eq('joined').sum())} 'Joined' rows with no offer or DOJ)",
       int(orphan.sum()), "Excluded from candidates.parquet (kept in candidates_excluded.parquet)", "Cannot be tied to a requisition; their 'Joined' status has no offer or joining date behind it")
excluded = c0[orphan].assign(exclusion_reason="no_matching_requisition")
c0 = c0[~orphan]
dq.step(CD, "exclude: no matching requisition", len(c0))

c = pd.DataFrame({"candidate_id": c0.candidate_id, "req_id": c0.req_id})
src_key = c0["Source"].astype(str).str.strip().str.lower()
c["source_raw"] = c0["Source"].astype(str)
c["source_clean"] = src_key.map(SOURCE)
c["agency_name"] = c0["Agency Name"].map(lambda v: None if is_blank(v) else str(v).strip())
dq.log(CD, "Source", f"{c0['Source'].nunique()} spellings (naukri, Naukri.com, LI, Linkedin, Referral, Website, IJP, agency, ...)",
       changed(c0["Source"], c["source_clean"]), f"Mapped to {', '.join(SOURCES)}")
vc = src_key.isin(["vendor", "consultant"])
dq.log(CD, "Source", "'Vendor' / 'Consultant'", int(vc.sum()), "Mapped to Agency",
       f"All {int(vc.sum())} carry an Agency Name ({int((vc & c['agency_name'].notna()).sum())} of {int(vc.sum())}), so they are agency-sourced")
ag_noname = int(((c.source_clean == "Agency") & c.agency_name.isna()).sum())
name_nonag = int(((c.source_clean != "Agency") & c.agency_name.notna()).sum())
dq.log(CD, "Agency Name", "Agency source without Agency Name / Agency Name on non-agency source", ag_noname + name_nonag, "Validated")

for raw_c, col in DATE_COLS.items():
    fm = c0[raw_c].map(date_format_of)
    c[col] = c0[raw_c].map(parse_date)
    odd = fm[~fm.isin(["blank", "datetime"])]
    if len(odd):
        dq.log(CD, raw_c, f"Mixed formats {odd.value_counts().to_dict()}", len(odd), "Parsed to date",
               "DD/MM/YYYY day-first; DD-Mon-YY = 20YY; Excel serials counted from 1899-12-30")
    unp = int((c[col].isna() & ~fm.eq("blank")).sum())
    if unp:
        dq.log(CD, raw_c, "Unparseable date", unp, "Left blank")

c["r1_interviewer_id"] = c0["R1 Interviewer ID"].map(norm_emp_id)
ri_bad = int((c.r1_interviewer_id.notna() & ~c.r1_interviewer_id.isin(pdir.employee_id)).sum())
dq.log(CD, "R1 Interviewer ID", "Not in People_Directory", ri_bad, "Validated")
c["r1_result"] = c0["R1 Result"].map(lambda v: None if is_blank(v) else str(v).strip())
c["r2_result"] = c0["R2 Result"].map(lambda v: None if is_blank(v) else str(v).strip())
c["offered_ctc"] = pd.to_numeric(c0["Offered CTC (INR)"], errors="coerce")
c["current_ctc"] = pd.to_numeric(c0["Current CTC (INR)"], errors="coerce")
ek = c0["Expected CTC (INR)"].map(lambda v: isinstance(v, str))
c["expected_ctc_num"] = c0["Expected CTC (INR)"].map(parse_inr)
dq.log(CD, "Expected CTC (INR)", "'x.x LPA' strings", int(ek.sum()), "Number x 100,000")
c["offer_status"] = c0["Offer Status"].map(lambda v: None if is_blank(v) else str(v).strip())


def notice_days(v):
    if is_blank(v):
        return np.nan
    if not isinstance(v, str):
        return float(v)
    s = v.strip().lower()
    if s == "immediate":
        return 0.0
    m = re.fullmatch(r"(\d+)\s*(day|days|month|months)?", s)
    if not m:
        return np.nan
    return float(m.group(1)) * (30 if (m.group(2) or "").startswith("month") else 1)


nstr = c0["Notice Period (Days)"].map(lambda v: isinstance(v, str))
c["notice_days"] = c0["Notice Period (Days)"].map(notice_days).astype("Int64")
dq.log(CD, "Notice Period (Days)", f"Text values {c0.loc[nstr, 'Notice Period (Days)'].value_counts().to_dict()}", int(nstr.sum()),
       "Converted to days", "1 month = 30 days; Immediate = 0")

cs_raw = c0["Candidate Status"].astype(str)
c["candidate_status"] = cs_raw.str.strip().str.lower().map(_CS_KEY)
dq.log(CD, "Candidate Status", "Spelling variants (Rejected-Profile, Profile Reject, R1 Reject, joined, 'Joined ', Declined)",
       changed(cs_raw, c["candidate_status"]), "Mapped to the 16 agreed canonical statuses")
dq.log(CD, "Candidate Status", "Unmapped status", int(c.candidate_status.isna().sum()), "Validated")

# consistency checks between stage dates and outcomes
chk = {
    "Offered CTC present <=> Offer Released On present": int((c.offered_ctc.notna() != c.offer_released_on.notna()).sum()),
    "Offer Status present <=> Offer Response On present": int((c.offer_status.notna() != c.offer_response_on.notna()).sum()),
    "Actual DOJ present <=> status Joined": int((c.actual_doj.notna() != (c.candidate_status == "Joined")).sum()),
    "Actual DOJ after 31-Oct-2026": int((c.actual_doj > AS_OF).sum()),
    "Applied before Req Raised On": int((c.applied_on < c.req_id.map(q.set_index("req_id").req_raised_on)).sum()),
}
for k, v in chk.items():
    dq.log(CD, "(stage dates)", k, v, "Validated" if v == 0 else "Flagged")
acc_wrong = (c.offer_status == "Accepted") & ~c.candidate_status.isin(["Joined", "Offer Accepted - Yet to Join", "Not Joined - Backed Out"])
dq.log(CD, "Candidate Status", "Accepted offer with a non-offer status", int(acc_wrong.sum()), "Validated" if not acc_wrong.any() else "Flagged")
fut = int((c.expected_doj > AS_OF).sum())
dq.log(CD, "Expected DOJ", "Expected DOJ after 31-Oct-2026", fut, "Kept (future joiners, not an error)")

# stage reached
reached = pd.DataFrame({
    "Applied": c.applied_on.notna(), "Shortlisted": c.shortlisted_on.notna(), "Screening Done": c.screening_done_on.notna(),
    "R1 Interview": c.r1_interview_date.notna(), "R1 Select": c.r1_result.eq("Select"), "R2 Interview": c.r2_interview_date.notna(),
    "Offer Released": c.offer_released_on.notna(), "Offer Accepted": c.offer_status.eq("Accepted"), "Joined": c.actual_doj.notna()})
for s in STAGES:
    c["reached_" + re.sub(r"\W+", "_", s.lower()).strip("_")] = reached[s]
gaps = int((reached.astype(int).diff(axis=1).fillna(0) > 0).sum(axis=1).gt(0).sum())  # reached a later stage but skipped an earlier one
dq.log(CD, "(stage dates)", "Candidate reached a later funnel stage without an earlier one", gaps, "Validated" if gaps == 0 else "Flagged")
c["stage_reached"] = reached.apply(lambda r: STAGES[max(i for i, s in enumerate(STAGES) if r[s])], axis=1)

# stage times
bad_order = c.shortlisted_on < c.applied_on
c["stage_dates_invalid"] = bad_order
dq.log(CD, "Shortlisted On", "Shortlisted On before Applied On", int(bad_order.sum()),
       "Flagged stage_dates_invalid; all stage-time fields blank for these rows (excluded from stage-time metrics)")
neg_total = 0
for a, b, name in TRANSITIONS:
    d = (c[b] - c[a]).dt.days
    neg = d < 0
    neg_total += int((neg & ~bad_order).sum())
    c[name] = d.where(~neg & ~bad_order).astype("Int64")
dq.log(CD, "(stage dates)", "Other out-of-order consecutive stage dates", neg_total, "Validated" if neg_total == 0 else "Set blank")
fb = (c.r1_feedback_submitted_on - c.r1_interview_date).dt.days
c["r1_feedback_days"] = fb.where(fb >= 0).astype("Int64")
dq.log(CD, "R1 Feedback Submitted On", "Feedback before interview", int((fb < 0).sum()), "Validated" if not (fb < 0).any() else "Set blank")
dq.log(CD, "R1 Feedback Submitted On", "R1 interview held, no feedback date (R1 Result 'Pending Feedback' or blank)",
       int((c.r1_interview_date.notna() & c.r1_feedback_submitted_on.isna()).sum()), "r1_feedback_days blank; excluded from turnaround")

# offers and hires
c["is_offer_accepted"] = c.offer_status.eq("Accepted")
c["is_offer_declined"] = c.offer_status.eq("Declined")
c["is_backed_out"] = c.candidate_status.eq("Not Joined - Backed Out")
c["is_joined"] = c.candidate_status.eq("Joined")
c["joining_due"] = c.is_offer_accepted & (c.expected_doj <= AS_OF)
c["offer_to_expected_ratio"] = (c.offered_ctc / c.expected_ctc_num).round(4)
c["offer_to_budget_ratio"] = (c.offered_ctc / c.req_id.map(q.set_index("req_id").budgeted_max_ctc)).round(4)
over_budget = int((c.offer_to_budget_ratio > 1).sum())
dq.log(CD, "Offered CTC (INR)", "Offer above the requisition's Budgeted Max CTC", over_budget, "Validated" if over_budget == 0 else "Flagged")

# hired candidate per requisition: accepted and not backed out; joined > yet-to-join > earliest acceptance
cand_h = c[c.is_offer_accepted & ~c.is_backed_out].copy()
cand_h["_rank"] = np.select([cand_h.is_joined, cand_h.candidate_status.eq("Offer Accepted - Yet to Join")], [0, 1], default=2)
cand_h = cand_h.sort_values(["req_id", "_rank", "offer_response_on", "candidate_id"])
multi = int(cand_h.req_id.duplicated().sum())
hires = cand_h.drop_duplicates("req_id", keep="first").set_index("req_id")
dq.log(RQ, "(derived) hired_candidate_id", "Requisitions with more than one live accepted offer", multi,
       "Rule: joined > yet to join > earliest acceptance" if multi else "Validated (rule not needed: at most one per req)")
dq.log(CD, "Candidate Status", "Accepted offers that backed out", int(c.is_backed_out.sum()), "Not a hire; the requisition stays open unless another candidate accepted")
c["is_hire"] = c.candidate_id.isin(hires.candidate_id)
c["agency_fee_inr"] = np.where((c.source_clean == "Agency") & c.is_joined, (AGENCY_FEE_RATE * c.offered_ctc).round(0), 0.0)
dq.log(CD, "(derived) agency_fee_inr", "Agency fee", int(((c.source_clean == "Agency") & c.is_joined).sum()),
       "8.33% x Offered CTC for agency-sourced candidates who joined; 0 otherwise")

# requisition-level hire fields
q = q.set_index("req_id")
q["hired_candidate_id"] = hires.candidate_id
q["hire_status"] = hires.candidate_status.map({"Joined": "Joined", "Offer Accepted - Yet to Join": "Yet to Join"})
q["hire_source"] = hires.source_clean
q["offer_accepted_on"] = hires.offer_response_on
q["hire_actual_doj"] = hires.actual_doj
q["ttf_days"] = (q.offer_accepted_on - q.req_raised_on).dt.days.astype("Int64")
q["is_filled"] = q.hired_candidate_id.notna()
q["sla_met"] = (q.ttf_days <= q.sla_days).where(q.is_filled)
q["age_days_as_of_31oct"] = (AS_OF - q.req_raised_on).dt.days.astype(int)
q["is_open"] = q.req_status.eq("Open")
q["open_breached"] = (q.age_days_as_of_31oct > q.sla_days).where(q.is_open)
q["sla_status_recomputed"] = np.select(
    [q.is_filled & (q.ttf_days <= q.sla_days), q.is_filled, q.is_open & (q.age_days_as_of_31oct > q.sla_days), q.is_open],
    ["Within SLA", "Breached", "Open - Breached", "Open - Within SLA"], default=None)
q["sla_status_mismatch"] = q.sla_status_system.fillna("") != pd.Series(q.sla_status_recomputed, index=q.index).fillna("")
neg_ttf = int((q.ttf_days < 0).sum())
dq.log(RQ, "(derived) ttf_days", "Negative time to fill", neg_ttf, "Validated" if neg_ttf == 0 else "Flagged")

exp_status = np.select([q.hire_status.eq("Joined"), q.hire_status.eq("Yet to Join")], ["Closed - Joined", "Offer Accepted"], default="")
inconsistent = int(((exp_status != "") & (q.req_status != exp_status)).sum() + ((exp_status == "") & q.req_status.isin(["Closed - Joined", "Offer Accepted"])).sum())
dq.log(RQ, "Req Status", "Req Status disagrees with its candidates (Closed - Joined <=> a joiner; Offer Accepted <=> a yet-to-join hire)",
       inconsistent, "Validated" if inconsistent == 0 else "Flagged")
held = ~q.is_filled & ~q.is_open
dq.log(RQ, "SLA Status (System)", f"Blank on On Hold / Archived reqs ({q.loc[q.sla_status_system.isna(), 'req_status'].value_counts().to_dict()})",
       int(q.sla_status_system.isna().sum()), "sla_status_recomputed also blank for On Hold / Archived (no SLA clock)", "SLA applies to filled and open reqs only")
mm = q[q.sla_status_mismatch]
pairs = (mm.sla_status_system.fillna("blank") + " -> " + pd.Series(mm.sla_status_recomputed, index=mm.index).fillna("blank")).value_counts().to_dict()
over = (mm.ttf_days - mm.sla_days).dropna()
dq.log(RQ, "SLA Status (System)", f"FINDING: system status disagrees with recomputed status ({pairs}); TTF overrun {int(over.min())}-{int(over.max())} days over SLA ({', '.join(mm.index)})", len(mm),
       "Recomputed SLA status used everywhere (KPIs, charts, deck); system value kept only as sla_status_system for the mismatch panel", "TTF = Offer Response On of the hired candidate - Req Raised On (README); the system marks these 'Within SLA' although TTF > SLA days, and no other date in the data explains it")

bo = c[c.is_backed_out].groupby("req_id").size()
bo_out = q.loc[bo.index]
refilled = bo_out.is_filled
dq.log(RQ, "(derived) is_filled", f"Reqs with a backed-out candidate: {len(bo)} ({int(refilled.sum())} refilled by another candidate who joined or accepted; "
       f"{int((~refilled).sum())} not refilled: {bo_out.loc[~refilled, 'req_status'].value_counts().to_dict()})", len(bo),
       "Backed-out candidates are never hires; the req counts as filled only via another accepted / joined candidate")
q["had_backout"] = q.index.isin(bo.index)
parallel = [r_ for r_ in bo_out.index[refilled] if q.at[r_, "offer_accepted_on"] <= c.loc[c.is_backed_out & (c.req_id == r_), "offer_response_on"].max()]
dq.log(RQ, "(derived) is_filled", f"Refilled reqs where the hire accepted on/before the backed-out candidate's acceptance (backup offer in parallel): {', '.join(parallel)}",
       len(parallel), "No change: TTF always uses the hired candidate's acceptance date", "README: occasionally a backup offer runs in parallel")
q = q.reset_index()
dq.step(RQ, "rows out", len(q))

CAND_COLS = (["candidate_id", "req_id", "source_raw", "source_clean", "agency_name"] + list(DATE_COLS.values()) +
             ["r1_interviewer_id", "r1_result", "r2_result", "offered_ctc", "current_ctc", "expected_ctc_num", "notice_days",
              "offer_status", "candidate_status", "stage_reached"] + [c_ for c_ in c.columns if c_.startswith("reached_")] +
             ["stage_dates_invalid"] + [t[2] for t in TRANSITIONS] +
             ["r1_feedback_days", "is_offer_accepted", "is_offer_declined", "is_backed_out", "is_joined", "joining_due",
              "offer_to_expected_ratio", "offer_to_budget_ratio", "is_hire", "agency_fee_inr"])
c = c[CAND_COLS].sort_values("candidate_id").reset_index(drop=True)
dq.step(CD, "rows out", len(c))
REQ_COLS = ["req_id", "req_raised_on", "raised_month", "thread", "function", "job_family", "designation", "grade", "grade_num",
            "location", "position_type", "replaced_employee_id", "replaced_in_master", "replaced_exit_date", "replaced_exit_type",
            "replaced_exit_classification", "replaced_is_regrettable", "replaced_thread", "replaced_function", "days_exit_to_req",
            "criticality", "criticality_raw", "criticality_derived", "criticality_mismatch", "hiring_manager_id", "recruiter",
            "recruiter_id", "sla_days", "sla_expected", "sla_mismatch", "req_status", "budgeted_max_ctc", "hired_candidate_id",
            "hire_status", "hire_source", "offer_accepted_on", "hire_actual_doj", "ttf_days", "is_filled", "sla_met",
            "age_days_as_of_31oct", "is_open", "open_breached", "sla_status_system", "sla_status_recomputed", "sla_status_mismatch",
            "had_backout"]
q = q[REQ_COLS]
for col in ["replaced_in_master", "replaced_is_regrettable", "sla_met", "open_breached"]:
    q[col] = q[col].astype("boolean")

# ═════════════════════════════════════════════════════════════════════════════
# write
# ═════════════════════════════════════════════════════════════════════════════
q.to_parquet(CLEAN_DIR / "requisitions.parquet", index=False)
c.to_parquet(CLEAN_DIR / "candidates.parquet", index=False)
rc.to_parquet(CLEAN_DIR / "recruiters.parquet", index=False)
pdir.to_parquet(CLEAN_DIR / "people_directory.parquet", index=False)
ex = excluded[[col for col in cd_raw.columns] + ["candidate_id", "req_id", "exclusion_reason"]].copy()
ex = ex.astype({col: "string" for col in cd_raw.columns})
ex.to_parquet(CLEAN_DIR / "candidates_excluded.parquet", index=False)
dq.write()

print(f"requisitions.parquet      {len(q):>5}   candidates.parquet {len(c):>5}   excluded {len(ex)}")
print(f"recruiters.parquet        {len(rc):>5}   people_directory.parquet {len(pdir):>5}   dq_log rows (Recruitment) {len(dq.rows)}")
print("\nReconciliation:")
for s in dq.recon:
    print(f"  {s['sheet']:<16} {s['order']:>2}. {s['step']:<36} {s['rows']:>5}  {s['change'] if s['change'] != '' else ''}")
print("\nReq status:", q.req_status.value_counts().to_dict())
print("Filled:", int(q.is_filled.sum()), "| hire status:", q.hire_status.value_counts().to_dict())
print(f"TTF median {q.ttf_days.median():.0f} d (n={q.ttf_days.notna().sum()}); SLA met {q.sla_met.mean():.1%}; open {int(q.is_open.sum())}, open past SLA {int(q.open_breached.sum())}")
print("SLA status system vs recomputed mismatches:", int(q.sla_status_mismatch.sum()), pairs)
print("Sources:", c.source_clean.value_counts().to_dict())
acc = int(c.is_offer_accepted.sum()); dec = int(c.is_offer_declined.sum()); due = int(c.joining_due.sum())
print(f"Offers: accepted {acc}, declined {dec} -> acceptance {acc / (acc + dec):.1%}; joined {int(c.is_joined.sum())} of {due} due -> joining rate {c.is_joined.sum() / due:.1%}")
print(f"Agency fees: INR {c.agency_fee_inr.sum():,.0f} on {int((c.agency_fee_inr > 0).sum())} joiners")
