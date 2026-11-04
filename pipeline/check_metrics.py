"""
check_metrics.py
----------------
Run every metric in backend/metrics_enps.py and backend/metrics_hiring.py UNFILTERED against
data/people.duckdb, print the headline numbers with n, and write analysis/metric_reference.md.

metric_reference.md is the reference the dashboard (Phase 5 checkpoint) and deck must match.
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
OUT = ROOT / "analysis" / "metric_reference.md"
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
for dim in E.SEGMENT_DIMS:
    add(f"Segment: {E.SEGMENT_DIMS[dim]}", E.segment, dim, note=f"n<{MIN_N} shows — (suppressed)")
drv = add("Drivers Q2–Q6 by wave", E.drivers)
add("Driver importance (October): correlation with Q1 vs mean", E.driver_importance)
add("Heatmap thread × function (October eNPS)", E.heatmap, "thread", "function")
add("Comment themes by wave", E.themes)
ex = add("April respondents who later exited, by NPS group", E.respondents_who_exited)

# ── Hiring ───────────────────────────────────────────────────────────────────
sections.append("## Hiring\n")
hk = add("KPIs", H.kpis)
add("Monthly trend", H.monthly)
add("Funnel", H.funnel)
add("Median days per stage", H.stage_time)
add("TTF by grade", H.ttf_by_grade)
add("Source effectiveness", H.source)
rc = add("Recruiter load vs target", H.recruiters, note="accepted offers per month over Apr–Oct 2026 (7 months), all accepted offers incl. later backouts")
add("Slowest R1 interviewers (min 5 interviews with feedback)", H.interviewers)
add("Offers by offered / expected CTC ratio", H.offers)
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
    f"- Rhea Kapoor owns {int(rhea.reqs)} of {int(h0.reqs_raised)} reqs ({rhea.pct_of_reqs}%); attainment {rhea.attainment_pct}% of target",
]
doc = ["# Metric reference",
       "",
       f"Generated by `pipeline/check_metrics.py` on {date.today():%d-%b-%Y} from `data/people.duckdb`, all metrics unfiltered.",
       "This is the reference the dashboard and the deck must match. Do not edit by hand; re-run the script.",
       f"Survey groups with fewer than {MIN_N} respondents show — (suppressed). Percentages are 0–100.",
       "",
       "## Headline numbers",
       ""] + head + [""] + sections
OUT.write_text("\n".join(doc), encoding="utf-8")
print("\n".join(head))
print(f"\nWrote {OUT.relative_to(ROOT)} ({len(sections)} sections)")
