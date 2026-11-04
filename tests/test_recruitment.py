"""Data checks for the cleaned recruitment workbook (Phase 3)."""
import pandas as pd
import pytest

from common import AS_OF, THREADS

SOURCES = {"Naukri", "LinkedIn", "Employee Referral", "Careers Page", "Internal (IJP)", "Agency"}
REQ_STATUSES = {"Open", "Offer Accepted", "Closed - Joined", "On Hold", "Archived"}
CAND_STATUSES = {"Applied - Under Review", "Shortlisted", "Screening Cleared", "R1 Cleared", "R1 Feedback Pending",
                 "Offer In Approval", "Offer Accepted - Yet to Join", "Joined", "Offer Declined",
                 "Not Joined - Backed Out", "Rejected - Profile", "Rejected - Screening", "Rejected - R1",
                 "Rejected - R2", "On Hold - Position Filled", "Withdrawn"}
STAGE_PAIRS = [("applied_on", "shortlisted_on", "days_applied_to_shortlisted"),
               ("shortlisted_on", "screening_done_on", "days_shortlisted_to_screening"),
               ("screening_done_on", "r1_interview_date", "days_screening_to_r1"),
               ("r1_interview_date", "r2_interview_date", "days_r1_to_r2"),
               ("r2_interview_date", "offer_released_on", "days_r2_to_offer"),
               ("offer_released_on", "offer_response_on", "days_offer_to_response"),
               ("offer_response_on", "actual_doj", "days_response_to_join")]


# ── the five checks named in the case brief ───────────────────────────────────────

def test_unique_candidate_id(rec):
    assert rec["cand"]["candidate_id"].is_unique


def test_kept_candidates_map_to_a_requisition(rec):
    assert rec["cand"]["req_id"].isin(rec["req"]["req_id"]).all()
    assert not rec["excl"]["req_id"].isin(rec["req"]["req_id"]).any()


@pytest.mark.parametrize("a,b,col", STAGE_PAIRS)
def test_stage_times_only_from_monotonic_dates(rec, a, b, col):
    c = rec["cand"]
    used = c[col].notna()
    assert (c.loc[used, b] >= c.loc[used, a]).all()
    assert (c.loc[used, col] == (c.loc[used, b] - c.loc[used, a]).dt.days).all()
    assert c.loc[c["stage_dates_invalid"], col].isna().all()


def test_one_hire_per_filled_req(rec):
    c, q = rec["cand"], rec["req"]
    hires = c[c["is_hire"]]
    assert hires["req_id"].is_unique
    assert set(hires["req_id"]) == set(q.loc[q["is_filled"], "req_id"])
    assert set(hires["candidate_id"]) == set(q["hired_candidate_id"].dropna())
    assert hires["is_offer_accepted"].all() and not hires["is_backed_out"].any()


def test_ttf_non_negative(rec):
    q = rec["req"]
    t = q["ttf_days"].dropna()
    assert len(t) == q["is_filled"].sum()
    assert (t >= 0).all()


# ── extra checks ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("col,allowed", [
    ("thread", set(THREADS)), ("req_status", REQ_STATUSES), ("criticality", {"Critical", "Non-Critical"}),
    ("position_type", {"New", "Replacement"}), ("job_family", {"Tech", "Non-Tech"}),
])
def test_req_categoricals(rec, col, allowed):
    v = rec["req"][col]
    assert v.notna().all() and set(v) <= allowed


def test_recruiters_resolve(rec):
    assert rec["req"]["recruiter"].isin(rec["rc"]["recruiter_name"]).all()
    assert rec["req"]["recruiter_id"].notna().all()


def test_candidate_categoricals(rec):
    c = rec["cand"]
    assert set(c["source_clean"]) <= SOURCES and c["source_clean"].notna().all()
    assert set(c["candidate_status"]) <= CAND_STATUSES and c["candidate_status"].notna().all()
    assert (c.loc[c["source_clean"] == "Agency", "agency_name"].notna()).all()


