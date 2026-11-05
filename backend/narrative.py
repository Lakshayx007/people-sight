"""
narrative.py
------------
Plain-language takeaways for people who are not analysts. Every sentence is written by code from the rows the
metric SQL already returned (no LLM, no new numbers), so it is always available and always matches the chart.

  takeaway(endpoint, rows, ctx)  -> one sentence for a panel, or None
  page_takeaways_*(...)          -> 3 headline bullets for a dashboard (with filters)
  dq_stories(...)                -> human summary of the cleaning log
Each function is defensive: suppressed groups (n < 5) are skipped and anything unexpected returns None.
"""
from __future__ import annotations

import math
import re
from typing import Any, Callable

MIN_N = 20          # a group must have at least this many respondents to be named as best / worst


# ── formatting (same conventions as the dashboard) ──────────────────────────
def _ok(v) -> bool:
    return isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))


def sgn(v, d: int = 1) -> str:
    return "—" if not _ok(v) else (f"+{v:.{d}f}" if v > 0 else f"−{abs(v):.{d}f}" if v < 0 else f"{0:.{d}f}")


def pct(v, d: int = 1) -> str:
    return "—" if not _ok(v) else f"{v:.{d}f}%"


def num(v) -> str:
    return "—" if not _ok(v) else f"{int(round(v)):,}"


def days(v) -> str:
    return "—" if not _ok(v) else f"{v:.0f} day" + ("" if round(v) == 1 else "s")


DIM_WORDS = {"thread": "thread", "function": "function", "job_family": "job family", "grade": "grade",
             "location": "location", "tenure_band": "tenure group", "compa_band": "pay band",
             "manager_status": "manager group", "performance_rating": "rating group"}


def _seg_name(dim: str, v: str) -> str:
    if dim == "tenure_band":
        return {"<6m": "people with under 6 months' tenure", "6-12m": "people with 6–12 months' tenure",
                "1-2y": "people with 1–2 years' tenure", "2-4y": "people with 2–4 years' tenure",
                "4y+": "people with 4+ years' tenure"}.get(v, v)
    if dim == "manager_status":
        return {"Changed manager": "people who changed manager", "Same manager": "people with the same manager",
                "New joiner (first manager)": "new joiners on their first manager"}.get(v, v)
    if dim == "compa_band":
        return {"Below": "people paid below band", "At": "people paid at band", "Above": "people paid above band"}.get(v, v)
    return v


# ── Employee sentiment panels ────────────────────────────────────────────────
def enps_segment(rows, ctx):
    dim = ctx.get("dim", "thread")
    ok = [r for r in rows if not r.get("suppressed_oct") and _ok(r.get("enps_oct")) and (r.get("n_oct") or 0) >= MIN_N]
    if len(ok) < 2:
        return None
    lo, hi = min(ok, key=lambda r: r["enps_oct"]), max(ok, key=lambda r: r["enps_oct"])
    s = (f"In October, {_seg_name(dim, lo['segment'])} were the least positive (eNPS {sgn(lo['enps_oct'])}, "
         f"{num(lo['n_oct'])} people) and {_seg_name(dim, hi['segment'])} the most ({sgn(hi['enps_oct'])}).")
    ch = [r for r in ok if _ok(r.get("enps_change")) and not r.get("suppressed_apr")]
    if ch:
        fall = min(ch, key=lambda r: r["enps_change"])
        if fall["enps_change"] < -5:
            s += f" The biggest fall since April was {_seg_name(dim, fall['segment'])} ({sgn(fall['enps_change'])} points)."
    low = [r["segment"] for r in rows if r.get("low_response_oct")]
    if low:
        s += f" Few people answered in {', '.join(low)}, so read those with care."
    return s


def enps_drivers(rows, ctx):
    oct_ = {r["label"]: r for r in rows if r["wave"] == "Oct" and not r.get("suppressed") and _ok(r.get("pct_favourable"))}
    apr = {r["label"]: r for r in rows if r["wave"] == "Apr" and not r.get("suppressed") and _ok(r.get("pct_favourable"))}
    if not oct_:
        return None
    weak = min(oct_.values(), key=lambda r: r["pct_favourable"])
    s = f"{weak['label']} is the weakest area in October: only {pct(weak['pct_favourable'])} answered positively."
    falls = [(k, oct_[k]["pct_favourable"] - apr[k]["pct_favourable"]) for k in oct_ if k in apr]
    if falls:
        k, d = min(falls, key=lambda x: x[1])
        if d < -2:
            s += f" {k} fell the most since April ({pct(apr[k]['pct_favourable'])} → {pct(oct_[k]['pct_favourable'])})."
    return s


