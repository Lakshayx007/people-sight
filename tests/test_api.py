"""API contract, filters, reconciliation and suppression through HTTP."""
import random

import pytest

from backend import db as dbm
from backend import metrics_enps as E, metrics_hiring as H
from backend.sql_common import MIN_N

ENPS_EP = ["kpis", "by-wave", "panel", "segment?dim=thread", "segment?dim=manager_status", "drivers",
           "driver-importance", "heatmap?row=thread&col=function", "themes", "respondents-who-exited",
           "non-response-bias?dim=thread"]
HIRING_EP = ["kpis", "monthly", "funnel", "stage-time", "source", "recruiters", "recruiter-comparison", "interviewers", "ttf-by-grade",
             "open-aging", "open-aging-buckets", "offers", "offers-summary", "sla-mismatch", "sla-mismatch-list", "backfill"]
SCORE_COLS = {"enps", "enps_apr", "enps_oct", "enps_change", "pct_promoters", "pct_passives", "pct_detractors",
              "mean_score", "pct_favourable", "corr_with_q1", "comments", "pct_of_respondents", "pct_exited",
              "apr_enps_oct_respondents", "apr_enps_oct_nonrespondents", "gap_nonresp_minus_resp"}


@pytest.fixture(scope="module")
def options(api):
    out = {"enps": {}, "hiring": {}}
    for r in api.get("/api/filters/options").json()["data"]:
        out[r["dashboard"]][r["key"]] = r["values"]
    return out


def combos(options, dash, k=5, seed=7):
    rnd = random.Random(seed + len(dash))
    keys = [x for x in options[dash] if x != "raised_month"]
    res = []
    for _ in range(k):
        f = {}
        for key in rnd.sample(keys, rnd.randint(1, 3)):
            vals = options[dash][key]
            f[key] = rnd.sample(vals, min(len(vals), rnd.randint(1, 2)))
        if dash == "hiring" and rnd.random() < 0.5:
            months = sorted(options["hiring"]["raised_month"])
            f["raised_month_from"], f["raised_month_to"] = months[1], months[-2]
        res.append(f)
    return res


def check_shape(j):
    assert {"data", "sql", "n"} <= set(j) <= {"data", "sql", "n", "takeaway"}
    assert isinstance(j["data"], list) and isinstance(j["sql"], str) and isinstance(j["n"], int)


def check_suppression(rows):
    """Any row flagged suppressed must carry no scores; any survey group with n < 5 must be flagged."""
    for r in rows:
        if "n_oct_respondents" in r:   # non-response bias: each side is suppressed on its own n
            for nk, vk in [("n_oct_respondents", "apr_enps_oct_respondents"), ("n_oct_nonrespondents", "apr_enps_oct_nonrespondents")]:
                if r[nk] < MIN_N:
                    assert r[vk] is None and r["suppressed"] is True and r["gap_nonresp_minus_resp"] is None, r
                else:
                    assert r[vk] is not None, r
            continue
        flags = {k: v for k, v in r.items() if k.startswith("suppressed")}
        if flags and all(flags.values()):
            assert all(r.get(c) is None for c in SCORE_COLS if c in r), r
        for nk, sk, vk in [("n", "suppressed", "enps"), ("n_oct", "suppressed_oct", "enps_oct"), ("n_apr", "suppressed_apr", "enps_apr")]:
            if nk in r and sk in r and r[nk] is not None and r[nk] < MIN_N:
                assert r[sk] is True and r.get(vk) is None, r


# ── contract ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ep", ENPS_EP)
def test_enps_endpoints_random_filters(api, options, ep):
    for f in [{}] + combos(options, "enps"):
        r = api.post(f"/api/enps/{ep}", json={"filters": f})
        assert r.status_code == 200, (ep, f, r.text)
        j = r.json()
        check_shape(j)
        check_suppression(j["data"])
        if f:
            assert j["sql"].startswith("-- params:")


@pytest.mark.parametrize("ep", HIRING_EP)
def test_hiring_endpoints_random_filters(api, options, ep):
    for f in [{}] + combos(options, "hiring"):
        r = api.post(f"/api/hiring/{ep}", json={"filters": f})
        assert r.status_code == 200, (ep, f, r.text)
        check_shape(r.json())


