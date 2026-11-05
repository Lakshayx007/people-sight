"""Plain-language layer: panel takeaways, page takeaways, data-quality stories and the landing endpoint."""
import re

import pytest

from backend import narrative

ENPS = ["segment?dim=thread", "segment?dim=manager_status", "drivers", "driver-importance",
        "heatmap?row=thread&col=function", "by-wave", "themes", "respondents-who-exited", "non-response-bias?dim=thread"]
HIRING = ["monthly", "funnel", "stage-time", "source", "recruiter-comparison", "interviewers", "ttf-by-grade",
          "open-aging-buckets", "offers", "sla-mismatch", "backfill"]


def _numbers(text):
    return re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))


@pytest.mark.parametrize("ep", ENPS)
def test_enps_panels_have_takeaways(api, ep):
    j = api.post(f"/api/enps/{ep}", json={}).json()
    assert isinstance(j["takeaway"], str) and 20 < len(j["takeaway"]) < 400


@pytest.mark.parametrize("ep", HIRING)
def test_hiring_panels_have_takeaways(api, ep):
    j = api.post(f"/api/hiring/{ep}", json={}).json()
    assert isinstance(j["takeaway"], str) and 20 < len(j["takeaway"]) < 400


def test_takeaway_numbers_come_from_rows(api):
    """Every number in the segment sentence appears in the rows the chart returned (no invented numbers)."""
    j = api.post("/api/enps/segment?dim=thread", json={}).json()
    vals = [abs(v) for r in j["data"] for v in r.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    pool = {f"{v:.1f}" for v in vals} | {str(int(round(v))) for v in vals}
    for n in _numbers(j["takeaway"]):
        assert n in pool, n


def test_takeaways_follow_filters(api):
    a = api.post("/api/enps/segment?dim=function", json={}).json()["takeaway"]
    b = api.post("/api/enps/segment?dim=function", json={"filters": {"thread": ["Intercity"]}}).json()["takeaway"]
    assert a != b


def test_survey_takeaways_never_name_people(api, db):
    names = {r[0] for r in db.execute("SELECT employee_name FROM v_interviewers").fetchall()}
    for ep in ENPS:
        t = api.post(f"/api/enps/{ep}", json={}).json()["takeaway"] or ""
        assert not any(n in t for n in names), ep
    for t in api.post("/api/enps/takeaways", json={}).json()["data"]:
        assert not any(n in t["text"] for n in names)


@pytest.mark.parametrize("ep", ["/api/enps/takeaways", "/api/hiring/takeaways"])
def test_page_takeaways(api, ep):
    j = api.post(ep, json={}).json()
    assert {"data", "sql", "n"} <= set(j)
    assert 2 <= len(j["data"]) <= 3
    for t in j["data"]:
        assert t["tone"] in {"bad", "good", "neutral"} and len(t["text"]) > 20


def test_page_takeaway_link_drills_to_a_real_segment(api):
    rows = api.post("/api/enps/takeaways", json={}).json()["data"]
    link = next(t["link"] for t in rows if t["link"])
    seg = api.post(f"/api/enps/segment?dim={link['dim']}", json={}).json()["data"]
    assert link["value"] in {r["segment"] for r in seg}


def test_dq_stories_reconcile_with_log(api):
    j = api.get("/api/dq/stories").json()
    log = api.get("/api/dq").json()["data"]
    changed = sum(r["rows_affected"] for r in log if r["changed_data"])
    assert j["n"] == len(log)
    assert sum(s["rows"] for s in j["data"]) <= changed
    assert {s["key"] for s in j["data"]} >= {"duplicates", "spelling", "excluded", "findings"}


def test_home(api):
    h = api.get("/api/home").json()["data"][0]
    k = api.post("/api/enps/kpis", json={}).json()["data"][0]
    hk = api.post("/api/hiring/kpis", json={}).json()["data"][0]
    assert h["enps_oct"] == k["enps_oct"] and h["h_median_ttf_days"] == hk["median_ttf_days"]
    assert len(h["findings"]) >= 3 and h["rules"] > 0


def test_narrative_is_defensive():
    assert narrative.takeaway("enps/segment", [], {}) is None
    assert narrative.takeaway("unknown", [{"a": 1}], {}) is None
    assert narrative.takeaway("enps/drivers", [{"bad": "row"}], {}) is None