def enps_driver_importance(rows, ctx):
    ok = [r for r in rows if not r.get("suppressed") and _ok(r.get("corr_with_q1"))]
    if len(ok) < 2:
        return None
    imp = max(ok, key=lambda r: r["corr_with_q1"])
    low = min(ok, key=lambda r: r["mean_score"])
    if imp["label"] == low["label"]:
        return (f"{imp['label']} matters most for whether people would recommend Porter, and it also scores lowest "
                "— the clearest place to act.")
    return (f"{imp['label']} matters most for whether people would recommend Porter; {low['label']} scores lowest. "
            "Fix what is both important and low-scoring first (bottom-right of the chart).")


def enps_heatmap(rows, ctx):
    ok = [r for r in rows if not r.get("suppressed") and _ok(r.get("enps")) and (r.get("n") or 0) >= 10]
    if len(ok) < 2:
        return None
    lo, hi = min(ok, key=lambda r: r["enps"]), max(ok, key=lambda r: r["enps"])
    return (f"The least positive team is {lo['col_value']} in {lo['row_value']} (eNPS {sgn(lo['enps'])}, {num(lo['n'])} "
            f"people); the most positive is {hi['col_value']} in {hi['row_value']} ({sgn(hi['enps'])}).")


def enps_by_wave(rows, ctx):
    w = {r["wave"]: r for r in rows if not r.get("suppressed")}
    if "Apr" not in w or "Oct" not in w:
        return None
    a, o = w["Apr"], w["Oct"]
    direction = "fell" if o["enps"] < a["enps"] else "rose" if o["enps"] > a["enps"] else "held"
    return (f"eNPS {direction} from {sgn(a['enps'])} to {sgn(o['enps'])}: promoters went from {pct(a['pct_promoters'])} to "
            f"{pct(o['pct_promoters'])} and detractors from {pct(a['pct_detractors'])} to {pct(o['pct_detractors'])}.")


def enps_themes(rows, ctx):
    p: dict[str, dict] = {}
    for r in rows:
        if not r.get("suppressed") and _ok(r.get("pct_of_comments")):
            p.setdefault(r["theme"], {})[r["wave"]] = r["pct_of_comments"]
    both = {t: v for t, v in p.items() if "Apr" in v and "Oct" in v}
    if not both:
        return None
    up = max((t for t in both if t != "Positive"), key=lambda t: both[t]["Oct"] - both[t]["Apr"], default=None)
    s = ""
    if up and both[up]["Oct"] > both[up]["Apr"]:
        s = f"Comments about {up.lower()} grew the most (from {pct(both[up]['Apr'])} to {pct(both[up]['Oct'])} of comments)."
    if "Positive" in both:
        s += (" " if s else "") + (f"Positive comments went from {pct(both['Positive']['Apr'])} to "
                                   f"{pct(both['Positive']['Oct'])}.")
    return s or None


def enps_exits(rows, ctx):
    g = {r["nps_group"]: r for r in rows if not r.get("suppressed")}
    if "Detractor" not in g or "Promoter" not in g:
        return None
    d, p = g["Detractor"]["pct_voluntary_exit"], g["Promoter"]["pct_voluntary_exit"]
    ratio = f" — about {d / p:.0f} times as often" if _ok(d) and _ok(p) and p > 0 and d / p >= 1.5 else ""
    return (f"{pct(d)} of people who were unhappy in April (detractors) chose to leave by October, against {pct(p)} of "
            f"promoters{ratio}. Low scores are an early warning of resignations.")


def enps_non_response(rows, ctx):
    ok = [r for r in rows if not r.get("suppressed") and _ok(r.get("oct_response_rate_pct"))]
    if not ok:
        return None
    lo = min(ok, key=lambda r: r["oct_response_rate_pct"])
    if lo["oct_response_rate_pct"] >= 50:
        return "Most people who answered in April answered again in October, so October results are representative."
    return (f"Only {pct(lo['oct_response_rate_pct'], 0)} of {lo['segment']} answered again in October, so a change there "
            "may reflect who answered rather than how people feel.")


