"""Data checks for the cleaned eNPS workbook (Phase 2)."""
import pandas as pd
import pytest

from common import AS_OF, COMPA_BANDS, DQ_COLUMNS, TENURE_BANDS, WAVES

THREADS = {"Intracity", "Intercity", "Enterprise", "Packers & Movers", "Geo Expansion", "Central"}
LOCATIONS = {"Bengaluru HO", "Bengaluru", "Ahmedabad", "Chennai", "Delhi NCR", "Hyderabad", "Jaipur",
             "Kolkata", "Lucknow", "Mumbai", "Pune"}
GRADES = {"TBA"} | {f"G{i}" for i in range(1, 11)}
RATINGS = {"Game Changer", "High Impact Player", "Solid Performer", "Needs Improvement",
           "Below Expectations", "Not Rated - New Joiner", "Missing"}
MANAGER_STATUSES = {"Changed manager", "New joiner (first manager)", "Same manager"}
THEMES = {"Manager", "Pay", "Growth", "Workload", "Onboarding", "Positive"}


@pytest.fixture
def valid(enps):
    return enps["resp"][enps["resp"]["is_valid"]]


# ── the five checks named in the case brief ───────────────────────────────────────

def test_unique_employee_ids(enps):
    ids = enps["emp"]["employee_id"]
    assert ids.is_unique
    assert ids.str.fullmatch(r"EMP\d{5}").all()


def test_q1_in_range_for_valid_rows(valid):
    assert valid["q1_clean"].notna().all()
    assert valid["q1_clean"].between(0, 10).all()


def test_one_valid_response_per_employee_per_wave(valid):
    assert not valid.duplicated(["employee_id", "wave"]).any()


def test_every_valid_respondent_active_on_wave_open_date(enps, valid):
    emp = enps["emp"].set_index("employee_id")
    for wave in ["Apr", "Oct"]:
        ids = valid.loc[valid["wave"] == wave, "employee_id"]
        assert ids.isin(emp.index).all()
        assert emp.loc[ids, f"active_on_{wave.lower()}_open"].all(), wave


@pytest.mark.parametrize("col,allowed", [
    ("thread", THREADS), ("location", LOCATIONS), ("grade", GRADES),
    ("employment_status", {"Active", "Exited"}), ("location_type", {"HO", "City"}),
    ("performance_rating", RATINGS), ("compa_band", set(COMPA_BANDS)), ("job_family", {"Tech", "Non-Tech"}),
    ("company", {"Porter", "SmartShift Info Marketing Services Pvt Ltd"}),
    ("ctc_flag", {"ok", "missing", "corrected_monthly_x12", "out_of_band"}),
    ("manager_status", MANAGER_STATUSES),
])
def test_employee_categoricals_canonical(enps, col, allowed):
    vals = set(enps["emp"][col].dropna().unique())
    assert vals <= allowed, vals - allowed
    assert enps["emp"][col].notna().all()


@pytest.mark.parametrize("col,allowed", [
    ("wave", {"Apr", "Oct"}), ("nps_group", {"Promoter", "Passive", "Detractor"}),
    ("comment_theme", THEMES), ("tenure_band", set(TENURE_BANDS)), ("thread", THREADS),
    ("grade", GRADES), ("location", LOCATIONS), ("compa_band", set(COMPA_BANDS)),
    ("manager_status", MANAGER_STATUSES),
])
def test_survey_categoricals_canonical(valid, col, allowed):
    vals = set(valid[col].dropna().unique())
    assert vals <= allowed, vals - allowed


# ── extra safety checks ──────────────────────────────────────────────────────

def test_survey_has_no_names(enps):
    assert not any("name" in c.lower() for c in enps["resp"].columns)


def test_valid_submissions_inside_window(valid):
    for wave, wd in WAVES.items():
        s = valid.loc[valid["wave"] == wave, "submitted_on"]
        assert (s >= wd["open"]).all() and (s < wd["close"] + pd.Timedelta(days=1)).all()


