"""Phase 4: the SQL metrics agree with an independent pandas calculation on the cleaned parquet,
segments add up to totals, suppression works, and the database schema is safe and documented."""
import numpy as np
import pandas as pd
import pytest

from backend import metrics_enps as E, metrics_hiring as H
from backend.sql_common import MIN_N


def enps_pd(df):
    return round(100 * ((df.q1_clean >= 9).mean() - (df.q1_clean <= 6).mean()), 1)


# ── eNPS vs pandas ───────────────────────────────────────────────────────────

def test_enps_kpis_match_pandas(q, enps):
    k = q(E.kpis).iloc[0]
    v = enps["resp"][enps["resp"].is_valid]
    e = enps["emp"]
    for w in ["Apr", "Oct"]:
        sub = v[v.wave == w]
        assert k[f"n_{w.lower()}"] == len(sub)
        assert k[f"enps_{w.lower()}"] == enps_pd(sub)
        assert k[f"invited_{w.lower()}"] == e[f"active_on_{w.lower()}_open"].sum()
        assert k[f"response_rate_{w.lower()}_pct"] == round(100 * len(sub) / e[f"active_on_{w.lower()}_open"].sum(), 1)
    assert k.enps_change == round(k.enps_oct - k.enps_apr, 1)
    assert abs(k.pct_promoters_oct + k.pct_passives_oct + k.pct_detractors_oct - 100) <= 0.15


def test_panel_matches_pandas(q, enps):
    v = enps["resp"][enps["resp"].is_valid & enps["resp"].in_panel]
    p = q(E.panel).iloc[0]
    assert p.n == v.employee_id.nunique()
    assert p.enps_apr == enps_pd(v[v.wave == "Apr"]) and p.enps_oct == enps_pd(v[v.wave == "Oct"])


@pytest.mark.parametrize("dim", list(E.SEGMENT_DIMS))
def test_segments_sum_to_totals(q, dim):
    s = q(E.segment, dim)
    k = q(E.kpis).iloc[0]
    assert s.n_apr.sum() == k.n_apr and s.n_oct.sum() == k.n_oct
    assert s.invited_apr.sum() == k.invited_apr and s.invited_oct.sum() == k.invited_oct
    assert s.segment.is_unique


@pytest.mark.parametrize("dim", list(E.SEGMENT_DIMS))
def test_suppression(q, dim):
    s = q(E.segment, dim)
    small = s[s.n_oct < MIN_N]
    assert small.enps_oct.isna().all() and small.suppressed_oct.all()
    big = s[s.n_oct >= MIN_N]
    assert big.enps_oct.notna().all() and not big.suppressed_oct.any()


def test_suppression_with_tiny_filter(q):
    w = ("thread = $t AND function = $f", {"t": "Central", "f": "Design & Research"})
    bw = q(E.by_wave, w)
    small = bw[bw.n < MIN_N]
    assert small.enps.isna().all() and small.pct_promoters.isna().all()


def test_drivers_match_pandas(q, enps):
    v = enps["resp"][enps["resp"].is_valid]
    d = q(E.drivers)
    for w in ["Apr", "Oct"]:
        for qq in ["q2", "q3", "q4", "q5", "q6"]:
            row = d[(d.driver == qq.upper()) & (d.wave == w)].iloc[0]
            col = v.loc[v.wave == w, qq].dropna().astype(float)
            assert row.n == len(col)
            assert row.mean_score == round(col.mean(), 2)
            assert row.pct_favourable == round(100 * (col >= 4).mean(), 1)


def test_driver_importance_corr(q, enps):
    v = enps["resp"][enps["resp"].is_valid & (enps["resp"].wave == "Oct")]
    d = q(E.driver_importance).set_index("driver")
    sub = v[["q2", "q1_clean"]].dropna().astype(float)
    assert d.loc["Q2", "corr_with_q1"] == round(sub.q2.corr(sub.q1_clean), 3)


def test_heatmap_cells_sum(q):
    h = q(E.heatmap, "thread", "function")
    assert h.n.sum() == q(E.kpis).iloc[0].n_oct
    assert h.loc[h.n < MIN_N, "enps"].isna().all()


def test_themes_and_exits(q, enps):
    v = enps["resp"][enps["resp"].is_valid]
    t = q(E.themes)
    assert t.comments.sum() == v.comment_theme.notna().sum()
    ex = q(E.respondents_who_exited)
    assert ex.n.sum() == (v.wave == "Apr").sum()
    apr = v[v.wave == "Apr"]
    det = apr[apr.nps_group == "Detractor"]
    assert ex.set_index("nps_group").loc["Detractor", "exited"] == det.exited_after_wave.sum()


def test_filters_pass_through(q, enps):
    w = ("thread = $t", {"t": "Intercity"})
    k = q(E.kpis, w).iloc[0]
    v = enps["resp"][enps["resp"].is_valid & (enps["resp"].thread == "Intercity")]
    assert k.n_oct == (v.wave == "Oct").sum() and k.enps_oct == enps_pd(v[v.wave == "Oct"])
    w2 = ("list_contains($m, manager_status)", {"m": ["Changed manager"]})
    s = q(E.segment, "thread", w2)
    assert s.n_oct.sum() == q(E.kpis, w2).iloc[0].n_oct


def test_bad_dimension_rejected():
    with pytest.raises(ValueError):
        E.segment("employee_name")
    with pytest.raises(ValueError):
        E.segment("thread; DROP TABLE t_survey")