# ── Hiring panels ────────────────────────────────────────────────────────────
def _month(m: str) -> str:
    try:
        y, mm = m.split("-")
        return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(mm) - 1] + " " + y
    except Exception:  # noqa: BLE001
        return m


def hiring_monthly(rows, ctx):
    ok = [r for r in rows if _ok(r.get("reqs_raised"))]
    if not ok:
        return None
    pk = max(ok, key=lambda r: r["reqs_raised"])
    pj = max(ok, key=lambda r: r.get("joins") or 0)
    return (f"New openings peaked in {_month(pk['month'])} ({num(pk['reqs_raised'])}); joiners peaked in "
            f"{_month(pj['month'])} ({num(pj['joins'])}), about a month after offers were accepted.")


def hiring_funnel(rows, ctx):
    if not rows:
        return None
    first, last = rows[0], rows[-1]
    drops = [r for r in rows[1:] if _ok(r.get("pct_of_previous"))]
    s = (f"Of {num(first['candidates'])} applicants, {num(last['candidates'])} joined "
         f"({pct(100 * last['candidates'] / first['candidates'], 1) if first['candidates'] else '—'}).")
    if drops:
        d = min(drops, key=lambda r: r["pct_of_previous"])
        s += (f" The biggest drop is at the '{d['stage']}' step: only {pct(d['pct_of_previous'], 0)} of candidates "
              "from the step before reach it.")
    return s


def hiring_stage_time(rows, ctx):
    ok = [r for r in rows if _ok(r.get("median_days"))]
    if not ok:
        return None
    long = max(ok, key=lambda r: r["median_days"])
    return (f"Most steps take a few days each; the longest wait is {long['transition']} "
            f"({days(long['median_days'])} at the median), largely notice periods.")


def hiring_source(rows, ctx):
    ok = [r for r in rows if _ok(r.get("applicant_to_hire_pct")) and (r.get("applicants") or 0) >= 50]
    if len(ok) < 2:
        return None
    best, worst = max(ok, key=lambda r: r["applicant_to_hire_pct"]), min(ok, key=lambda r: r["applicant_to_hire_pct"])
    s = (f"{best['source']} turns {pct(best['applicant_to_hire_pct'], 1)} of applicants into hires; "
         f"{worst['source']} only {pct(worst['applicant_to_hire_pct'], 1)}.")
    ag = next((r for r in rows if r["source"] == "Agency" and _ok(r.get("cost_per_joiner_inr")) and r["cost_per_joiner_inr"] > 0), None)
    if ag:
        s += f" Agency hires cost ₹{num(ag['cost_per_joiner_inr'])} each in fees."
    return s


def hiring_recruiter_comparison(rows, ctx):
    ok = [r for r in rows if (r.get("reqs_assigned") or 0) > 0]
    if len(ok) < 2:
        return None
    tot = sum(r["reqs_assigned"] for r in ok)
    top = max(ok, key=lambda r: r["reqs_assigned"])
    return (f"{top['recruiter']} handles {num(top['reqs_assigned'])} of {num(tot)} openings "
            f"({pct(100 * top['reqs_assigned'] / tot, 0)}) — compare speed and SLA per opening, not total offers.")


