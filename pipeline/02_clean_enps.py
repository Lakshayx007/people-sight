"""
02_clean_enps.py
----------------
Clean the eNPS workbook (Employee_Master, eNPS_Responses, Pay_Bands).

Order: IDs -> duplicates -> categoricals -> dates -> CTC -> derived fields -> survey cleaning.
Every rule writes one row to data/clean/dq_log.csv; row counts in -> each exclusion -> out
go to data/clean/reconciliation.csv.

Outputs (data/clean/): employees.parquet, survey_responses.parquet, pay_bands.parquet
Run:  python pipeline/02_clean_enps.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    AS_OF, CLEAN_DIR, EMP_ID_RE, ENPS_FILE, WAVES, DQLog, active_on, date_format_of, grade_num,
    is_blank, job_family, norm_emp_id, norm_grade, parse_date, parse_inr, tenure_band, THREADS, thread_clean,
)

DS = "eNPS"
EM, RS, PB = "Employee_Master", "eNPS_Responses", "Pay_Bands"
dq = DQLog(DS)

# ── canonical values ─────────────────────────────────────────────────────────
LOCATIONS = ["Bengaluru HO", "Bengaluru", "Ahmedabad", "Chennai", "Delhi NCR", "Hyderabad", "Jaipur",
             "Kolkata", "Lucknow", "Mumbai", "Pune"]
_LOC_KEY = {"blr - ho": "Bengaluru HO", "bangalore ho": "Bengaluru HO", "bengaluru ho": "Bengaluru HO",
            "bengaluru": "Bengaluru", "hyd": "Hyderabad", "hyderabad": "Hyderabad", "mumbai": "Mumbai",
            "chennai": "Chennai", "delhi": "Delhi NCR", "new delhi": "Delhi NCR", "gurugram": "Delhi NCR",
            "delhi ncr": "Delhi NCR", "calcutta": "Kolkata", "kolkata": "Kolkata", "ahmedabad": "Ahmedabad",
            "jaipur": "Jaipur", "lucknow": "Lucknow", "pune": "Pune"}
RATINGS = ["Game Changer", "High Impact Player", "Solid Performer", "Needs Improvement",
           "Below Expectations", "Not Rated - New Joiner", "Missing"]
NOT_RATED = "Not Rated - New Joiner"
COMMENT_THEMES = {
    "Supportive manager and peers.": "Positive",
    "Love the pace and ownership here.": "Positive",
    "Proud of the work we do.": "Positive",
    "Great team and good learning.": "Positive",
    "Expectations keep changing week to week, no clarity from manager.": "Manager",
    "Too much micromanagement from my reporting manager.": "Manager",
    "1:1s have stopped after the reorg, feel unheard.": "Manager",
    "Would like more regular feedback from my manager.": "Manager",
    "My manager rarely gives feedback since the team change.": "Manager",
    "Increment this year did not match the effort.": "Pay",
    "Friends in similar roles elsewhere earn much more.": "Pay",
    "Salary is below what peers in the market get.": "Pay",
    "Pay is not competitive for the work we do.": "Pay",
    "Not sure what the next role for me looks like.": "Growth",
    "Career path is unclear beyond my current grade.": "Growth",
    "Late-night escalations are becoming the norm.": "Workload",
    "Workload during peak season is too high.": "Workload",
    "Too many weekend shifts.": "Workload",
    "No buddy or onboarding plan when I joined.": "Onboarding",
    "Training at the city office was rushed.": "Onboarding",
    "First month was confusing, no proper induction at the hub.": "Onboarding",
    "Did not get laptop/access for two weeks after joining.": "Onboarding",
}
MGR_WINDOW = (pd.Timestamp("2026-04-18"), pd.Timestamp("2026-10-04"))
MGR_CHANGED, MGR_FIRST, MGR_SAME = "Changed manager", "New joiner (first manager)", "Same manager"
MANAGER_STATUSES = [MGR_CHANGED, MGR_FIRST, MGR_SAME]
BAND_SET_DATE = pd.Timestamp("2026-04-01")   # band set effective on the as-of date


def changed(before: pd.Series, after: pd.Series) -> int:
    return int((before.astype(str) != after.astype(str)).sum())


# ═════════════════════════════════════════════════════════════════════════════
# Pay_Bands
# ═════════════════════════════════════════════════════════════════════════════
pb_raw = pd.read_excel(ENPS_FILE, PB, dtype=object)
dq.step(PB, "rows in (raw)", len(pb_raw))
pb = pd.DataFrame({
    "effective_from": pd.to_datetime(pb_raw["Effective From"]),
    "job_family": pb_raw["Job Family"].str.strip(),
    "grade": pb_raw["Grade"].map(norm_grade),
    "band_min": pb_raw["Band Min (INR)"].astype(float),
    "band_mid": pb_raw["Band Mid (INR)"].astype(float),
    "band_max": pb_raw["Band Max (INR)"].astype(float),
})
bad_order = int(((pb.band_min > pb.band_mid) | (pb.band_mid > pb.band_max)).sum())
dq.log(PB, "Effective From", "Two band sets (2025-04-01, 2026-04-01)", len(pb), "Kept both; compa-ratio uses the 2026-04-01 set (effective on the 31-Oct-2026 as-of date and on both wave open dates)",
       "Band set in force on a date = latest Effective From on or before it")
dq.log(PB, "Band Min/Mid/Max", "Check min <= mid <= max", bad_order, "Validated" if bad_order == 0 else "Flagged")
dq.step(PB, "rows out", len(pb))
bands_now = pb[pb.effective_from == BAND_SET_DATE].set_index(["job_family", "grade"])

# ═════════════════════════════════════════════════════════════════════════════
# Employee_Master
# ═════════════════════════════════════════════════════════════════════════════
raw = pd.read_excel(ENPS_FILE, EM, dtype=object)
dq.step(EM, "rows in (raw)", len(raw))
e = raw.copy()

# 1. IDs ----------------------------------------------------------------------
e["employee_id"] = e["Employee ID"].map(norm_emp_id)
n = changed(e["Employee ID"], e["employee_id"])
n_lower = int(e["Employee ID"].astype(str).str.contains("emp").sum())
dq.log(EM, "Employee ID", f"Leading/trailing spaces ({n - n_lower}) or lowercase 'emp' ({n_lower})", n, "Strip spaces, upper-case")
bad_fmt = int((~e["employee_id"].map(lambda v: bool(EMP_ID_RE.fullmatch(v)))).sum())
dq.log(EM, "Employee ID", "Format check EMP + 5 digits after fix", bad_fmt, "Validated")
e["Reporting Manager ID"] = e["Reporting Manager ID"].map(norm_emp_id)

# 2. duplicates ---------------------------------------------------------------
cmp_cols = [c for c in raw.columns if c != "Employee ID"] + ["employee_id"]
exact = e.duplicated(subset=cmp_cols, keep="first")
dq.log(EM, "(all columns)", "Exact duplicate rows (after ID fix)", int(exact.sum()), "Dropped, kept one copy")
e = e[~exact]
dq.step(EM, "drop exact duplicates", len(e))
e["_upd"] = pd.to_datetime(e["Record Updated On"])
dup_ids = sorted(e.loc[e["employee_id"].duplicated(keep=False), "employee_id"].unique())
e = e.sort_values(["employee_id", "_upd"]).drop_duplicates("employee_id", keep="last")
dq.log(EM, "Employee ID", f"Same ID, different values ({', '.join(dup_ids)}: Location differs)", len(dup_ids),
       "Kept the row with the latest Record Updated On", "Latest HRMS update is the current record; both versions were updated after Apr-2026, so no history can be recovered for the April snapshot")
dq.step(EM, "keep latest record per duplicated ID", len(e))

# 3. categoricals -------------------------------------------------------------
e["company"] = e["Company"].str.strip()
e["function"] = e["Function"].str.strip()
e["designation"] = e["Designation"].str.strip()
e["employee_name"] = e["Employee Name"].str.strip()

e["thread"] = e["Thread"].map(thread_clean)
dq.log(EM, "Thread", "Spelling variants / trailing spaces (Intra City, InterCity, P&M, Geo-Expansion, ...)",
       changed(e["Thread"], e["thread"]), f"Mapped to 6 canonical threads: {', '.join(THREADS)}")

e["grade"] = e["Grade"].map(norm_grade)
dq.log(EM, "Grade", "Variants g1 / Grade 3 / bare 4 / Trainee", changed(e["Grade"], e["grade"]), "Mapped to TBA, G1..G10 (Trainee -> TBA; bare number n -> Gn)")

loc_raw = e["Location"].astype(str).str.strip()
lt_raw = e["Location Type"].map(lambda v: None if is_blank(v) else str(v).strip())
loc = loc_raw.str.lower().map(_LOC_KEY)
blr = loc_raw.str.upper().eq("BLR")
loc[blr] = np.where(lt_raw[blr].eq("HO"), "Bengaluru HO", "Bengaluru")
e["location"] = loc
dq.log(EM, "Location", "Spelling/case/space variants (BLR - HO, Bangalore HO, Hyd, MUMBAI, chennai, Calcutta, trailing spaces)",
       changed(e["Location"], e["location"]) - int(blr.sum()), "Mapped to canonical city names; Bengaluru (city) kept separate from Bengaluru HO")
dq.log(EM, "Location", "Delhi / New Delhi / Gurugram", int(loc_raw.str.lower().isin(["delhi", "new delhi", "gurugram"]).sum()), "Merged into Delhi NCR")
dq.log(EM, "Location", "Ambiguous 'BLR'", int(blr.sum()), "Decided by Location Type: all are City -> Bengaluru", "BLR with Location Type City is the Bengaluru city office, not HO")
e["location_type"] = lt_raw
fill = e["location_type"].isna()
e.loc[fill, "location_type"] = np.where(e.loc[fill, "location"].eq("Bengaluru HO"), "HO", "City")
dq.log(EM, "Location Type", "Blank", int(fill.sum()), "Filled: HO if location is Bengaluru HO, else City")
lt_conflict = int(((e["location"] == "Bengaluru HO") != (e["location_type"] == "HO")).sum())
dq.log(EM, "Location Type", "Check: HO <=> Bengaluru HO", lt_conflict, "Validated" if lt_conflict == 0 else "Flagged")

e["employment_status"] = e["Employment Status"].astype(str).str.strip().str.title()
dq.log(EM, "Employment Status", "Case / trailing-space variants (ACTIVE, 'Active ', EXITED)", changed(e["Employment Status"], e["employment_status"]), "Mapped to Active / Exited")

e["exit_type"] = e["Exit Type"].map(lambda v: None if is_blank(v) else str(v).strip())
e["exit_classification"] = e["Exit Classification"].map(lambda v: None if is_blank(v) else str(v).strip())

# 4. dates --------------------------------------------------------------------
fmt = e["Date of Joining"].map(date_format_of)
e["date_of_joining"] = e["Date of Joining"].map(parse_date)
dq.log(EM, "Date of Joining", f"Mixed formats {fmt.value_counts().to_dict()}", int((fmt != "datetime").sum()),
       "Parsed to date", "DD/MM/YYYY strings are day-first (Indian format)")
dq.log(EM, "Date of Joining", "Unparseable", int(e["date_of_joining"].isna().sum()), "Validated")
fmt = e["Date of Exit"].map(date_format_of)
e["date_of_exit"] = e["Date of Exit"].map(parse_date)
dq.log(EM, "Date of Exit", f"Mixed formats {fmt[fmt != 'blank'].value_counts().to_dict()}", int(fmt.isin(['DD-Mon-YY']).sum()), "Parsed to date", "DD-Mon-YY years are 20YY")
e["manager_effective_from"] = pd.to_datetime(e["Manager Effective From"])
e["record_updated_on"] = e["_upd"]

# status vs exit date cross-check (agreed decision, Phase 0/1)
act_exit = (e["employment_status"] == "Active") & e["date_of_exit"].notna()
dq.log(EM, "Employment Status", f"'Active' but Date of Exit + Exit Type present ({', '.join(e.loc[act_exit, 'employee_id'])})", int(act_exit.sum()),
       "Set to Exited, kept the exit date", "Exit date, type and classification agree; the status field is stale")
e.loc[act_exit, "employment_status"] = "Exited"
ex_nodate = (e["employment_status"] == "Exited") & e["date_of_exit"].isna()
e["exit_date_unknown"] = ex_nodate
dq.log(EM, "Date of Exit", f"'Exited' but no exit date ({', '.join(e.loc[ex_nodate, 'employee_id'])})", int(ex_nodate.sum()),
       "Kept Exited; exit date left blank, exit_date_unknown = true", "Without an exit date they count as active on both wave open dates and have no exit month")
type_no_exit = int((e["exit_type"].notna() & (e["employment_status"] != "Exited")).sum())
dq.log(EM, "Exit Type", "Exit Type present on a non-exited employee (after fixes)", type_no_exit, "Validated" if type_no_exit == 0 else "Flagged")
late_exit = int((e["date_of_exit"] > AS_OF).sum())
dq.log(EM, "Date of Exit", "Exit date after 31-Oct-2026", late_exit, "Validated")
mef_before = int((e["manager_effective_from"] < e["date_of_joining"]).sum())
dq.log(EM, "Manager Effective From", "Before Date of Joining", mef_before, "Validated")

# performance rating
pr = e["Performance Rating FY25-26"].map(lambda v: None if is_blank(v) else str(v).strip())
nj = pr.eq("New Joiner")
null_new = pr.isna() & (e["date_of_joining"] >= pd.Timestamp("2026-01-01"))
null_old = pr.isna() & ~null_new
pr[nj] = NOT_RATED
pr[null_new] = NOT_RATED
pr[null_old] = "Missing"
e["performance_rating"] = pr
dq.log(EM, "Performance Rating FY25-26", "'New Joiner' label", int(nj.sum()), f"Mapped to '{NOT_RATED}'")
dq.log(EM, "Performance Rating FY25-26", "Blank for joiners on/after 01-Jan-2026", int(null_new.sum()), f"Set to '{NOT_RATED}'", "Joiners after 01-Jan-2026 are not rated (data dictionary)")
dq.log(EM, "Performance Rating FY25-26", "Blank for earlier joiners", int(null_old.sum()), "Set to 'Missing'")

# 5. CTC ----------------------------------------------------------------------
kind = e["Annual CTC (INR)"].map(lambda v: "blank" if is_blank(v) else ("number" if not isinstance(v, str) else ("lakh" if re.search(r"[A-Za-z]", v) else "comma")))
e["annual_ctc_raw"] = e["Annual CTC (INR)"].map(lambda v: None if is_blank(v) else str(v))
e["annual_ctc"] = e["Annual CTC (INR)"].map(parse_inr)
dq.log(EM, "Annual CTC (INR)", "Indian-comma strings (e.g. 4,48,000)", int((kind == "comma").sum()), "Commas removed, parsed to number")
dq.log(EM, "Annual CTC (INR)", "Lakh strings (2.96 LPA / 8.44 L / 3.64 Lakhs)", int((kind == "lakh").sum()), "Number x 100,000")
dq.log(EM, "Annual CTC (INR)", "Blank", int((kind == "blank").sum()), "Left blank; compa-ratio and compa band = Unknown")

e["job_family"] = e["function"].map(job_family)
e["band_mid"] = [bands_now["band_mid"].get((f, g), np.nan) for f, g in zip(e["job_family"], e["grade"])]
dq.log(EM, "Grade", "No 2026 pay band for (job family, grade)", int(e["band_mid"].isna().sum()), "Validated")
ratio = e["annual_ctc"] / e["band_mid"]
monthly = (ratio < 0.5) & ((ratio * 12).between(0.5, 2.0))
e["ctc_flag"] = "ok"
e.loc[e["annual_ctc"].isna(), "ctc_flag"] = "missing"
e.loc[monthly, "annual_ctc"] = e.loc[monthly, "annual_ctc"] * 12
e.loc[monthly, "ctc_flag"] = "corrected_monthly_x12"
dq.log(EM, "Annual CTC (INR)", f"Value < 0.5x band mid and x12 lands within 0.5x-2x ({', '.join(e.loc[monthly, 'employee_id'])})", int(monthly.sum()),
       "Multiplied by 12, ctc_flag = corrected_monthly_x12", "Monthly salary entered in the annual field (user decision, Phase 1, option A)")
ratio = e["annual_ctc"] / e["band_mid"]
oob = ratio.notna() & ((ratio < 0.5) | (ratio > 2.0))
e.loc[oob, "ctc_flag"] = "out_of_band"
dq.log(EM, "Annual CTC (INR)", "Outside 0.5x-2x of band mid after correction", int(oob.sum()), "Flagged (ctc_flag = out_of_band), value kept")

# 6. derived fields -----------------------------------------------------------
e["grade_num"] = e["grade"].map(grade_num).astype("Int64")
e["compa_ratio"] = ratio.round(4)
e["compa_band"] = np.select([ratio < 0.90, ratio <= 1.10, ratio > 1.10], ["Below", "At", "Above"], default="Unknown")
e["is_exited"] = e["employment_status"].eq("Exited")
e["exit_month"] = e["date_of_exit"].dt.strftime("%Y-%m")
e["is_regrettable_exit"] = e["is_exited"] & e["exit_classification"].eq("Regrettable")
end = e["date_of_exit"].fillna(AS_OF).clip(upper=AS_OF)
e["tenure_days"] = (end - e["date_of_joining"]).dt.days.astype("Int64")
for w, wd in WAVES.items():
    key = w.lower()
    e[f"active_on_{key}_open"] = active_on(e["date_of_joining"], e["date_of_exit"], wd["open"])
    e[f"tenure_band_{key}"] = tenure_band(e["date_of_joining"], wd["open"])
e["tenure_band_asof"] = tenure_band(e["date_of_joining"], AS_OF)
in_win = e["manager_effective_from"].between(*MGR_WINDOW)
e["manager_changed_literal"] = in_win          # backup only: literal the case brief rule, not used in charts
changed_mgr = in_win & (e["manager_effective_from"] > e["date_of_joining"])
first_mgr = in_win & (e["manager_effective_from"] == e["date_of_joining"])
e["manager_status"] = np.select([changed_mgr, first_mgr], [MGR_CHANGED, MGR_FIRST], default=MGR_SAME)
e["joined_between_waves"] = e["date_of_joining"].between(WAVES["Apr"]["open"] + pd.Timedelta(days=1), WAVES["Oct"]["open"])
MGR_ASSUMPTION = ("Manager Effective From equal to joining date = first manager, not a change. Only the current "
                  "manager is recorded, so earlier changes or multiple changes are not visible.")
dq.log(EM, "Manager Effective From", f"manager_status: '{MGR_CHANGED}' (effective 18-Apr..04-Oct-2026 and after Date of Joining)",
       int(changed_mgr.sum()), "manager_status = Changed manager (dashboard filter + segment dimension)", MGR_ASSUMPTION)
dq.log(EM, "Manager Effective From", f"manager_status: '{MGR_FIRST}' (effective 18-Apr..04-Oct-2026 and equal to Date of Joining)",
       int(first_mgr.sum()), "manager_status = New joiner (first manager)", MGR_ASSUMPTION)
dq.log(EM, "Manager Effective From", f"manager_status: '{MGR_SAME}' (everyone else)",
       int((e["manager_status"] == MGR_SAME).sum()), "manager_status = Same manager", MGR_ASSUMPTION)
dq.log(EM, "Manager Effective From", "Literal the case brief rule (effective 18-Apr..04-Oct-2026), any joining date",
       int(in_win.sum()), "Kept as manager_changed_literal (backup only, not used in charts)", MGR_ASSUMPTION)
other_in_win = int((in_win & (e["manager_effective_from"] < e["date_of_joining"])).sum())
dq.log(EM, "Manager Effective From", "In window but before Date of Joining", other_in_win, "Validated" if other_in_win == 0 else "Flagged")

dq.step(EM, "rows out (one per employee)", len(e))
EMP_COLS = ["employee_id", "employee_name", "company", "thread", "function", "job_family", "designation", "grade", "grade_num",
            "location", "location_type", "date_of_joining", "reporting_manager_id", "manager_effective_from",
            "manager_status", "manager_changed_literal", "joined_between_waves", "performance_rating",
            "annual_ctc", "annual_ctc_raw", "ctc_flag", "band_mid", "compa_ratio", "compa_band",
            "employment_status", "is_exited", "date_of_exit", "exit_date_unknown", "exit_month", "exit_type",
            "exit_classification", "is_regrettable_exit", "record_updated_on", "tenure_days", "tenure_band_asof",
            "active_on_apr_open", "active_on_oct_open", "tenure_band_apr", "tenure_band_oct"]
e = e.rename(columns={"Reporting Manager ID": "reporting_manager_id"})[EMP_COLS].sort_values("employee_id").reset_index(drop=True)
emp = e.set_index("employee_id")

# ═════════════════════════════════════════════════════════════════════════════
# eNPS_Responses
# ═════════════════════════════════════════════════════════════════════════════
rraw = pd.read_excel(ENPS_FILE, RS, dtype=object)
dq.step(RS, "rows in (raw)", len(rraw))
QMAP = {c: f"q{c[1]}" for c in rraw.columns if re.match(r"Q[1-6]\.", c)}
r = rraw.rename(columns=QMAP).copy()
r["response_id"] = r["Response ID"].astype(str).str.strip()
r["employee_id"] = r["Employee ID"].map(norm_emp_id)
dq.log(RS, "Employee ID", "Leading/trailing spaces or lowercase", changed(r["Employee ID"], r["employee_id"]), "Strip spaces, upper-case")
r["submitted_on"] = pd.to_datetime(r["Submitted On"])

# wave
r["wave"] = r["Survey Wave"].astype(str).str.strip().str.lower().str[:3].map({"apr": "Apr", "oct": "Oct"})
dq.log(RS, "Survey Wave", f"{r['Survey Wave'].nunique()} spellings ({', '.join(sorted(r['Survey Wave'].unique()))})",
       int((~r["Survey Wave"].isin(["Apr", "Oct"])).sum()), "Mapped to Apr / Oct")
wm = int(((r["wave"] == "Apr") & (r["submitted_on"].dt.month != 4)).sum() + ((r["wave"] == "Oct") & (r["submitted_on"].dt.month != 10)).sum())
dq.log(RS, "Survey Wave", "Cross-check wave label vs Submitted On month", wm, "Validated" if wm == 0 else "Flagged")

# answers
q1s = r["q1"].map(lambda v: None if is_blank(v) else str(v).strip())
frac = q1s.fillna("").str.contains("/")
r["q1_raw"] = q1s
r["q1_num"] = pd.to_numeric(q1s.str.split("/").str[0], errors="coerce")
dq.log(RS, "Q1", "'x/10' style strings", int(frac.sum()), "Parsed numerator to number")
q1_oor = r["q1_num"].notna() & ~r["q1_num"].between(0, 10)
q1_blank = r["q1_num"].isna()
r["q1_clean"] = r["q1_num"].where(~q1_oor).astype("Int64")
for q in ["q2", "q3", "q4", "q5", "q6"]:
    r[q] = pd.to_numeric(r[q], errors="coerce").astype("Int64")
    oor = int((r[q].notna() & ~r[q].between(1, 5)).sum())
    dq.log(RS, q.upper(), "Blank answer", int(r[q].isna().sum()), "Left blank; excluded from that driver's mean / % favourable only")
    dq.log(RS, q.upper(), "Outside 1-5", oor, "Validated" if oor == 0 else "Set blank")

# exclusions — first reason wins, in this order
r["exclusion_reason"] = None


def exclude(mask, reason, column, issue, treatment, assumption=""):
    m = mask & r["exclusion_reason"].isna()
    r.loc[m, "exclusion_reason"] = reason
    dq.log(RS, column, issue, int(m.sum()), treatment, assumption)
    dq.step(RS, f"exclude: {reason}", int(r["exclusion_reason"].isna().sum()))
    return int(m.sum())


is_test = ~r["employee_id"].map(lambda v: bool(EMP_ID_RE.fullmatch(v)))
exclude(is_test, "test_id", "Employee ID", f"Test IDs ({', '.join(sorted(r.loc[is_test, 'employee_id']))})", "Excluded")
nim = ~r["employee_id"].isin(emp.index)
exclude(nim, "not_in_master", "Employee ID", f"Not in Employee_Master ({', '.join(sorted(r.loc[nim & ~is_test, 'employee_id']))})", "Excluded", "Cannot verify invitation or attach attributes")
r = r.sort_values(["employee_id", "wave", "submitted_on"])
superseded = r.duplicated(["employee_id", "wave"], keep="last") & r["exclusion_reason"].isna()
exclude(superseded, "duplicate_superseded", "Response ID", "Same employee answered the same wave twice", "Kept the latest submission, excluded the earlier one",
        "The last answer is the intended one")
open_d = r["wave"].map(lambda w: WAVES[w]["open"])
close_d = r["wave"].map(lambda w: WAVES[w]["close"]) + pd.Timedelta(days=1)
inm = r["employee_id"].isin(emp.index)
act = pd.Series(False, index=r.index)
act[inm] = [bool(active_on(pd.Series([emp.at[i, "date_of_joining"]]), pd.Series([emp.at[i, "date_of_exit"]]), d).iloc[0])
            for i, d in zip(r.loc[inm, "employee_id"], open_d[inm])]
exclude(inm & ~act, "not_active_on_open_date", "Submitted On", "Respondent not active on the wave open date (joined after it or exited before it)", "Excluded", "Only invited employees count")
outside = (r["submitted_on"] < open_d) | (r["submitted_on"] >= close_d)
exclude(outside, "outside_window", "Submitted On", "Submitted outside the wave window", "Excluded")
exclude(q1_blank, "q1_blank", "Q1", "Q1 blank", "Excluded from all survey metrics", "Keeps one base n per wave for eNPS and drivers")
exclude(q1_oor, "q1_out_of_range", "Q1", f"Q1 outside 0-10 ({sorted(r.loc[q1_oor, 'q1_num'].astype(int).unique().tolist())})", "Excluded from all survey metrics", "Keeps one base n per wave for eNPS and drivers")
r["is_valid"] = r["exclusion_reason"].isna()

# derived
r["nps_group"] = pd.cut(r["q1_clean"].astype(float), [-0.5, 6.5, 8.5, 10.5], labels=["Detractor", "Passive", "Promoter"]).astype(object)
r["comment"] = r["Comments (optional)"].map(lambda v: None if is_blank(v) else str(v).strip())
r["comment_theme"] = r["comment"].map(lambda c: None if c is None else COMMENT_THEMES.get(c, "Other"))
dq.log(RS, "Comments (optional)", f"{r['comment'].nunique()} repeated phrases", int(r["comment"].notna().sum()),
       "Mapped to themes Manager, Pay, Growth, Workload, Onboarding, Positive", "Phrase-to-theme mapping in 02_clean_enps.py (COMMENT_THEMES)")

# snapshot attributes at the wave open date
SNAP = ["company", "thread", "function", "job_family", "grade", "grade_num", "location", "location_type",
        "performance_rating", "compa_band", "manager_status", "joined_between_waves", "is_exited",
        "exit_type", "exit_classification", "is_regrettable_exit", "date_of_exit"]
for c in SNAP:
    r[c] = r["employee_id"].map(emp[c]) if c in emp.columns else None
r["tenure_band"] = [emp.at[i, f"tenure_band_{w.lower()}"] if i in emp.index else None for i, w in zip(r["employee_id"], r["wave"])]
r["exited_after_wave"] = r["date_of_exit"].notna() & (r["date_of_exit"] > r["wave"].map(lambda w: WAVES[w]["close"]))
dq.log(RS, "(segment attributes)", "Attributes snapshotted at wave open date", int(r["is_valid"].sum()),
       "Tenure band computed at each wave's open date; thread/function/grade/location/rating/compa band taken from the current HRMS record",
       "The HRMS export has no attribute history, so current values stand in for the wave-date values")
valid = r[r["is_valid"]]
both = valid.groupby("employee_id")["wave"].nunique()
r["in_panel"] = r["employee_id"].isin(both[both == 2].index) & r["is_valid"]
dq.step(RS, "rows out: valid responses", int(r["is_valid"].sum()), f"Apr {int((valid.wave == 'Apr').sum())}, Oct {int((valid.wave == 'Oct').sum())}")

RESP_COLS = ["response_id", "employee_id", "wave", "submitted_on", "q1_raw", "q1_clean", "nps_group",
             "q2", "q3", "q4", "q5", "q6", "comment", "comment_theme", "is_valid", "exclusion_reason", "in_panel",
             "tenure_band"] + SNAP + ["exited_after_wave"]
r = r[RESP_COLS].sort_values(["wave", "submitted_on"]).reset_index(drop=True)

# ═════════════════════════════════════════════════════════════════════════════
# write
# ═════════════════════════════════════════════════════════════════════════════
CLEAN_DIR.mkdir(parents=True, exist_ok=True)
e.to_parquet(CLEAN_DIR / "employees.parquet", index=False)
r.to_parquet(CLEAN_DIR / "survey_responses.parquet", index=False)
pb.to_parquet(CLEAN_DIR / "pay_bands.parquet", index=False)
dq.write()

# console summary (numbers for the checkpoint; the official reference is metric_reference.md in Phase 4)
print(f"employees.parquet        {len(e):>5} rows  (raw {len(raw)})")
print(f"survey_responses.parquet {len(r):>5} rows  ({int(r.is_valid.sum())} valid)")
print(f"pay_bands.parquet        {len(pb):>5} rows")
print(f"dq_log rows (eNPS)       {len(dq.rows):>5}")
print("\nReconciliation:")
for s in dq.recon:
    print(f"  {s['sheet']:<16} {s['order']:>2}. {s['step']:<40} {s['rows']:>5}  {s['change'] if s['change'] != '' else ''}")
print("\nmanager_status:", e["manager_status"].value_counts().to_dict(), "| literal:", int(e["manager_changed_literal"].sum()))
print("\nCheckpoint numbers:")
for w in ["Apr", "Oct"]:
    v = r[r.is_valid & (r.wave == w)]
    n = len(v)
    p, d = (v.nps_group == "Promoter").mean() * 100, (v.nps_group == "Detractor").mean() * 100
    invited = int(e[f"active_on_{w.lower()}_open"].sum())
    print(f"  {w}: eNPS {p - d:+.1f}  (n={n}; promoters {p:.1f}%, detractors {d:.1f}%; invited {invited}; response rate {n / invited:.1%})")