# ── hiring vs pandas ─────────────────────────────────────────────────────────

def test_hiring_kpis_match_pandas(q, rec):
    k = q(H.kpis).iloc[0]
    r, c = rec["req"], rec["cand"]
    assert k.reqs_raised == len(r) and k.open_reqs == r.is_open.sum() and k.filled_reqs == r.is_filled.sum()
    assert k.median_ttf_days == r.loc[r.is_filled, "ttf_days"].median()
    assert k.pct_within_sla == round(100 * r.loc[r.is_filled, "sla_met"].astype(float).mean(), 1)
    assert k.open_past_sla == r.open_breached.fillna(False).sum()
    acc, dec = c.is_offer_accepted.sum(), c.is_offer_declined.sum()
    assert k.offer_acceptance_pct == round(100 * acc / (acc + dec), 1)
    assert k.joining_rate_pct == round(100 * (c.joining_due & c.is_joined).sum() / c.joining_due.sum(), 1)
    assert k.agency_fees_inr == c.agency_fee_inr.sum()


def test_funnel_matches_pandas(q, rec):
    f = q(H.funnel).set_index("stage")
    c = rec["cand"]
    assert f.loc["Applied", "candidates"] == len(c)
    assert f.loc["Joined", "candidates"] == c.is_joined.sum()
    assert f.loc["Offer Accepted", "candidates"] == c.is_offer_accepted.sum()
    assert (f.candidates.diff().dropna() <= 0).all()


def test_stage_time_matches_pandas(q, rec):
    s = q(H.stage_time).set_index("transition")
    c = rec["cand"]
    col = c.loc[~c.stage_dates_invalid, "days_r1_to_r2"].dropna()
    assert s.loc["R1 → R2", "n"] == len(col) and s.loc["R1 → R2", "median_days"] == col.median()


def test_monthly_totals(q, rec):
    m = q(H.monthly)
    assert m.reqs_raised.sum() == len(rec["req"])
    assert m.offers_accepted.sum() == rec["cand"].is_offer_accepted.sum()
    assert m.joins.sum() == rec["cand"].is_joined.sum()


def test_source_and_recruiters_add_up(q, rec):
    s = q(H.source)
    assert s.applicants.sum() == len(rec["cand"]) and s.hires.sum() == rec["req"].is_filled.sum()
    assert s.agency_fees_inr.sum() == rec["cand"].agency_fee_inr.sum()
    r = q(H.recruiters)
    assert r.reqs.sum() == len(rec["req"]) and len(r) == 8
    rhea = r.set_index("recruiter").loc["Rhea Kapoor"]
    assert rhea.attainment_pct == round(100 * rhea.offers_accepted / 7 / rhea.monthly_offer_target, 1)


def test_ttf_grade_and_sla_lists(q, rec):
    g = q(H.ttf_by_grade)
    assert g.filled.sum() == rec["req"].is_filled.sum()
    assert len(q(H.sla_mismatch_list)) == rec["req"].sla_status_mismatch.sum() == 14
    assert q(H.open_aging_buckets).open_reqs.sum() == rec["req"].is_open.sum()


def test_interviewers_min_n(q):
    i = q(H.interviewers)
    assert len(i) <= 15 and (i.n >= 5).all() and i.interviewer.notna().all()
    assert i.median_feedback_days.is_monotonic_decreasing


def test_hiring_filter_pass_through(q, rec):
    wr = ("recruiter = $rc", {"rc": "Rhea Kapoor"})
    wc = ("recruiter = $rc AND source = $src", {"rc": "Rhea Kapoor", "src": "Agency"})
    k = q(H.kpis, wr, wc).iloc[0]
    assert k.reqs_raised == (rec["req"].recruiter == "Rhea Kapoor").sum()
    c = rec["cand"].merge(rec["req"][["req_id", "recruiter"]], on="req_id")
    assert k.applicants == ((c.recruiter == "Rhea Kapoor") & (c.source_clean == "Agency")).sum()


# ── database schema ──────────────────────────────────────────────────────────

def test_every_view_column_commented(db):
    rows = db.execute("""SELECT c.table_name, c.column_name, c.comment FROM duckdb_columns() c
                         JOIN duckdb_views() v ON v.view_name = c.table_name
                         WHERE c.table_name LIKE 'v\\_%' ESCAPE '\\'""").fetchall()
    assert rows and all(r[2] for r in rows), [r[:2] for r in rows if not r[2]]
    views = {r[0] for r in db.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}
    assert {"v_employees", "v_survey", "v_requisitions", "v_candidates", "v_recruiters", "v_interviewers", "v_dq_log"} <= views


def test_survey_is_anonymous(db):
    for t in ["v_survey", "t_survey", "v_invited", "t_invited"]:
        cols = {r[0] for r in db.execute(f"DESCRIBE {t}").fetchall()}
        assert not cols & {"employee_id", "employee_name", "response_id"}, t
    emp_cols = {r[0] for r in db.execute("DESCRIBE v_employees").fetchall()}
    assert "employee_name" not in emp_cols


def test_invited_matches_survey(db):
    a = db.execute("SELECT wave, count(*) FROM v_survey GROUP BY 1 ORDER BY 1").fetchall()
    b = db.execute("SELECT wave, sum(responded::INT) FROM v_invited GROUP BY 1 ORDER BY 1").fetchall()
    assert a == b


def test_db_opened_read_only(db):
    with pytest.raises(Exception):
        db.execute("CREATE TABLE x AS SELECT 1")