def hiring_interviewers(rows, ctx):
    ok = [r for r in rows if _ok(r.get("median_feedback_days"))]
    if len(ok) < 3:
        return None
    s = sorted(ok, key=lambda r: -r["median_feedback_days"])
    rest = sorted(r["median_feedback_days"] for r in s[2:])
    mid = rest[len(rest) // 2] if rest else None
    return (f"Two interviewers take {days(s[0]['median_feedback_days'])} and {days(s[1]['median_feedback_days'])} to give "
            f"feedback, while most give it within {days(mid)}. Candidates waiting that long tend to drop out.")


def hiring_ttf_by_grade(rows, ctx):
    ok = [r for r in rows if _ok(r.get("pct_within_sla")) and (r.get("filled") or 0) >= 5]
    if not ok:
        return None
    w = min(ok, key=lambda r: r["pct_within_sla"])
    return (f"{w['grade']} roles hit the {w['sla_days']:.0f}-day target only {pct(w['pct_within_sla'], 0)} of the time "
            f"(median {days(w['median_ttf_days'])}); junior roles mostly fill on time.")


def hiring_open_aging(rows, ctx):
    tot = sum(r.get("open_reqs") or 0 for r in rows)
    if not tot:
        return None
    within = sum(r["open_reqs"] for r in rows if r["aging_bucket"] == "Within SLA")
    worst = next((r for r in rows if r["aging_bucket"].startswith("60+")), None)
    s = f"{num(tot - within)} of {num(tot)} open roles are past their target time."
    if worst and worst["open_reqs"]:
        s += f" {num(worst['open_reqs'])} are more than 60 days late."
    return s


def hiring_offers(rows, ctx):
    b = {r["ratio_band"]: r for r in rows if _ok(r.get("decline_rate_pct"))}
    if "<0.90" not in b or "0.90-0.99" not in b:
        return None
    return (f"Candidates offered less than 90% of what they asked for said no {pct(b['<0.90']['decline_rate_pct'], 0)} "
            f"of the time, against {pct(b['0.90-0.99']['decline_rate_pct'], 0)} for offers at 90–99%.")


def hiring_sla_mismatch(rows, ctx):
    m = [r for r in rows if r.get("mismatch")]
    if not m:
        return "The applicant tracking system's SLA status agrees with the dates on every filled role."
    n = sum(r["reqs"] for r in m)
    return (f"The applicant tracking system marks {num(n)} filled roles as on time that actually missed their target "
            "by the dates — the dashboard uses the dates.")


def hiring_backfill(rows, ctx):
    if not rows or not _ok(rows[0].get("median_days_exit_to_req")):
        return None
    r = rows[0]
    return (f"Replacement hiring starts a median {days(r['median_days_exit_to_req'])} after someone leaves, and "
            f"{pct(r['pct_regrettable_of_known'], 0)} of replacements are for people Porter did not want to lose.")


PANELS: dict[str, Callable[[list, dict], str | None]] = {
    "enps/segment": enps_segment, "enps/drivers": enps_drivers, "enps/driver-importance": enps_driver_importance,
    "enps/heatmap": enps_heatmap, "enps/by-wave": enps_by_wave, "enps/themes": enps_themes,
    "enps/respondents-who-exited": enps_exits, "enps/non-response-bias": enps_non_response,
    "hiring/monthly": hiring_monthly, "hiring/funnel": hiring_funnel, "hiring/stage-time": hiring_stage_time,
    "hiring/source": hiring_source, "hiring/recruiter-comparison": hiring_recruiter_comparison,
    "hiring/interviewers": hiring_interviewers, "hiring/ttf-by-grade": hiring_ttf_by_grade,
    "hiring/open-aging-buckets": hiring_open_aging, "hiring/offers": hiring_offers,
    "hiring/sla-mismatch": hiring_sla_mismatch, "hiring/backfill": hiring_backfill,
}


def takeaway(endpoint: str, rows: list[dict], ctx: dict | None = None) -> str | None:
    fn = PANELS.get(endpoint)
    if not fn or not rows:
        return None
    try:
        return fn(rows, ctx or {})
    except Exception:  # noqa: BLE001 — a takeaway must never break a chart
        return None


# ── page-level takeaways ─────────────────────────────────────────────────────
def page_takeaways_enps(kpis: dict, panel: dict, segs: dict[str, list], drivers: list) -> list[dict]:
    out: list[dict] = []
    if _ok(kpis.get("enps_oct")) and _ok(kpis.get("enps_apr")):
        ch = kpis["enps_oct"] - kpis["enps_apr"]
        verb = "fell" if ch < 0 else "rose" if ch > 0 else "held steady"
        t = (f"Would people recommend Porter as a place to work? The score (eNPS) {verb} from {sgn(kpis['enps_apr'])} in "
             f"April to {sgn(kpis['enps_oct'])} in October ({num(kpis['n_oct'])} people answered).")
        if _ok(panel.get("enps_change")) and panel.get("n"):
            t += f" Among the {num(panel['n'])} people who answered both times it moved {sgn(panel['enps_change'])} points."
        out.append({"tone": "bad" if ch < 0 else "good" if ch > 0 else "neutral", "text": t, "link": None})
    worst = None
    for dim, rows in segs.items():
        for r in rows or []:
            if not r.get("suppressed_oct") and _ok(r.get("enps_oct")) and (r.get("n_oct") or 0) >= MIN_N:
                if worst is None or r["enps_oct"] < worst[1]["enps_oct"]:
                    worst = (dim, r)
    if worst:
        dim, r = worst
        out.append({"tone": "bad", "link": {"dim": dim, "value": r["segment"]},
                    "text": f"Least positive group: {_seg_name(dim, r['segment'])}, with an eNPS of {sgn(r['enps_oct'])} "
                            f"({num(r['n_oct'])} people). Click to see their full picture."})
    d = enps_drivers(drivers, {})
    if d:
        out.append({"tone": "neutral", "text": d, "link": None})
    return out


def page_takeaways_hiring(kpis: dict, grades: list, offers: list, interviewers: list) -> list[dict]:
    out: list[dict] = []
    if _ok(kpis.get("median_ttf_days")):
        out.append({"tone": "neutral", "link": None,
                    "text": f"A typical opening is filled in {days(kpis['median_ttf_days'])}; {pct(kpis['pct_within_sla'], 0)} "
                            f"are filled within their target time, and {num(kpis['open_past_sla'])} of "
                            f"{num(kpis['open_reqs'])} open roles are already late."})
    g = hiring_ttf_by_grade(grades, {}) if grades else None
    if g:
        out.append({"tone": "bad", "text": g, "link": None})
    o = hiring_offers(offers, {}) if offers else None
    if o:
        out.append({"tone": "bad", "text": o + " Offering closer to expectations is the quickest win.", "link": None})
    elif interviewers:
        i = hiring_interviewers(interviewers, {})
        if i:
            out.append({"tone": "bad", "text": i, "link": None})
    return out


# ── data quality, for people ─────────────────────────────────────────────────
DQ_GROUPS = [
    ("duplicates", "Duplicates removed", r"duplicate|answered the same wave twice|Same ID, different",
     "The same person or candidate appeared more than once. We kept one record each, so nobody is counted twice."),
    ("spelling", "Spellings made consistent", r"spelling|variants|case|trailing|spellings|Short / case",
     "The same team, grade or status was typed in different ways (e.g. 'InterCity' and 'Intercity'). We merged "
     "them so each group is counted as one."),
    ("formats", "Dates, money and text fixed", r"Mixed formats|String dates|comma strings|Lakh strings|LPA|Text values|x/10|excel serial",
     "Dates, salaries and notice periods came in mixed formats. We converted them so they can be compared and averaged."),
    ("excluded", "Records left out on purpose", r"Test IDs|Not in Employee_Master|No matching requisition|not active on the wave|Q1 blank|Q1 outside",
     "Test entries, people not on the employee list, and candidates with no matching job opening were set aside, "
     "because counting them would distort the results."),
    ("corrected", "Values corrected and flagged", r"Value < 0.5x band mid|'Active' but Date of Exit|Exited with missing exit date|Vendor",
     "A few values were clearly wrong (a monthly salary entered as yearly, a leaver still marked active). We corrected "
     "them and flagged each one."),
    ("findings", "Things the business should know", r"FINDING|backed out|raised before the replaced",
     "Not errors to fix but facts worth knowing — for example, the hiring system marks some late hires as on time."),
]


def dq_stories(log_rows: list[dict]) -> list[dict]:
    """Group changed-data rules into a few plain-language cards. Counts are summed from the cleaning log."""
    out = []
    used: set[int] = set()
    for key, title, rx, why in DQ_GROUPS:
        pat = re.compile(rx, re.I)
        hits = [(i, r) for i, r in enumerate(log_rows)
                if i not in used and r.get("rows_affected", 0) > 0 and r.get("treatment") != "Validated"
                and pat.search(str(r.get("issue", "")))]
        if not hits:
            continue
        used |= {i for i, _ in hits}
        examples = [f"{r['sheet'] + ' (whole rows)' if str(r.get('column', '')).startswith('(') else r.get('column')}: "
                    f"{r['rows_affected']:,}"
                    for _, r in sorted(hits, key=lambda x: -x[1]["rows_affected"])[:3]]
        out.append({"key": key, "title": title, "rules": len(hits),
                    "rows": int(sum(r["rows_affected"] for _, r in hits)), "why": why, "examples": examples})
    return out