def test_nps_group_matches_q1(valid):
    q = valid["q1_clean"]
    assert (valid.loc[q >= 9, "nps_group"] == "Promoter").all()
    assert (valid.loc[q.between(7, 8), "nps_group"] == "Passive").all()
    assert (valid.loc[q <= 6, "nps_group"] == "Detractor").all()


def test_drivers_in_range(valid):
    for q in ["q2", "q3", "q4", "q5", "q6"]:
        assert valid[q].dropna().between(1, 5).all(), q


def test_invalid_rows_have_one_reason(enps):
    r = enps["resp"]
    assert r.loc[~r["is_valid"], "exclusion_reason"].notna().all()
    assert r.loc[r["is_valid"], "exclusion_reason"].isna().all()


def test_reconciliation_adds_up(enps):
    rec = enps["recon"]
    for sheet, g in rec[rec["dataset"] == "eNPS"].groupby("sheet"):
        g = g.sort_values("order")
        assert g["rows"].iloc[0] + pd.to_numeric(g["change"], errors="coerce").fillna(0).sum() == g["rows"].iloc[-1], sheet
    resp = rec[(rec["dataset"] == "eNPS") & (rec["sheet"] == "eNPS_Responses")].sort_values("order")
    assert resp["rows"].iloc[-1] == enps["resp"]["is_valid"].sum()
    assert len(enps["resp"]) == resp["rows"].iloc[0]
    emp = rec[(rec["dataset"] == "eNPS") & (rec["sheet"] == "Employee_Master")].sort_values("order")
    assert emp["rows"].iloc[-1] == len(enps["emp"])


def test_exclusion_counts_match_log(enps):
    r = enps["resp"]
    rec = enps["recon"]
    steps = rec[(rec["dataset"] == "eNPS") & rec["step"].str.startswith("exclude: ")]
    for _, s in steps.iterrows():
        reason = s["step"].replace("exclude: ", "")
        assert (r["exclusion_reason"] == reason).sum() == -int(s["change"] or 0), reason


def test_dq_log_shape(enps):
    dq = enps["dq"]
    assert list(dq.columns) == DQ_COLUMNS
    e = dq[dq["dataset"] == "eNPS"]
    assert len(e) > 0 and e["treatment"].notna().all() and (e["rows_affected"] >= 0).all()


def test_compa_band_matches_ratio(enps):
    e = enps["emp"]
    cr = e["compa_ratio"]
    assert (e.loc[cr < 0.90, "compa_band"] == "Below").all()
    assert (e.loc[cr.between(0.90, 1.10), "compa_band"] == "At").all()
    assert (e.loc[cr > 1.10, "compa_band"] == "Above").all()
    assert (e.loc[cr.isna(), "compa_band"] == "Unknown").all()
    assert cr.dropna().between(0.5, 2.0).all()


def test_status_consistent_with_exit_date(enps):
    e = enps["emp"]
    assert not ((e["employment_status"] == "Active") & e["date_of_exit"].notna()).any()
    assert ((e["employment_status"] == "Exited") & e["date_of_exit"].isna()).sum() == e["exit_date_unknown"].sum()
    unk = e[e["exit_date_unknown"]]
    assert not unk["active_on_oct_open"].any()
    assert (unk["active_on_apr_open"] == (unk["date_of_joining"] <= WAVES["Apr"]["open"])).all()
    assert (e["date_of_exit"].dropna() <= AS_OF).all()


def test_panel_flag(valid):
    p = valid[valid["in_panel"]]
    assert (p.groupby("employee_id")["wave"].nunique() == 2).all()


def test_manager_status_rule(enps):
    e = enps["emp"]
    lo, hi = pd.Timestamp("2026-04-18"), pd.Timestamp("2026-10-04")
    win = e["manager_effective_from"].between(lo, hi)
    assert (e["manager_changed_literal"] == win).all()
    ch = e["manager_status"] == "Changed manager"
    nj = e["manager_status"] == "New joiner (first manager)"
    assert (ch == (win & (e["manager_effective_from"] > e["date_of_joining"]))).all()
    assert (nj == (win & (e["manager_effective_from"] == e["date_of_joining"]))).all()
    assert ch.sum() + nj.sum() == win.sum()
    assert "manager_changed_between_waves" not in e.columns