def test_sql_returned_is_the_sql_run(api):
    f = {"thread": ["Intercity", "Central"], "grade": ["G2", "G3"]}
    j = api.post("/api/enps/segment?dim=function", json={"filters": f}).json()
    params = {"f_thread": f["thread"], "f_grade": f["grade"]}
    assert dbm.query(j["sql"], params) == j["data"]


# ── reconciliation under filters ─────────────────────────────────────────────

def test_unfiltered_kpis_equal_metric_reference(api, db):
    k = api.post("/api/enps/kpis", json={}).json()["data"][0]
    sql, p = E.kpis()
    ref = db.execute(sql, p).df().iloc[0]
    for c in ["enps_apr", "enps_oct", "enps_change", "n_apr", "n_oct", "invited_apr", "invited_oct",
              "response_rate_apr_pct", "response_rate_oct_pct", "pct_promoters_oct", "pct_detractors_oct"]:
        assert k[c] == ref[c], c
    assert (k["enps_apr"], k["enps_oct"], k["enps_change"], k["n_apr"], k["n_oct"]) == (11.0, 3.3, -7.7, 866, 799)
    h = api.post("/api/hiring/kpis", json={}).json()["data"][0]
    sql, p = H.kpis()
    href = db.execute(sql, p).df().iloc[0]
    for c in ["reqs_raised", "filled_reqs", "median_ttf_days", "pct_within_sla", "offer_acceptance_pct",
              "joining_rate_pct", "agency_fees_inr", "open_past_sla"]:
        assert h[c] == href[c], c


@pytest.mark.parametrize("dim", list(E.SEGMENT_DIMS))
def test_segments_sum_to_kpis_under_filters(api, options, dim):
    for f in [{}] + combos(options, "enps", seed=11):
        f = {k: v for k, v in f.items() if k != dim}
        k = api.post("/api/enps/kpis", json={"filters": f}).json()
        s = api.post(f"/api/enps/segment?dim={dim}", json={"filters": f}).json()
        kd = k["data"][0]
        assert sum(r["n_apr"] for r in s["data"]) == (kd["n_apr"] or 0)
        assert sum(r["n_oct"] for r in s["data"]) == (kd["n_oct"] or 0)
        assert sum(r["invited_oct"] for r in s["data"]) == (kd["invited_oct"] or 0)
        assert k["n"] == s["n"] == kd["n"]


def test_hiring_reconciles_under_filters(api, options):
    for f in [{}, {"recruiter": ["Rhea Kapoor"], "source": ["Agency"]}] + combos(options, "hiring", seed=3):
        get = lambda ep: api.post(f"/api/hiring/{ep}", json={"filters": f}).json()
        k = get("kpis")["data"][0]
        fun = {r["stage"]: r["candidates"] for r in get("funnel")["data"]}
        assert fun["Joined"] == k["filled_joined"], f
        assert fun["Offer Accepted"] == k["offers_accepted"], f
        assert fun["Applied"] == k["applicants"] == get("funnel")["n"], f
        assert sum(r["filled"] for r in get("ttf-by-grade")["data"]) == k["filled_reqs"], f
        assert sum(r["hires"] for r in get("source")["data"]) == k["filled_reqs"], f
        assert sum(r["filled"] for r in get("recruiters")["data"]) == k["filled_reqs"], f
        rc = get("recruiter-comparison")["data"]
        assert sum(r["filled"] for r in rc) == k["filled_reqs"] and sum(r["reqs_assigned"] for r in rc) == k["reqs_raised"], f
        assert sum(r["open_past_sla"] for r in rc) == k["open_past_sla"], f
        assert sum(r["reqs_raised"] for r in get("monthly")["data"]) == k["reqs_raised"] == get("kpis")["n"], f
        assert sum(r["open_reqs"] for r in get("open-aging-buckets")["data"]) == k["open_reqs"], f


def test_source_filter_semantics(api, rec):
    k = api.post("/api/hiring/kpis", json={"filters": {"source": ["Agency"]}}).json()["data"][0]
    c, r = rec["cand"], rec["req"]
    assert k["reqs_raised"] == c.loc[c.source_clean == "Agency", "req_id"].nunique()
    assert k["filled_reqs"] == (c.is_hire & (c.source_clean == "Agency")).sum()


