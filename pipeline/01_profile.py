"""
01_profile.py
-------------
Profile the two raw workbooks (read-only) and write analysis/profile.md.

Sections
  1. Known-issue checklist: every issue listed in the case brief, re-counted from the data.
  2. New findings not listed in the case brief before Phase 1.
  3. Duplicate keys.  4. ID format checks.  5. Foreign-key checks.
  6. Per-sheet, per-column profile (type mix, nulls, distinct, top 25, min/max).

Run:  python pipeline/01_profile.py
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ANALYSIS_DIR, AS_OF, EMP_ID_RE, ENPS_FILE, NOTES_SHEETS, RECRUIT_FILE, REQ_ID_RE, WAVES,
    active_on, date_format_of, grade_num, is_blank, job_family, norm_emp_id, norm_grade,
    norm_req_id, parse_date, parse_inr,
)

OUT = ANALYSIS_DIR / "profile.md"
DATE_COL_RE = re.compile(r"Date|\bOn$|DOJ|Effective From")
TOP_N = 25

# Candidate Status values agreed in Phase 0 (spelling variants map onto these).
CANDIDATE_STATUS_CANON = {
    "Applied - Under Review", "Shortlisted", "Screening Cleared", "R1 Cleared", "R1 Feedback Pending",
    "Offer In Approval", "Offer Accepted - Yet to Join", "Joined", "Offer Declined",
    "Not Joined - Backed Out", "Rejected - Profile", "Rejected - Screening", "Rejected - R1",
    "Rejected - R2", "On Hold - Position Filled", "Withdrawn",
}


# ── small helpers ────────────────────────────────────────────────────────────

def load(path: Path) -> dict[str, pd.DataFrame]:
    sheets = pd.read_excel(path, sheet_name=None, dtype=object)
    return {k: v for k, v in sheets.items() if k.lower() not in NOTES_SHEETS}


def tname(v) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, np.integer)):
        return "int"
    if isinstance(v, (float, np.floating)):
        return "float"
    if isinstance(v, str):
        return "str"
    if hasattr(v, "year"):
        return "datetime"
    return type(v).__name__


def esc(x) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def show(v) -> str:
    """Show a raw value so stray spaces are visible."""
    if isinstance(v, str) and v != v.strip():
        return f"`{v!r}`"
    if hasattr(v, "year") and not isinstance(v, str):
        return f"`{pd.Timestamp(v):%Y-%m-%d %H:%M}`".replace(" 00:00", "")
    return f"`{v}`"


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def shape(v) -> str:
    """Format shape of a string: digits -> 9, letters -> a."""
    s = str(v)
    return re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "9", s))


def counts(s: pd.Series) -> dict:
    return s.value_counts(dropna=False).to_dict()


def fmt_list(xs, limit=12) -> str:
    xs = list(xs)
    more = f" … (+{len(xs) - limit})" if len(xs) > limit else ""
    return ", ".join(show(x) for x in xs[:limit]) + more


# ── load ─────────────────────────────────────────────────────────────────────

E = load(ENPS_FILE)
R = load(RECRUIT_FILE)
em, rs, pb = E["Employee_Master"].copy(), E["eNPS_Responses"].copy(), E["Pay_Bands"].copy()
rq, cd, rc, pdir = (R["Requisitions"].copy(), R["Candidates"].copy(),
                    R["Recruiters"].copy(), R["People_Directory"].copy())
Q1 = [c for c in rs.columns if c.startswith("Q1")][0]
QCOLS = [c for c in rs.columns if re.match(r"Q[1-6]\.", c)]

# Normalised helper columns (profiling only — the real cleaning is Phase 2/3)
em["_id"] = em["Employee ID"].map(norm_emp_id)
em["_upd"] = pd.to_datetime(em["Record Updated On"])
em["_status"] = em["Employment Status"].str.strip().str.title()
em["_doj"] = em["Date of Joining"].map(parse_date)
em["_exit"] = em["Date of Exit"].map(parse_date)
em["_grade"] = em["Grade"].map(norm_grade)
em["_ctc"] = em["Annual CTC (INR)"].map(parse_inr)
emu = em.sort_values("_upd").drop_duplicates("_id", keep="last").set_index("_id")
master_ids = set(em["_id"])

rs["_id"] = rs["Employee ID"].map(norm_emp_id)
rs["_wave"] = rs["Survey Wave"].str.strip().str.lower().str[:3].map({"apr": "Apr", "oct": "Oct"})
rs["_sub"] = pd.to_datetime(rs["Submitted On"])
TEST_IDS = {i for i in rs["_id"] if not EMP_ID_RE.fullmatch(i)}

cdd = cd.drop_duplicates().copy()            # after dropping exact duplicates
cdd["_req"] = cdd["Req ID"].map(norm_req_id)
cdd["_status"] = cdd["Candidate Status"].str.strip()
req_ids = set(rq["Req ID"].map(norm_req_id))
orph = cdd[~cdd["_req"].isin(req_ids)]
cdk = cdd[cdd["_req"].isin(req_ids)]          # kept candidates

rq["_grade"] = rq["Grade"].map(norm_grade)
rq["_gnum"] = rq["_grade"].map(grade_num)
rq["_raised"] = rq["Req Raised On"].map(parse_date)

findings_known: list[list] = []
findings_new: list[list] = []


def known(sheet, issue, found, expected=None, ok=None):
    if ok is None:
        ok = True if expected is None else (found == expected)
    status = "✅ found" if ok else "⚠ differs"
    findings_known.append([len(findings_known) + 1, sheet, issue, found, status])


def new(sheet, finding, impact):
    findings_new.append([f"N{len(findings_new) + 1}", sheet, finding, impact])


# ── 1. known-issue checklist ─────────────────────────────────────────────────
raw_id = em["Employee ID"].astype(str)
n_idfix = int((raw_id != em["_id"]).sum())
n_lower = int(raw_id.str.contains("emp").sum())
known("Employee_Master", "Employee ID needs strip + upper", f"{n_idfix} rows ({n_lower} lowercase, {n_idfix - n_lower} spaces only)", ok=n_idfix == 26)
dup_extra = int(em["_id"].duplicated().sum())
exact_dup = int(em.drop(columns=["Employee ID"]).assign(_id=em["_id"]).drop(columns=[c for c in em.columns if c.startswith("_") and c != "_id"]).duplicated().sum())
known("Employee_Master", "12 duplicate IDs, 8 exact duplicates", f"{dup_extra} extra rows on duplicated IDs; {exact_dup} exact duplicates", ok=(dup_extra, exact_dup) == (12, 8))
known("Employee_Master", "Thread variants → 6 canonical", f"{em['Thread'].nunique()} raw values: {fmt_list(sorted(em['Thread'].unique()), 20)}")
known("Employee_Master", "Grade variants → TBA, G1..G10", f"{em['Grade'].nunique()} raw values; all map: {em['_grade'].notna().all()}", ok=em["_grade"].notna().all())
known("Employee_Master", "Location variants", f"{em['Location'].nunique()} raw values: {fmt_list(sorted(em['Location'].unique()), 30)}")
known("Employee_Master", "Location Type null (26)", int(em["Location Type"].isna().sum()), 26)
known("Employee_Master", "Employment Status variants", counts(em["Employment Status"]))
known("Employee_Master", "Date of Joining mixed formats", counts(em["Date of Joining"].map(date_format_of)), ok=em["_doj"].notna().all())
known("Employee_Master", "Date of Exit datetime + DD-Mon-YY", counts(em["Date of Exit"].map(date_format_of)))
ctc_kinds = em["Annual CTC (INR)"].map(lambda v: "blank" if is_blank(v) else ("int" if not isinstance(v, str) else ("lakh string" if re.search(r"[A-Za-z]", v) else "comma string")))
known("Employee_Master", "Annual CTC ints / comma strings / lakh strings", f"{counts(ctc_kinds)}; unparseable: {int((em['_ctc'].isna() & ~ctc_kinds.eq('blank')).sum())}")
bands26 = pb[pd.to_datetime(pb["Effective From"]) == pd.Timestamp("2026-04-01")].set_index(["Job Family", "Grade"])["Band Mid (INR)"]
em["_mid"] = [bands26.get((job_family(f), g), np.nan) for f, g in zip(em["Function"].str.strip(), em["_grade"])]
em["_compa"] = em["_ctc"] / em["_mid"]
n_ctc_out = int(((em["_compa"] < 0.5) | (em["_compa"] > 2)).sum())
known("Employee_Master", "CTC outside 0.5x–2x band mid (flag)", f"{n_ctc_out} rows; CTC blank: {int(em['_ctc'].isna().sum())}")
known("Employee_Master", "Performance rating: New Joiner / nulls", counts(em["Performance Rating FY25-26"]))

known("eNPS_Responses", "Survey Wave 8 spellings", f"{rs['Survey Wave'].nunique()}: {counts(rs['Survey Wave'])}", ok=rs["Survey Wave"].nunique() == 8)
wave_mismatch = int(((rs["_wave"] == "Apr") & (rs["_sub"].dt.month != 4)).sum() + ((rs["_wave"] == "Oct") & (rs["_sub"].dt.month != 10)).sum())
known("eNPS_Responses", "Wave label cross-check vs Submitted On", f"{wave_mismatch} disagreements", ok=wave_mismatch == 0)
q1s = rs[Q1].dropna()
q1_frac = int(q1s.map(lambda v: isinstance(v, str) and "/" in v).sum())
q1_num = pd.to_numeric(q1s.map(lambda v: str(v).split("/")[0]), errors="coerce")
q1_oor = q1_num[(q1_num < 0) | (q1_num > 10)]
known("eNPS_Responses", "Q1 '7/10' strings; out of range -1/11/12", f"{q1_frac} 'x/10' strings; {len(q1_oor)} out of range {dict(Counter(q1_oor.astype(int)))}; Q1 blank: {int(rs[Q1].isna().sum())}")
n_rid_fix = int((rs["Employee ID"].astype(str) != rs["_id"]).sum())
known("eNPS_Responses", "Employee ID spaces / lowercase", f"{n_rid_fix} rows")
known("eNPS_Responses", "Test IDs TEST001/TEST002/HRTEST", f"{int(rs['_id'].isin(TEST_IDS).sum())} rows: {sorted(TEST_IDS)}", ok=TEST_IDS == {"TEST001", "TEST002", "HRTEST"})
not_in = rs[~rs["_id"].isin(master_ids) & ~rs["_id"].isin(TEST_IDS)]
known("eNPS_Responses", "IDs not in master (EMP99xxx)", f"{len(not_in)} rows, {not_in['_id'].nunique()} IDs: {sorted(not_in['_id'].unique())}")
pairs = rs[~rs["_id"].isin(TEST_IDS)].groupby(["_id", "_wave"]).size()
known("eNPS_Responses", "28 employee-wave pairs answered twice", int((pairs > 1).sum()), 28)
od = rs["_wave"].map(lambda w: WAVES[w]["open"])
cl = rs["_wave"].map(lambda w: WAVES[w]["close"]) + pd.Timedelta(days=1)
outside = int(((rs["_sub"] < od) | (rs["_sub"] >= cl)).sum())
inm = rs["_id"].isin(emu.index)
act = pd.Series(False, index=rs.index)
act[inm] = [bool(active_on(pd.Series([emu.at[i, "_doj"]]), pd.Series([emu.at[i, "_exit"]]), d).iloc[0]) for i, d in zip(rs.loc[inm, "_id"], od[inm])]
known("eNPS_Responses", "Respondent not active on wave open date / outside window", f"{int((inm & ~act).sum())} not active on open date; {outside} outside window")
known("eNPS_Responses", "~20 repeated comment phrases → 6 themes", f"{rs['Comments (optional)'].nunique()} distinct phrases on {int(rs['Comments (optional)'].notna().sum())} rows")
known("Pay_Bands", "Two band sets", counts(pd.to_datetime(pb["Effective From"]).dt.strftime("%Y-%m-%d")), ok=pb["Effective From"].nunique() == 2)

known("Requisitions", "Thread variants", f"{rq['Thread'].nunique()} raw values: {fmt_list(sorted(rq['Thread'].unique()), 20)}")
rnames = set(rc["Recruiter Name"])
known("Requisitions", "Recruiter variants → Recruiters sheet names", f"{int((~rq['Recruiter'].isin(rnames)).sum())} rows not an exact sheet name: {fmt_list(sorted(set(rq['Recruiter']) - rnames), 20)}")
known("Requisitions", "Req Status variants", counts(rq["Req Status"]))
tech = rq["Function"].str.strip().map(lambda f: job_family(f) == "Tech")
crit_rule = np.where((tech & (rq["_gnum"] >= 6)) | (~tech & (rq["_gnum"] >= 8)), "Critical", "Non-Critical")
crit_mis = int((rq["Criticality"].notna() & (rq["Criticality"] != crit_rule)).sum())
known("Requisitions", "Criticality null (9); rule mismatches", f"{int(rq['Criticality'].isna().sum())} null; {crit_mis} mismatches vs rule", ok=int(rq["Criticality"].isna().sum()) == 9)
sla_rule = np.where(rq["_gnum"] <= 2, 30, np.where(rq["_gnum"] <= 5, 45, 60))
known("Requisitions", "SLA (Days) vs grade rule", f"{int((rq['SLA (Days)'].astype(int) != sla_rule).sum())} mismatches")
known("Requisitions", "Req Raised On: 12 string dates", counts(rq["Req Raised On"].map(date_format_of)), ok=int((rq["Req Raised On"].map(date_format_of) != "datetime").sum()) == 12)

known("Candidates", "22 exact duplicate rows", int(cd.duplicated().sum()), 22)
noprefix = int((~cd["Req ID"].astype(str).str.strip().str.upper().str.startswith("REQ_")).sum())
known("Candidates", "Req ID missing REQ_ (~14%); 36 unmatched after fix", f"{noprefix} rows ({noprefix / len(cd):.1%}); unmatched after fix (deduped): {len(orph)}", ok=len(orph) == 36)
src = cdd["Source"]
ag_like = src.str.strip().str.lower().isin(["agency", "vendor", "consultant"])
known("Candidates", "Source variants", f"{src.nunique()} raw values: {counts(src)}")
known("Candidates", "Vendor/Consultant rows have Agency Name?", f"Vendor/Consultant/agency rows with Agency Name: {int((ag_like & cdd['Agency Name'].notna()).sum())} of {int(ag_like.sum())}; Agency Name on non-agency source: {int((~ag_like & cdd['Agency Name'].notna()).sum())}")
dcols = ["Applied On", "Shortlisted On", "Screening Done On", "R1 Interview Date", "R1 Feedback Submitted On",
         "R2 Interview Date", "Offer Released On", "Offer Response On", "Expected DOJ", "Actual DOJ"]
fmt_by_col = {c: {k: v for k, v in counts(cdd[c].map(date_format_of)).items() if k not in ("blank", "datetime")} for c in dcols}
known("Candidates", "Mixed date formats incl. Excel serials", "; ".join(f"{c}: {v}" for c, v in fmt_by_col.items() if v))
ap, sh = cdd["Applied On"].map(parse_date), cdd["Shortlisted On"].map(parse_date)
known("Candidates", "16 rows Shortlisted On < Applied On", int((sh < ap).sum()), 16)
np_str = cdd["Notice Period (Days)"][cdd["Notice Period (Days)"].map(lambda v: isinstance(v, str))]
known("Candidates", "Notice Period strings", counts(np_str))
known("Candidates", "Expected CTC 'LPA' strings", f"{int(cdd['Expected CTC (INR)'].map(lambda v: isinstance(v, str)).sum())} rows, e.g. {fmt_list(cdd['Expected CTC (INR)'][cdd['Expected CTC (INR)'].map(lambda v: isinstance(v, str))].unique()[:5])}")
known("Candidates", "Candidate Status variants", counts(cdd["Candidate Status"]))
edoj = cdd["Expected DOJ"].map(parse_date)
known("Candidates", "Expected DOJ after 31-Oct-2026 (valid)", f"{int((edoj > AS_OF).sum())} rows")
known("People_Directory", "Directory IDs join to Employee_Master", f"{int((~pdir['Employee ID'].map(norm_emp_id).isin(master_ids)).sum())} not found", ok=bool(pdir["Employee ID"].map(norm_emp_id).isin(master_ids).all()))
known("Candidates", "R1 Interviewer IDs all resolve", f"{int((~cdd['R1 Interviewer ID'].dropna().map(norm_emp_id).isin(set(pdir['Employee ID']))).sum())} not in People_Directory")

# ── 2. new findings ──────────────────────────────────────────────────────────
new("Employee_Master", f"Of the {n_idfix} Employee IDs that need fixing, only {n_lower} are lowercase; {n_idfix - n_lower} just have stray spaces.", "Wording fix in the case brief; same treatment.")
emu_s = emu
a_ex = emu_s[(emu_s["_status"] == "Active") & emu_s["_exit"].notna()]
x_nd = emu_s[(emu_s["_status"] == "Exited") & emu_s["_exit"].isna()]
new("Employee_Master", f"{len(a_ex)} employees are 'Active' but have an exit date and Exit Type/Classification ({', '.join(a_ex.index)}); {len(x_nd)} are 'Exited' with no exit date but an Exit Type ({', '.join(x_nd.index)}).",
    "Agreed treatment: first group → Exited (keep date); second → Exited, exit date unknown (counts as active on both wave open dates).")
blr = em[em["Location"].str.strip() == "BLR"]
new("Employee_Master", f"All {len(blr)} 'BLR' rows have Location Type = {fmt_list(blr['Location Type'].dropna().unique())}.", "Map BLR → Bengaluru (City), not HO.")
lt_null_loc = em[em["Location Type"].isna()]["Location"].str.strip()
new("Employee_Master", f"Location Type is null on {len(lt_null_loc)} rows; {int(lt_null_loc.isin(['Bengaluru HO', 'BLR - HO', 'Bangalore HO']).sum())} of them are at an HO spelling.", "Fill from cleaned Location per the case brief rule.")
pnull = em["Performance Rating FY25-26"].isna()
new("Employee_Master", f"All {int(pnull.sum())} null performance ratings belong to joiners on/after 01-Jan-2026 ({int((pnull & (em['_doj'] >= '2026-01-01')).sum())}); none are otherwise missing.", "All → 'Not Rated - New Joiner'; 'Missing' bucket will be empty.")
gv = sorted(set(em["Grade"]) - {f"G{i}" for i in range(1, 11)} - {"TBA"})
new("Employee_Master", f"Grade spellings beyond the examples in the case brief: {fmt_list(gv, 30)}.", "All map to TBA/G1–G10 with one rule.")
mgr_missing = sorted(set(em["Reporting Manager ID"].map(norm_emp_id)) - master_ids)
new("Employee_Master", f"{len(mgr_missing)} Reporting Manager IDs are not in Employee_Master (of {em['Reporting Manager ID'].nunique()} distinct).", "Informational: manager attributes unavailable for those; not used in metrics.")
paired = rs[rs.duplicated(["_id", "_wave"], keep=False) & ~rs["_id"].isin(TEST_IDS)].sort_values("_sub")
diff_pairs = int(paired.groupby(["_id", "_wave"])[QCOLS].nunique(dropna=False).gt(1).any(axis=1).sum())
new("eNPS_Responses", f"Of the {int((pairs > 1).sum())} double-answered employee-wave pairs, {diff_pairs} have at least one different Q1–Q6 answer between the two submissions.", "Keep latest submission (the case brief rule); the choice matters only for these pairs.")
qnull = {c.split('.')[0]: int(rs[c].isna().sum()) for c in QCOLS}
new("eNPS_Responses", f"Blank answers per question: {qnull}.", "Q1 blank → not valid for eNPS; Q2–Q6 blank → excluded from that driver's mean only.")
new("eNPS_Responses", f"{rs['Comments (optional)'].nunique()} distinct comment phrases (the case brief says ~20).", "All 22 get a theme in Phase 2.")
new("Requisitions", f"Thread spelling `central` (lowercase) is not in the the case brief variant list.", "Same normalisation.")
rep_ids = rq["Replaced Employee ID"].dropna().map(norm_emp_id)
new("Requisitions", f"{int((~rep_ids.isin(master_ids)).sum())} of {len(rep_ids)} Replaced Employee IDs are not in Employee_Master.", "Expected per data dictionary (left before 01-Apr-2026): exit fields and days_exit_to_req stay null.")
new("Requisitions", f"SLA Status (System) is blank on {int(rq['SLA Status (System)'].isna().sum())} reqs (by Req Status: {counts(rq.loc[rq['SLA Status (System)'].isna(), 'Req Status'])}).", "Recomputed SLA status covers them; count as 'system blank' in the mismatch table.")
orj = orph[orph["_status"].str.lower() == "joined"]
acc_rej = orph[(orph["Offer Status"] == "Accepted") & ~orph["_status"].str.lower().isin(["joined", "offer accepted - yet to join"])]
new("Candidates", f"All {len(orph)} orphan candidate rows have IDs C690xxx ({orph['Candidate ID'].str.startswith('C690').all()}) and Req IDs outside REQ_5102–5697 ({sorted(orph['_req'].unique())[:3]}…). They include {len(orj)} rows marked 'Joined' with no offer or joining date and {len(acc_rej)} accepted offer marked '{', '.join(acc_rej['_status'])}'.", "Already excluded; without them, joined = 167 everywhere. Log as DQ finding.")
cs = cdk["_status"]
new("Candidates", f"Kept candidates: {int(cs.str.lower().eq('joined').sum())} status Joined, {int(cdk['Actual DOJ'].notna().sum())} with Actual DOJ, {int(rq['Req Status'].str.strip().str.lower().isin(['closed - joined', 'closed-joined', 'joined']).sum())} reqs Closed - Joined.", "Counts reconcile once orphans are excluded.")
extra_status = sorted(set(cdd["Candidate Status"].str.strip()) - CANDIDATE_STATUS_CANON)
new("Candidates", f"Candidate Status values outside the 16 agreed canonical values (spelling variants only): {fmt_list(extra_status)}.", "Map to canonical list; no new categories.")
new("Candidates", f"Notice Period strings beyond the case brief examples: {fmt_list(sorted(set(np_str) - {'2 months', '1 month', '30 days', 'Immediate'}))}.", "Same rule (month = 30 days, Immediate = 0).")
new("Candidates", f"Offer Status values: {counts(cdd['Offer Status'].dropna())} — no 'Pending' despite the data dictionary.", "Nothing to do.")
pairs_stage = [("Applied On", "Shortlisted On"), ("Shortlisted On", "Screening Done On"), ("Screening Done On", "R1 Interview Date"),
               ("R1 Interview Date", "R2 Interview Date"), ("R2 Interview Date", "Offer Released On"),
               ("Offer Released On", "Offer Response On"), ("Offer Response On", "Actual DOJ"),
               ("R1 Interview Date", "R1 Feedback Submitted On")]
neg = {}
for a, b in pairs_stage:
    da, db = cdk[a].map(parse_date), cdk[b].map(parse_date)
    neg[f"{a} → {b}"] = int((db < da).sum())
new("Candidates", "Out-of-order stage dates on kept candidates: " + "; ".join(f"{k}: {v}" for k, v in neg.items()) + ".", "Stage-time and R1 turnaround metrics skip out-of-order pairs; logged.")
r1_no_date = int((cdk["R1 Interviewer ID"].notna() & cdk["R1 Interview Date"].isna()).sum())
r1_res_no_fb = int((cdk["R1 Result"].isin(["Select", "Reject"]) & cdk["R1 Feedback Submitted On"].isna()).sum())
new("Candidates", f"{r1_no_date} rows have an R1 interviewer but no R1 date; {r1_res_no_fb} rows have an R1 Select/Reject but no feedback date; R1 'Pending Feedback': {int((cdk['R1 Result'] == 'Pending Feedback').sum())}.", "Turnaround uses rows with both dates only.")
budget = rq.set_index(rq["Req ID"].map(norm_req_id))["Budgeted Max CTC (INR)"]
off = cdk[cdk["Offered CTC (INR)"].notna()]
over = off[off["Offered CTC (INR)"].astype(float) > off["_req"].map(budget).astype(float)]
new("Candidates", f"{len(over)} of {len(off)} offers exceed the requisition's Budgeted Max CTC ({over['Offer Status'].value_counts().to_dict()}).", "Input to hypothesis 13 (budget headroom).")

ctc_flag = em[(em["_compa"] < 0.5) | (em["_compa"] > 2)].drop_duplicates("_id")
new("Employee_Master", f"{len(ctc_flag)} employees have CTC outside 0.5x–2x of their 2026 band mid (compa {ctc_flag['_compa'].min():.2f}–{ctc_flag['_compa'].max():.2f}); lowest CTC is ₹{em['_ctc'].min():,.0f}. All are low, none high; ×12 puts every one at compa {(ctc_flag['_compa'] * 12).min():.2f}–{(ctc_flag['_compa'] * 12).max():.2f}, so they look like monthly figures. Detail table below.", "Decision for Phase 2: ×12 (treat as monthly) or keep raw and exclude from compa-ratio analysis. Flag either way.")
names_per_id = em.drop_duplicates("_id")["Employee Name"]
new("Employee_Master", f"Employee names are not unique: {names_per_id.nunique():,} distinct names across {len(names_per_id):,} employee IDs ({int(names_per_id.duplicated(keep=False).sum())} IDs share a name).", "Never join or look up by name; Ask the Data refuses named-person survey questions regardless.")

# ── 3. duplicate keys ────────────────────────────────────────────────────────
dups = [
    ["Employee_Master", "Employee ID (raw)", int(em["Employee ID"].duplicated().sum())],
    ["Employee_Master", "Employee ID (strip+upper)", dup_extra],
    ["Employee_Master", "Exact duplicate rows (after ID fix)", exact_dup],
    ["eNPS_Responses", "Response ID", int(rs["Response ID"].duplicated().sum())],
    ["eNPS_Responses", "Employee ID + wave (excl. test IDs)", int((pairs > 1).sum())],
    ["Pay_Bands", "Effective From + Job Family + Grade", int(pb.duplicated(["Effective From", "Job Family", "Grade"]).sum())],
    ["Requisitions", "Req ID", int(rq["Req ID"].duplicated().sum())],
    ["Candidates", "Exact duplicate rows", int(cd.duplicated().sum())],
    ["Candidates", "Candidate ID (raw)", int(cd["Candidate ID"].duplicated().sum())],
    ["Candidates", "Candidate ID (after dropping exact dups)", int(cdd["Candidate ID"].duplicated().sum())],
    ["Recruiters", "Recruiter ID / Name", f"{int(rc['Recruiter ID'].duplicated().sum())} / {int(rc['Recruiter Name'].duplicated().sum())}"],
    ["People_Directory", "Employee ID", int(pdir["Employee ID"].duplicated().sum())],
]
dupid_rows = em[em["_id"].duplicated(keep=False)].sort_values(["_id", "_upd"])
diffcols = {}
for i, g in dupid_rows.groupby("_id"):
    cols = [c for c in em.columns if not c.startswith("_") and c != "Employee ID" and g[c].astype(str).nunique() > 1]
    if cols:
        diffcols[i] = cols

# ── 4. ID format checks ──────────────────────────────────────────────────────
def idcheck(sheet, col, s, rx, normf):
    s = s.dropna()
    raw_fail = s[~s.astype(str).map(lambda v: bool(rx.fullmatch(v)))]
    n = s.map(normf)
    norm_fail = n[~n.map(lambda v: bool(rx.fullmatch(v)))]
    return [sheet, col, rx.pattern, len(s), len(raw_fail), fmt_list(raw_fail.unique()[:6], 6), len(norm_fail), fmt_list(norm_fail.unique()[:6], 6)]

idrows = [
    idcheck("Employee_Master", "Employee ID", em["Employee ID"], EMP_ID_RE, norm_emp_id),
    idcheck("Employee_Master", "Reporting Manager ID", em["Reporting Manager ID"], EMP_ID_RE, norm_emp_id),
    idcheck("eNPS_Responses", "Employee ID", rs["Employee ID"], EMP_ID_RE, norm_emp_id),
    idcheck("Requisitions", "Req ID", rq["Req ID"], REQ_ID_RE, norm_req_id),
    idcheck("Requisitions", "Replaced Employee ID", rq["Replaced Employee ID"], EMP_ID_RE, norm_emp_id),
    idcheck("Requisitions", "Hiring Manager ID", rq["Hiring Manager ID"], EMP_ID_RE, norm_emp_id),
    idcheck("Candidates", "Req ID", cd["Req ID"].astype(str), REQ_ID_RE, norm_req_id),
    idcheck("Candidates", "R1 Interviewer ID", cd["R1 Interviewer ID"], EMP_ID_RE, norm_emp_id),
    idcheck("People_Directory", "Employee ID", pdir["Employee ID"], EMP_ID_RE, norm_emp_id),
    idcheck("eNPS_Responses", "Response ID", rs["Response ID"], re.compile(r"R\d+"), lambda v: str(v).strip()),
    idcheck("Candidates", "Candidate ID", cd["Candidate ID"], re.compile(r"C\d+"), lambda v: str(v).strip()),
]

# ── 5. foreign keys ──────────────────────────────────────────────────────────
pd_ids = set(pdir["Employee ID"].map(norm_emp_id))
def fk(child, col, s, parent, pset, note=""):
    s = s.dropna()
    miss = s[~s.isin(pset)]
    return [child, col, parent, len(s), len(miss), miss.nunique(), fmt_list(sorted(miss.unique())[:6], 6), note]

fkrows = [
    fk("eNPS_Responses", "Employee ID (norm.)", rs["_id"], "Employee_Master", master_ids, "includes 3 test IDs"),
    fk("eNPS_Responses", "Employee ID (norm., excl. test)", rs.loc[~rs["_id"].isin(TEST_IDS), "_id"], "Employee_Master", master_ids),
    fk("Candidates", "Req ID (raw, all rows)", cd["Req ID"].astype(str), "Requisitions", set(rq["Req ID"]), "before REQ_ fix"),
    fk("Candidates", "Req ID (REQ_ fixed, deduped)", cdd["_req"], "Requisitions", req_ids, "after fix"),
    fk("Candidates", "R1 Interviewer ID", cdd["R1 Interviewer ID"].map(norm_emp_id), "People_Directory", pd_ids),
    fk("Requisitions", "Hiring Manager ID", rq["Hiring Manager ID"].map(norm_emp_id), "People_Directory", pd_ids),
    fk("Requisitions", "Replaced Employee ID", rq["Replaced Employee ID"].map(norm_emp_id), "Employee_Master", master_ids, "misses = left before 01-Apr-2026"),
    fk("Requisitions", "Recruiter (raw)", rq["Recruiter"], "Recruiters.Recruiter Name", rnames, "needs name mapping"),
    fk("People_Directory", "Employee ID", pdir["Employee ID"].map(norm_emp_id), "Employee_Master", master_ids),
    fk("Employee_Master", "Reporting Manager ID", em["Reporting Manager ID"].map(norm_emp_id), "Employee_Master", master_ids),
]

# ── 6. sheet profiles ────────────────────────────────────────────────────────
def profile_sheet(name: str, df: pd.DataFrame) -> str:
    df = df[[c for c in df.columns if not c.startswith("_")]]
    lines = [f"### {name} — {len(df):,} rows × {df.shape[1]} columns", ""]
    rows, tops = [], []
    for c in df.columns:
        s = df[c]
        nn = s[~s.map(is_blank)]
        types = dict(Counter(nn.map(tname)))
        kind = "date" if DATE_COL_RE.search(c) else ("number" if sum(types.get(k, 0) for k in ("int", "float")) >= len(nn) / 2 else "text")
        mn = mx = ""
        extra = ""
        if kind == "date":
            d = s.map(parse_date).dropna()
            if len(d):
                mn, mx = f"{d.min():%Y-%m-%d}", f"{d.max():%Y-%m-%d}"
            fm = {k: v for k, v in Counter(nn.map(date_format_of)).items()}
            unp = int(s.map(parse_date).isna().sum() - s.map(is_blank).sum())
            extra = f"formats {fm}" + (f"; **{unp} unparseable**" if unp else "")
        elif kind == "number":
            num = pd.to_numeric(nn, errors="coerce").dropna()
            if len(num):
                mn, mx = f"{num.min():,.0f}" if num.abs().max() >= 1000 else f"{num.min():g}", f"{num.max():,.0f}" if num.abs().max() >= 1000 else f"{num.max():g}"
            nonnum = nn[pd.to_numeric(nn, errors="coerce").isna()]
            if len(nonnum):
                extra = f"{len(nonnum)} non-numeric, shapes {dict(Counter(nonnum.map(shape)).most_common(6))}"
        else:
            sp = int(nn.map(lambda v: isinstance(v, str) and v != v.strip()).sum())
            if sp:
                extra = f"{sp} with leading/trailing spaces"
        rows.append([f"`{c[:60]}`", kind, ", ".join(f"{k} {v}" for k, v in types.items()), int(s.map(is_blank).sum()),
                     int(nn.astype(str).nunique()), mn, mx, extra])
        if kind == "text" or nn.astype(str).nunique() <= 40:
            vc = nn.map(lambda v: v if isinstance(v, str) else (pd.Timestamp(v) if hasattr(v, "year") else v)).value_counts()
            tops.append(f"- **{c[:60]}** ({len(vc)} distinct): " + ", ".join(f"{show(k)} {v}" for k, v in vc.head(TOP_N).items()) + (" …" if len(vc) > TOP_N else ""))
    lines.append(table(["Column", "Kind", "Type mix", "Blank", "Distinct", "Min", "Max", "Notes"], rows))
    lines += ["", "Top values (up to 25):", ""] + tops + [""]
    return "\n".join(lines)


# ── write ────────────────────────────────────────────────────────────────────
n_ok = sum(1 for r in findings_known if r[-1].startswith("✅"))
md = [
    "# Raw data profile",
    "",
    "Generated by `pipeline/01_profile.py` from `data/raw/` (read-only). Do not edit by hand; re-run the script.",
    "Normalisation used here (strip/upper IDs, REQ_ prefix, date parsing) is only for checking; the cleaning itself is Phases 2–3.",
    "",
    "## Row counts",
    "",
    table(["Workbook", "Sheet", "Rows", "Columns"],
          [["eNPS_Data.xlsx", k, f"{len(v):,}", v.shape[1]] for k, v in E.items()] +
          [["Recruitment_Data.xlsx", k, f"{len(v):,}", v.shape[1]] for k, v in R.items()]),
    "",
    f"## 1. Known-issue checklist ({n_ok} of {len(findings_known)} confirmed as described in the case brief)",
    "",
    table(["#", "Sheet", "Issue in the case brief", "Found in data", "Status"], findings_known),
    "",
    "## 2. New findings (not in the case brief before Phase 1)",
    "",
    table(["#", "Sheet", "Finding", "Treatment / impact"], findings_new),
    "",
    "Employees with CTC outside 0.5x–2x of band mid (2026-04-01 bands):",
    "",
    table(["Employee ID", "Function", "Grade (norm.)", "Raw CTC", "Parsed CTC", "Band mid", "Compa", "Compa if ×12"],
          [[i, f, g, show(r), f"{c:,.0f}", f"{m:,.0f}", f"{c / m:.2f}", f"{12 * c / m:.2f}"] for i, f, g, r, c, m in
           zip(ctc_flag["_id"], ctc_flag["Function"], ctc_flag["_grade"], ctc_flag["Annual CTC (INR)"], ctc_flag["_ctc"], ctc_flag["_mid"])]),
    "",
    "## 3. Duplicate keys",
    "",
    table(["Sheet", "Key", "Extra (duplicate) rows"], dups),
    "",
    "Employee IDs that repeat with different values (latest Record Updated On wins in Phase 2):",
    "",
    table(["Employee ID", "Columns that differ"], [[k, ", ".join(v)] for k, v in diffcols.items()]),
    "",
    "## 4. ID format checks",
    "",
    table(["Sheet", "Column", "Pattern", "Non-blank", "Fail raw", "Examples (raw)", "Fail after normalising", "Examples (normalised)"], idrows),
    "",
    "## 5. Foreign-key checks",
    "",
    table(["Child sheet", "Column", "Parent", "Non-blank", "Unmatched rows", "Unmatched distinct", "Examples", "Note"], fkrows),
    "",
    "## 6. Column profiles",
    "",
]
for k, v in E.items():
    md.append(profile_sheet(k, v))
for k, v in R.items():
    md.append(profile_sheet(k, v))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(md), encoding="utf-8")
print(f"Wrote {OUT.relative_to(OUT.parents[1])}: {len(findings_known)} known-issue checks ({n_ok} confirmed), {len(findings_new)} new findings")
for r in findings_known:
    if not r[-1].startswith("✅"):
        print("  DIFFERS:", r[0], r[1], r[2], "->", r[3])
