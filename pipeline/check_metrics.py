"""
check_metrics.py
----------------
Run every metric in backend/metrics_enps.py and backend/metrics_hiring.py UNFILTERED against
data/people.duckdb, print the headline numbers with n, and write docs/metric_reference.md.

metric_reference.md is the reference the dashboard and the deck must match.
Run:  python pipeline/check_metrics.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import metrics_enps as E, metrics_hiring as H  # noqa: E402
from backend.sql_common import MIN_N  # noqa: E402

DB = ROOT / "data" / "people.duckdb"
OUT = ROOT / "docs" / "metric_reference.md"
con = duckdb.connect(str(DB), read_only=True)


def run(fn, *a, **k) -> pd.DataFrame:
    sql, params = fn(*a, **k)
    return con.execute(sql, params).df()


def md(df: pd.DataFrame) -> str:
    def cell(v):
        if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
            return "—"
        if isinstance(v, float):
            return f"{v:,.0f}" if abs(v) >= 1000 else (f"{v:g}" if v != int(v) else f"{int(v)}")
        if isinstance(v, pd.Timestamp):
            return f"{v:%Y-%m-%d}"
        return str(v)
    head = "| " + " | ".join(df.columns) + " |\n|" + "|".join("---" for _ in df.columns) + "|\n"
    return head + "\n".join("| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False))


sections: list[str] = []


def add(title: str, fn, *a, note: str = "", **k) -> pd.DataFrame:
    df = run(fn, *a, **k)
    name = f"{fn.__module__.split('.')[-1]}.{fn.__name__}" + (f"({', '.join(repr(x) for x in a)})" if a else "()")
    sections.append(f"### {title}\n\n`{name}`" + (f" — {note}" if note else "") + f"\n\n{md(df)}\n")
    return df


# ── Employee Sentiment ───────────────────────────────────────────────────────
sections.append("## Employee Sentiment (eNPS)\n")
k = add("KPIs", E.kpis)
add("By wave", E.by_wave)
pnl = add("Panel — respondents valid in both waves", E.panel)
seg = {}
for dim in E.SEGMENT_DIMS:
    seg[dim] = add(f"Segment: {E.SEGMENT_DIMS[dim]}", E.segment, dim,
                   note=f"n<{MIN_N} shows — (suppressed); low_response = response rate < 50% (dashboard badge)")
drv = add("Drivers Q2–Q6 by wave", E.drivers)
add("Driver importance (October): correlation with Q1 vs mean", E.driver_importance)
add("Heatmap thread × function (October eNPS)", E.heatmap, "thread", "function")
add("Comment themes by wave", E.themes)
ex = add("April respondents who later exited, by NPS group", E.respondents_who_exited)
nrb_all = add("Non-response bias — overall", E.non_response_bias, None,
              note="panel-eligible only (invited to both waves AND answered in April): APRIL eNPS of October respondents vs "
                   "October non-respondents. Negative gap = the people who skipped October were less positive, so October eNPS is flattered")
nrb = add("Non-response bias — by thread", E.non_response_bias, "thread", note="as above, by thread; low_response = October response rate < 50%")

# ── Hiring ───────────────────────────────────────────────────────────────────
sections.append("## Hiring\n")
hk = add("KPIs", H.kpis)
add("Monthly trend", H.monthly)
add("Funnel", H.funnel)
add("Median days per stage", H.stage_time)
tg = add("TTF by grade", H.ttf_by_grade)
add("Source effectiveness", H.source)
rc = add("Recruiter load vs target", H.recruiters,
         note="two attainment versions over Apr–Oct 2026 (7 months): **_all** = all accepted offers incl. candidates who later "
              "backed out; **_excl_bo** = accepted offers excluding backed-out candidates. Attainment = accepted per month ÷ monthly target. "
              "Note: attainment depends on how many reqs a recruiter is given (see the fair comparison below)")
rcc = add("Recruiter fair comparison (use this to compare recruiters)", H.recruiter_comparison,
          note="per-req measures that do not depend on how many reqs a recruiter was given: filled %, median TTF, % filled "
               "within SLA, open past SLA, accepted offers per assigned req. **Attainment (above) depends on how many reqs a "
               "recruiter is given** — a recruiter with few reqs cannot reach a fixed monthly offer target — so it measures load as "
               "much as performance")
iv = add("Slowest R1 interviewers (min 5 interviews with feedback)", H.interviewers)
ofr = add("Offers by offered / expected CTC ratio", H.offers)
add("Accepted vs declined offers", H.offers_summary)
add("Open req aging (buckets)", H.open_aging_buckets)
add("SLA status: system vs recomputed", H.sla_mismatch)
add("SLA mismatches (list)", H.sla_mismatch_list)
add("Backfills (replacement reqs)", H.backfill)

# ── headline block ───────────────────────────────────────────────────────────
k0, h0, p0 = k.iloc[0], hk.iloc[0], pnl.iloc[0]
rhea = rc[rc.recruiter == "Rhea Kapoor"].iloc[0]
head = [
    f"- eNPS April **{k0.enps_apr:+.1f}** (n = {int(k0.n_apr)} of {int(k0.invited_apr)} invited, response rate {k0.response_rate_apr_pct}%)",
    f"- eNPS October **{k0.enps_oct:+.1f}** (n = {int(k0.n_oct)} of {int(k0.invited_oct)} invited, response rate {k0.response_rate_oct_pct}%)",
    f"- Change **{k0.enps_change:+.1f} pts**; panel of {int(p0.n)} both-wave respondents: {p0.enps_apr:+.1f} → {p0.enps_oct:+.1f} ({p0.enps_change:+.1f} pts)",
    f"- October mix: promoters {k0.pct_promoters_oct}%, passives {k0.pct_passives_oct}%, detractors {k0.pct_detractors_oct}%",
    f"- Requisitions raised **{int(h0.reqs_raised)}**: open {int(h0.open_reqs)}, filled {int(h0.filled_reqs)} "
    f"({int(h0.filled_joined)} joined, {int(h0.filled_yet_to_join)} yet to join), on hold / archived {int(h0.on_hold_or_archived)}",
    f"- Median TTF **{h0.median_ttf_days:g} days** (n = {int(h0.filled_reqs)} filled); within SLA **{h0.pct_within_sla}%**; open past SLA {int(h0.open_past_sla)} of {int(h0.open_reqs)}",
    f"- Offer acceptance **{h0.offer_acceptance_pct}%** ({int(h0.offers_accepted)} / {int(h0.offers_accepted + h0.offers_declined)}); "
    f"joining rate **{h0.joining_rate_pct}%** ({int(h0.joined_of_due)} / {int(h0.joining_due)} due by 31-Oct)",
    f"- Agency fees **₹{h0.agency_fees_lakh} lakh** (₹{h0.agency_fees_inr:,.0f}) on {int(h0.agency_joiners)} agency joiners",
    f"- Rhea Kapoor owns {int(rhea.reqs)} of {int(h0.reqs_raised)} reqs ({rhea.pct_of_reqs}%); attainment {rhea.attainment_all_pct}% "
    f"(all accepted offers, {int(rhea.offers_accepted_all)}) / {rhea.attainment_excl_bo_pct}% (excluding backed-out, {int(rhea.offers_accepted_excl_bo)}) of a {int(rhea.monthly_offer_target)}/month target",
]

# early signals — every number with its n (significance is tested in docs/insights.md)
ms = seg["manager_status"].set_index("segment")
th = seg["thread"].set_index("segment")
exg = ex.set_index("nps_group")
o = ofr.set_index("ratio_band")
g = tg.set_index("grade")
na, nt = nrb_all.iloc[0], nrb.set_index("segment")
slow = iv[iv.median_feedback_days > 2]
others = iv[iv.median_feedback_days <= 2]
def seg_line(name, r):
    return f"{name} {r.enps_apr:+.1f} (n = {int(r.n_apr)}) → {r.enps_oct:+.1f} (n = {int(r.n_oct)})"
signals = [
    f"- Manager status, October eNPS: Changed manager **{ms.loc['Changed manager', 'enps_oct']:+.1f}** (n = {int(ms.loc['Changed manager', 'n_oct'])}) vs "
    f"Same manager {ms.loc['Same manager', 'enps_oct']:+.1f} (n = {int(ms.loc['Same manager', 'n_oct'])}); New joiner (first manager) "
    f"{ms.loc['New joiner (first manager)', 'enps_oct']:+.1f} (n = {int(ms.loc['New joiner (first manager)', 'n_oct'])}). "
    f"Changed-manager cohort in April: {ms.loc['Changed manager', 'enps_apr']:+.1f} (n = {int(ms.loc['Changed manager', 'n_apr'])})",
    f"- Weakest threads: {seg_line('Intercity', th.loc['Intercity'])}; {seg_line('Central', th.loc['Central'])}",
    f"- Response rate collapse with rising eNPS: Enterprise {th.loc['Enterprise', 'response_rate_apr_pct']}% (n = {int(th.loc['Enterprise', 'n_apr'])} of "
    f"{int(th.loc['Enterprise', 'invited_apr'])}) → {th.loc['Enterprise', 'response_rate_oct_pct']}% (n = {int(th.loc['Enterprise', 'n_oct'])} of {int(th.loc['Enterprise', 'invited_oct'])}); "
    f"Packers & Movers {th.loc['Packers & Movers', 'response_rate_apr_pct']}% (n = {int(th.loc['Packers & Movers', 'n_apr'])} of {int(th.loc['Packers & Movers', 'invited_apr'])}) → "
    f"{th.loc['Packers & Movers', 'response_rate_oct_pct']}% (n = {int(th.loc['Packers & Movers', 'n_oct'])} of {int(th.loc['Packers & Movers', 'invited_oct'])})",
    f"- Non-response bias: April eNPS of October non-respondents {na.apr_enps_oct_nonrespondents:+.1f} (n = {int(na.n_oct_nonrespondents)}) vs "
    f"October respondents {na.apr_enps_oct_respondents:+.1f} (n = {int(na.n_oct_respondents)}), gap {na.gap_nonresp_minus_resp:+.1f} pts. "
    f"Packers & Movers {nt.loc['Packers & Movers', 'apr_enps_oct_nonrespondents']:+.1f} (n = {int(nt.loc['Packers & Movers', 'n_oct_nonrespondents'])}) vs "
    f"{nt.loc['Packers & Movers', 'apr_enps_oct_respondents']:+.1f} (n = {int(nt.loc['Packers & Movers', 'n_oct_respondents'])}); "
    f"Enterprise {nt.loc['Enterprise', 'apr_enps_oct_nonrespondents']:+.1f} (n = {int(nt.loc['Enterprise', 'n_oct_nonrespondents'])}) vs "
    f"{nt.loc['Enterprise', 'apr_enps_oct_respondents']:+.1f} (n = {int(nt.loc['Enterprise', 'n_oct_respondents'])})",
    f"- April respondents who later exited: detractors **{exg.loc['Detractor', 'pct_exited']}%** ({int(exg.loc['Detractor', 'exited'])} of n = {int(exg.loc['Detractor', 'n'])}), "
    f"passives {exg.loc['Passive', 'pct_exited']}% ({int(exg.loc['Passive', 'exited'])} of n = {int(exg.loc['Passive', 'n'])}), "
    f"promoters {exg.loc['Promoter', 'pct_exited']}% ({int(exg.loc['Promoter', 'exited'])} of n = {int(exg.loc['Promoter', 'n'])})",
    f"- TTF vs SLA by grade: G6 median {g.loc['G6', 'median_ttf_days']:g} d vs 60-day SLA, {g.loc['G6', 'pct_within_sla']}% within (n = {int(g.loc['G6', 'filled'])} filled); "
    f"G7 {g.loc['G7', 'median_ttf_days']:g} d, {g.loc['G7', 'pct_within_sla']}% within (n = {int(g.loc['G7', 'filled'])}); "
    f"G3 {g.loc['G3', 'median_ttf_days']:g} d vs 45, {g.loc['G3', 'pct_within_sla']}% within (n = {int(g.loc['G3', 'filled'])})",
    "- Slow R1 feedback: " + "; ".join(f"{r.interviewer} median {r.median_feedback_days:g} d (n = {int(r.n)} interviews)" for r in slow.itertuples())
    + f"; the other {len(others)} ranked interviewers have medians ≤ 2 d",
    "- Recruiters, fair comparison (per assigned req): " + "; ".join(
        f"{r.recruiter} {r.filled_pct}% filled, median TTF {r.median_ttf_days:g} d, {r.pct_filled_within_sla}% within SLA, "
        f"{r.accepted_per_assigned_req} accepted / req (n = {int(r.reqs_assigned)} reqs)" for r in rcc.itertuples()),
    f"- Offers below 0.90× expected CTC: **{o.loc['<0.90', 'decline_rate_pct']}%** declined ({int(o.loc['<0.90', 'declined'])} of n = {int(o.loc['<0.90', 'offers'])}) vs "
    f"{o.loc['0.90-0.99', 'decline_rate_pct']}% at 0.90–0.99 ({int(o.loc['0.90-0.99', 'declined'])} of n = {int(o.loc['0.90-0.99', 'offers'])}) and "
    f"{o.loc['1.00-1.09', 'decline_rate_pct']}% at 1.00–1.09 ({int(o.loc['1.00-1.09', 'declined'])} of n = {int(o.loc['1.00-1.09', 'offers'])})",
]
doc = ["# Metric reference",
       "",
       f"Generated by `pipeline/check_metrics.py` on {date.today():%d-%b-%Y} from `data/people.duckdb`, all metrics unfiltered.",
       "This is the reference the dashboard and the deck must match. Do not edit by hand; re-run the script.",
       f"Survey groups with fewer than {MIN_N} respondents show — (suppressed). Percentages are 0–100.",
       "",
       "## Headline numbers",
       ""] + head + ["", "## Early signals (with n; significance tested in docs/insights.md)", ""] + signals + [""] + sections
OUT.write_text("\n".join(doc), encoding="utf-8")
print("\n".join(head + [""] + signals))
print(f"\nWrote {OUT.relative_to(ROOT)} ({len(sections)} sections)")