# ── safety ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,body", [
    ("/api/enps/kpis", {"filters": {"employee_name": ["x"]}}),
    ("/api/enps/kpis", {"filters": {"recruiter": ["Rhea Kapoor"]}}),
    ("/api/hiring/kpis", {"filters": {"manager_status": ["Same manager"]}}),
    ("/api/hiring/kpis", {"filters": {"raised_month_from": "May"}}),
    ("/api/enps/segment?dim=employee_id", {}),
    ("/api/enps/heatmap?row=thread&col=thread", {}),
    ("/api/enps/heatmap?row=thread&col=function&wave=Jan", {}),
])
def test_bad_requests_rejected(api, url, body):
    assert api.post(url, json=body).status_code in (400, 422)


def test_injection_in_values_is_inert(api):
    r = api.post("/api/enps/kpis", json={"filters": {"thread": ["x') OR 1=1; DROP TABLE t_survey; --"]}})
    assert r.status_code == 200 and r.json()["n"] == 0
    assert api.post("/api/enps/kpis", json={}).json()["n"] == 1665


def test_no_names_in_survey_endpoints(api):
    for ep in ENPS_EP:
        j = api.post(f"/api/enps/{ep}", json={}).json()
        for row in j["data"]:
            assert not any("name" in k or k in ("employee_id", "respondent_key") for k in row), (ep, row)


def test_small_n_combo_suppressed(api):
    f = {"thread": ["Intercity"], "manager_status": ["Changed manager"], "grade": ["G4"]}
    for ep in ["kpis", "by-wave", "segment?dim=function", "drivers", "themes"]:
        check_suppression(api.post(f"/api/enps/{ep}", json={"filters": f}).json()["data"])


def test_misc_endpoints(api):
    for url in ["/api/dq", "/api/dq/reconciliation", "/api/dq/summary", "/api/health", "/api/filters/options"]:
        r = api.get(url)
        assert r.status_code == 200
        check_shape(r.json())
    opts = {(o["dashboard"], o["key"]) for o in api.get("/api/filters/options").json()["data"]}
    assert ("enps", "manager_status") in opts and ("hiring", "source") in opts
    assert api.get("/api/does-not-exist").status_code == 404


def test_dq_dataset_param(api):
    all_n = api.get("/api/dq").json()["n"]
    e, r = api.get("/api/dq?dataset=eNPS").json(), api.get("/api/dq?dataset=Recruitment").json()
    assert e["n"] + r["n"] == all_n and all(x["dataset"] == "eNPS" for x in e["data"])
    assert api.get("/api/dq?dataset=bogus").status_code == 422


def test_open_aging_base_is_open_reqs(api):
    j = api.post("/api/hiring/open-aging-buckets", json={}).json()
    assert j["n"] == sum(x["open_reqs"] for x in j["data"])


def test_survey_code_never_touches_names():
    """Names live only in v_interviewers (hiring). Survey metrics must never reference it, v_employees or names."""
    import inspect
    from backend import metrics_enps
    src = inspect.getsource(metrics_enps)
    for banned in ("v_interviewers", "employee_name", "v_employees", "t_people_directory", "employee_id"):
        assert banned not in src, banned


def test_dq_summary_matches_log(api):
    for ds in ["", "?dataset=eNPS", "?dataset=Recruitment"]:
        sm = api.get(f"/api/dq/summary{ds}").json()["data"][0]
        log = api.get(f"/api/dq{ds}").json()["data"]
        assert sm["rules"] == len(log)
        assert sm["issues_treated"] == sum(r["changed_data"] for r in log)
        assert sm["checks_passed"] == sum(r["rows_affected"] == 0 for r in log)


def test_recruiter_tables_follow_filters(api):
    f = {"filters": {"recruiter": ["Rhea Kapoor"], "source": ["Agency"]}}
    for ep in ["recruiters", "recruiter-comparison"]:
        rows = api.post(f"/api/hiring/{ep}", json=f).json()["data"]
        assert [r["recruiter"] for r in rows] == ["Rhea Kapoor"], ep
        assert len(api.post(f"/api/hiring/{ep}", json={}).json()["data"]) == 8