def test_sla_rules(rec):
    q = rec["req"]
    exp = q["grade_num"].map(lambda g: 30 if g <= 2 else 45 if g <= 5 else 60)
    assert (q["sla_expected"] == exp).all()
    f = q[q["is_filled"]]
    assert (f["sla_met"] == (f["ttf_days"] <= f["sla_days"])).all()
    o = q[q["is_open"]]
    assert (o["open_breached"] == ((AS_OF - o["req_raised_on"]).dt.days > o["sla_days"])).all()
    assert q.loc[~q["is_filled"] & ~q["is_open"], "sla_status_recomputed"].isna().all()


def test_criticality_rule(rec):
    q = rec["req"]
    rule = (((q["job_family"] == "Tech") & (q["grade_num"] >= 6)) | ((q["job_family"] == "Non-Tech") & (q["grade_num"] >= 8)))
    assert (q["criticality_derived"] == rule.map({True: "Critical", False: "Non-Critical"})).all()
    assert (q.loc[q["criticality_raw"].isna(), "criticality"] == q.loc[q["criticality_raw"].isna(), "criticality_derived"]).all()


def test_req_status_matches_hires(rec):
    q = rec["req"]
    assert (q.loc[q["hire_status"] == "Joined", "req_status"] == "Closed - Joined").all()
    assert (q.loc[q["hire_status"] == "Yet to Join", "req_status"] == "Offer Accepted").all()
    assert not q.loc[~q["is_filled"], "req_status"].isin(["Closed - Joined", "Offer Accepted"]).any()


def test_agency_fee(rec):
    c = rec["cand"]
    paid = c["agency_fee_inr"] > 0
    assert (c.loc[paid, "source_clean"] == "Agency").all() and c.loc[paid, "is_joined"].all()
    assert ((c.loc[paid, "agency_fee_inr"] - 0.0833 * c.loc[paid, "offered_ctc"]).abs() <= 0.5).all()
    assert (c.loc[(c["source_clean"] == "Agency") & c["is_joined"], "agency_fee_inr"] > 0).all()


def test_joined_counts_reconcile(rec):
    c, q = rec["cand"], rec["req"]
    assert c["is_joined"].sum() == c["actual_doj"].notna().sum() == (q["req_status"] == "Closed - Joined").sum()


def test_notice_and_expected_ctc_numeric(rec):
    c = rec["cand"]
    assert c["notice_days"].notna().all() and c["notice_days"].between(0, 180).all()
    assert c["expected_ctc_num"].notna().all() and (c["expected_ctc_num"] > 100_000).all()


def test_interviewers_and_managers_in_directory(rec):
    ids = set(rec["pdir"]["employee_id"])
    assert rec["cand"]["r1_interviewer_id"].dropna().isin(ids).all()
    assert rec["req"]["hiring_manager_id"].isin(ids).all()


def test_recruitment_reconciliation(rec):
    r = rec["recon"]
    r = r[r["dataset"] == "Recruitment"]
    for sheet, g in r.groupby("sheet"):
        g = g.sort_values("order")
        assert g["rows"].iloc[0] + pd.to_numeric(g["change"], errors="coerce").fillna(0).sum() == g["rows"].iloc[-1], sheet
    cand = r[r["sheet"] == "Candidates"].sort_values("order")
    assert cand["rows"].iloc[-1] == len(rec["cand"])
    assert cand["rows"].iloc[0] - cand["rows"].iloc[-1] == 22 + len(rec["excl"])


def test_dq_log_has_both_datasets(rec):
    assert {"eNPS", "Recruitment"} <= set(rec["dq"]["dataset"])


def test_backed_out_never_hires(rec):
    c, q = rec["cand"], rec["req"]
    bo = c[c["is_backed_out"]]
    assert not bo["is_hire"].any()
    filled_bo = q[q["req_id"].isin(bo["req_id"]) & q["is_filled"]]
    hires = c[c["is_hire"]].set_index("req_id")
    assert (~hires.loc[filled_bo["req_id"], "is_backed_out"]).all()


def test_agency_fee_only_joiners(rec):
    c = rec["cand"]
    yet = (c["source_clean"] == "Agency") & (c["candidate_status"] == "Offer Accepted - Yet to Join")
    assert (c.loc[yet, "agency_fee_inr"] == 0).all()
