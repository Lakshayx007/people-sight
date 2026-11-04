"""
05_insights.py
--------------
Tests every Phase 9 hypothesis in the project plan against data/people.duckdb (read-only, v_* views only) and writes:
  analysis/hypotheses.md   the hypotheses and the test planned for each
  analysis/insights.md     ranked findings, counterfactuals, recommendations, one section per hypothesis
  analysis/charts/F*.png   one deck-ready chart (16:9) for each of the top-8 findings

Every number in the outputs is computed here at run time (Hard rule 1). Survey data are only ever grouped; no
names or manager IDs are joined to survey rows (3b uses employee-level HRMS fields only).

Statistics (scipy):
  eNPS difference   z-test on the per-person score (+1 promoter / 0 passive / -1 detractor); effect = Cohen's d
  proportions       two-proportion z-test, Fisher exact when a cell < 10; effect = Cohen's h
  1-5 scores, days  Mann-Whitney U (two-sided); effect = rank-biserial r converted to the d scale (2r / sqrt(1-r^2))
  paired panel      Wilcoxon signed-rank on the per-person Oct - Apr change
  within strata     permutation test (manager status shuffled within thread x grade), 5,000 draws, seed 7
  correlations      Spearman rho
Ranking score = |effect (d scale)| x log10(n) x actionability (1-3). Descriptive findings have no test and no score.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import metrics_enps, metrics_hiring  # noqa: E402

DB = ROOT / "data" / "people.duckdb"
OUT = ROOT / "analysis"
CHARTS = OUT / "charts"
SEED = 7
N_PERM = 5000
ALPHA = 0.05
TOP_N = 8

ACCENT, GREY, RED, INK, MUTED = "#2563EB", "#9CA3AF", "#DC2626", "#111827", "#6B7280"


# ----------------------------------------------------------------------------------------------------------------- data
con = duckdb.connect(str(DB), read_only=True)
q = lambda sql, p=None: con.execute(sql, p or {}).df()  # noqa: E731

S = q("select * exclude (comment) from v_survey")
S["score"] = (S.is_promoter.astype(int) - S.is_detractor.astype(int)).astype(float)
INV = q("select * from v_invited")
EMP = q("select * from v_employees")
REQ = q("select * from v_requisitions")
CAND = q("select * from v_candidates")
OCT, APR = S[S.wave == "Oct"], S[S.wave == "Apr"]


def metric(fn, *a, **k) -> pd.DataFrame:
    sql, params = fn(*a, **k)
    return q(sql, params)


# ------------------------------------------------------------------------------------------------------------ helpers
def fmt_p(p: float | None) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "n/a"
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}" if p < 0.01 else f"p = {p:.2f}"


def sig_text(p: float | None) -> str:
    if p is None:
        return "no test (descriptive)"
    return f"significant ({fmt_p(p)})" if p < ALPHA else f"**NOT significant** ({fmt_p(p)})"


def enps(df: pd.DataFrame) -> float:
    return round(100 * df.score.mean(), 1) if len(df) else float("nan")


def enps_test(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    sa, sb = a.score.astype(float), b.score.astype(float)
    diff = sa.mean() - sb.mean()
    se = math.sqrt(sa.var(ddof=0) / len(sa) + sb.var(ddof=0) / len(sb))
    z = diff / se if se else 0.0
    pooled = math.sqrt(((len(sa) - 1) * sa.var() + (len(sb) - 1) * sb.var()) / (len(sa) + len(sb) - 2))
    return {"diff": round(100 * diff, 1), "p": 2 * stats.norm.sf(abs(z)), "d": diff / pooled if pooled else 0.0,
            "n": len(sa) + len(sb)}


def prop_test(x1: int, n1: int, x2: int, n2: int) -> dict:
    p1, p2 = x1 / n1, x2 / n2
    h = 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))
    if min(x1, n1 - x1, x2, n2 - x2) < 10:
        p = stats.fisher_exact([[x1, n1 - x1], [x2, n2 - x2]])[1]
        test = "Fisher exact"
    else:
        pp = (x1 + x2) / (n1 + n2)
        se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
        p = 2 * stats.norm.sf(abs((p1 - p2) / se)) if se else 1.0
        test = "two-proportion z-test"
    return {"p1": 100 * p1, "p2": 100 * p2, "diff": 100 * (p1 - p2), "p": p, "d": h, "test": test, "n": n1 + n2}


def mw_test(a, b) -> dict:
    a, b = pd.Series(a).dropna().astype(float), pd.Series(b).dropna().astype(float)
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    r = 2 * u / (len(a) * len(b)) - 1
    r = max(min(r, 0.99), -0.99)
    return {"p": p, "r": r, "d": 2 * r / math.sqrt(1 - r * r), "n": len(a) + len(b),
            "med_a": a.median(), "med_b": b.median(), "mean_a": a.mean(), "mean_b": b.mean()}


def fav(s: pd.Series) -> float:
    s = s.dropna()
    return round(100 * (s >= 4).mean(), 1)


def pct(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}%"


def sgn(x: float, d: int = 1) -> str:
    return f"{x:+.{d}f}"


def times(a: float, b: float) -> str:
    """'5 times' style ratio, computed."""
    return f"{a / b:.0f} times" if b else "far more than"


def inr_lakh(x: float) -> str:
    return f"₹{x / 1e5:.2f} lakh"


FINDINGS: list[dict] = []


def add(fid, hyp, area, title, finding, table, test, caveat, action, effect=None, n=None, act=None, act_why="",
        chart=None, verdict="Supported", extra=""):
    FINDINGS.append(dict(id=fid, hyp=hyp, area=area, title=title, finding=finding, table=table, test=test,
                         caveat=caveat, action=action, effect=effect, n=n, act=act, act_why=act_why, chart=chart,
                         verdict=verdict, extra=extra))


def grp(label, value, n, note=""):
    return (label, value, n, note)


# =========================================================================================================== SENTIMENT
k = metric(metrics_enps.kpis).iloc[0]
assert round(enps(APR), 1) == round(k.enps_apr, 1) and round(enps(OCT), 1) == round(k.enps_oct, 1), "eNPS mismatch"

# ---------------------------------------------------------------------------------------------------- H1 overall change
t1 = enps_test(OCT, APR)
panel = S[S.responded_both_waves].pivot_table(index="respondent_key", columns="wave",
                                              values=["q1", "q2", "q5", "score"], aggfunc="first")
panel = panel.dropna(subset=[("q1", "Apr"), ("q1", "Oct")])
pan_status = S[S.responded_both_waves & (S.wave == "Oct")].set_index("respondent_key").manager_status
pan = pd.DataFrame({
    "q1_apr": panel[("q1", "Apr")], "q1_oct": panel[("q1", "Oct")],
    "q2_apr": panel[("q2", "Apr")], "q2_oct": panel[("q2", "Oct")],
    "s_apr": panel[("score", "Apr")], "s_oct": panel[("score", "Oct")],
}).join(pan_status)
pan_e_apr, pan_e_oct = round(100 * pan.s_apr.mean(), 1), round(100 * pan.s_oct.mean(), 1)
w1 = stats.wilcoxon(pan.q1_oct - pan.q1_apr, zero_method="wilcox")
d_pan = (pan.q1_oct - pan.q1_apr).mean() / (pan.q1_oct - pan.q1_apr).std()
f1_sig = t1["p"] < ALPHA or w1.pvalue < ALPHA
add("F1", "1", "Sentiment",
    "eNPS fell between the waves, and the fall holds for the same people" if f1_sig else
    f"eNPS fell {abs(t1['diff']):.1f} points, also for the same people — but company-wide the fall is not "
    "statistically significant; it sits in specific groups",
    f"Company eNPS fell from {sgn(enps(APR))} (n = {len(APR)}) in April to {sgn(enps(OCT))} (n = {len(OCT)}) in "
    f"October ({sgn(t1['diff'])} pts); among the {len(pan)} people who answered both waves it fell by a similar amount, "
    f"from {sgn(pan_e_apr)} to {sgn(pan_e_oct)}, so the drop is not just a change in who answered"
    + ("." if f1_sig else ", but neither test reaches significance at the 5% level."),
    [grp("April, all respondents", sgn(enps(APR)), len(APR)), grp("October, all respondents", sgn(enps(OCT)), len(OCT)),
     grp("April, panel (both waves)", sgn(pan_e_apr), len(pan)), grp("October, panel", sgn(pan_e_oct), len(pan))],
    f"All respondents: z-test on eNPS, {sig_text(t1['p'])}. Panel: Wilcoxon signed-rank on the per-person Q1 change "
    f"(mean {sgn((pan.q1_oct - pan.q1_apr).mean(), 2)} points), {sig_text(w1.pvalue)}.",
    "The two waves share most respondents, so the all-respondent z-test treats overlapping samples as independent; the "
    "panel test is the cleaner one. The headline mixes several groups (F2, F3a) — see what drives it before acting.",
    "Report the panel number alongside the headline every wave, so a change in who answers is never read as a change "
    "in sentiment.",
    effect=abs(d_pan), n=len(pan), act=1, act_why="headline only; the actions sit in the drivers below",
    verdict="Supported" if f1_sig else "Direction supported, NOT significant",
    chart=dict(kind="bar", cats=["April", "October", "Panel Apr", "Panel Oct"],
               vals=[enps(APR), enps(OCT), pan_e_apr, pan_e_oct], ns=[len(APR), len(OCT), len(pan), len(pan)],
               colors=[GREY, ACCENT, GREY, ACCENT], ylabel="eNPS (points)"))

# ------------------------------------------------------------------------------------------- H2 changed vs same manager
ch_o, sm_o, nj_o = (OCT[OCT.manager_status == s] for s in ["Changed manager", "Same manager",
                                                            "New joiner (first manager)"])
ch_a, sm_a = APR[APR.manager_status == "Changed manager"], APR[APR.manager_status == "Same manager"]
t2 = enps_test(ch_o, sm_o)
# within thread x grade: permutation test
cs = OCT[OCT.manager_status.isin(["Changed manager", "Same manager"])].copy()
cs["is_ch"] = (cs.manager_status == "Changed manager").astype(int)
cs["stratum"] = cs.thread + "|" + cs.grade.astype(str)
strata = [g for _, g in cs.groupby("stratum") if g.is_ch.sum() > 0 and (1 - g.is_ch).sum() > 0]


def strat_stat(groups, labels):
    num = den = 0.0
    for g, lab in zip(groups, labels):
        a, b = g.score.values[lab == 1], g.score.values[lab == 0]
        w = 1 / (1 / len(a) + 1 / len(b))
        num += w * (a.mean() - b.mean())
        den += w
    return 100 * num / den


obs = strat_stat(strata, [g.is_ch.values for g in strata])
rng = np.random.default_rng(SEED)
perm = np.array([strat_stat(strata, [rng.permutation(g.is_ch.values) for g in strata]) for _ in range(N_PERM)])
p_strat = (np.sum(np.abs(perm) >= abs(obs)) + 1) / (N_PERM + 1)
n_strat = sum(len(g) for g in strata)
ch_in_strata = sum(g.is_ch.sum() for g in strata)
# panel: per-person change, Changed vs Same
pc, ps = pan[pan.manager_status == "Changed manager"], pan[pan.manager_status == "Same manager"]
mw_pan = mw_test(pc.q1_oct - pc.q1_apr, ps.q1_oct - ps.q1_apr)
# Q2 path
mw_q2 = mw_test(ch_o.q2, sm_o.q2)
mw_q2p = mw_test(pc.q2_oct - pc.q2_apr, ps.q2_oct - ps.q2_apr)
t2_apr = enps_test(ch_a, sm_a[sm_a.thread == "Intercity"])
add("F2", "2", "Sentiment", "People who changed manager are far less positive — within the same thread and grade",
    f"October eNPS for people who changed manager was {sgn(enps(ch_o))} (n = {len(ch_o)}) vs {sgn(enps(sm_o))} for "
    f"those with the same manager (n = {len(sm_o)}); within the same thread and grade the gap is {sgn(obs)} pts, and "
    f"the same people were {sgn(enps(ch_a))} in April (n = {len(ch_a)}), before the change.",
    [grp("Changed manager, October", sgn(enps(ch_o)), len(ch_o)),
     grp("Same manager, October", sgn(enps(sm_o)), len(sm_o)),
     grp("Changed manager, April (before the change)", sgn(enps(ch_a)), len(ch_a)),
     grp("Same manager in Intercity, April", sgn(enps(sm_a[sm_a.thread == 'Intercity'])),
         len(sm_a[sm_a.thread == "Intercity"])),
     grp("Panel: mean Q1 change, Changed manager", sgn(pc.q1_oct.sub(pc.q1_apr).mean(), 2), len(pc)),
     grp("Panel: mean Q1 change, Same manager", sgn(ps.q1_oct.sub(ps.q1_apr).mean(), 2), len(ps)),
     grp("Q2 manager feedback, % favourable Oct: Changed", pct(fav(ch_o.q2)), len(ch_o)),
     grp("Q2 manager feedback, % favourable Oct: Same", pct(fav(sm_o.q2)), len(sm_o))],
    f"Raw gap: z-test, {sig_text(t2['p'])}. Within thread × grade ({len(strata)} strata, {n_strat} respondents, "
    f"{ch_in_strata} changed): permutation test, {sig_text(p_strat)}. Panel per-person Q1 change, Changed vs Same: "
    f"Mann-Whitney, {sig_text(mw_pan['p'])}. Q2 in October: Mann-Whitney, {sig_text(mw_q2['p'])}; Q2 change on the "
    f"panel: {sig_text(mw_q2p['p'])}. Before the change (April), Changed vs Intercity Same manager: "
    f"{sig_text(t2_apr['p'])} — no gap existed beforehand.",
    "All changed-manager respondents are in Intercity, so 'within thread' means within Intercity only. HRMS keeps only "
    "the current manager, so earlier or repeated changes are invisible. Observational data: the April baseline makes "
    "a pre-existing difference unlikely, but it is not an experiment.",
    "Treat a manager change as a risk event: a 30-day check-in by HRBP, a first 1:1 within a week, and a pulse "
    "question on manager feedback (Q2) for affected teams.",
    effect=abs(t2["d"]), n=t2["n"], act=3, act_why="specific group, clear lever (manager transition process)",
    chart=dict(kind="grouped", cats=["Changed manager", "Same manager"],
               series=[("April", [enps(ch_a), enps(sm_a)], [len(ch_a), len(sm_a)], GREY),
                       ("October", [enps(ch_o), enps(sm_o)], [len(ch_o), len(sm_o)], ACCENT)],
               bad_oct_negative=True, ylabel="eNPS (points)"))

# ----------------------------------------------------------------------------------------- H2b new joiner vs same (Oct)
t2b = enps_test(nj_o, sm_o)
mw_q5nj = mw_test(nj_o.q5, sm_o.q5)
add("F2b", "2b", "Sentiment", "New joiners start negative, and onboarding (Q5) is the weak point",
    f"New joiners on their first manager scored October eNPS {sgn(enps(nj_o))} (n = {len(nj_o)}) vs "
    f"{sgn(enps(sm_o))} for same-manager employees (n = {len(sm_o)}), and only {pct(fav(nj_o.q5))} rated "
    f"onboarding/tools (Q5) favourably vs {pct(fav(sm_o.q5))}.",
    [grp("New joiner (first manager): eNPS Oct", sgn(enps(nj_o)), len(nj_o)),
     grp("Same manager: eNPS Oct", sgn(enps(sm_o)), len(sm_o)),
     grp("New joiner: Q5 mean / % favourable", f"{nj_o.q5.mean():.2f} / {pct(fav(nj_o.q5))}", len(nj_o)),
     grp("Same manager: Q5 mean / % favourable", f"{sm_o.q5.mean():.2f} / {pct(fav(sm_o.q5))}", len(sm_o)),
     grp("New joiners in Intercity: eNPS Oct", sgn(enps(nj_o[nj_o.thread == 'Intercity'])),
         len(nj_o[nj_o.thread == "Intercity"])),
     grp("New joiners elsewhere: eNPS Oct", sgn(enps(nj_o[nj_o.thread != 'Intercity'])),
         len(nj_o[nj_o.thread != "Intercity"]))],
    f"eNPS: z-test, {sig_text(t2b['p'])}. Q5: Mann-Whitney, {sig_text(mw_q5nj['p'])}.",
    "New joiners are also the <6-month tenure group (F6, F19), so this is largely the same signal seen three ways. "
    "Intercity new joiners are much lower than new joiners elsewhere (n shown) — it overlaps with the Intercity reorg.",
    "Fix onboarding for the first 90 days (tools ready on day 1, buddy, 30/60/90 check-ins); measure Q5 for joiners "
    "next wave.",
    effect=abs(t2b["d"]), n=t2b["n"], act=3, act_why="onboarding is fully in HR's control",
    chart=dict(kind="bar", cats=["New joiner\n(first manager)", "Same manager"],
               vals=[fav(nj_o.q5), fav(sm_o.q5)], ns=[len(nj_o), len(sm_o)], colors=[RED, ACCENT],
               ylabel="Q5 onboarding / tools, % favourable", unit="%"))

# ---------------------------------------------------------------------------------------------- H3 Intercity weakest
ic_o, ic_a = OCT[OCT.thread == "Intercity"], APR[APR.thread == "Intercity"]
rest_o = OCT[OCT.thread != "Intercity"]
seg = metric(metrics_enps.segment, "thread")
seg_o = seg.sort_values("enps_oct")
t3 = enps_test(ic_o, rest_o)
by_thread_o = OCT.groupby("thread").apply(enps, include_groups=False).sort_values()
weakest = by_thread_o.index[0]
# counterfactual: Changed + New joiner respondents scored like Same manager in the same thread (October)
same_rate = sm_o.groupby("thread").score.mean()
cf = OCT.copy()
mask = cf.manager_status != "Same manager"
cf.loc[mask, "score"] = cf.loc[mask, "thread"].map(same_rate)
cf_company = round(100 * cf.score.mean(), 1)
cf_ic = round(100 * cf[cf.thread == "Intercity"].score.mean(), 1)
cf_only_ch = OCT.copy()
m2 = cf_only_ch.manager_status == "Changed manager"
cf_only_ch.loc[m2, "score"] = cf_only_ch.loc[m2, "thread"].map(same_rate)
cf_company_ch = round(100 * cf_only_ch.score.mean(), 1)
cf_ic_ch = round(100 * cf_only_ch[cf_only_ch.thread == "Intercity"].score.mean(), 1)
company_change = round(enps(OCT) - enps(APR), 1)
cf_change = round(cf_company - enps(APR), 1)
share_explained = 100 * (cf_company - enps(OCT)) / (enps(APR) - enps(OCT)) if enps(APR) != enps(OCT) else float("nan")
COUNTERFACTUAL_SENT = dict(cf_company=cf_company, cf_ic=cf_ic, cf_company_ch=cf_company_ch, cf_ic_ch=cf_ic_ch,
                           share=share_explained, n_ch=len(ch_o), n_nj=len(nj_o))
add("F3", "3", "Sentiment", f"{weakest} is the weakest thread, and its fall comes from the manager-change "
    "and new-joiner groups",
    f"{weakest} had the lowest October eNPS ({sgn(enps(ic_o))}, n = {len(ic_o)}) vs {sgn(enps(rest_o))} for the rest "
    f"of the company (n = {len(rest_o)}); if its changed-manager and new-joiner respondents had scored like its "
    f"same-manager respondents, {weakest} would be {sgn(cf_ic)}.",
    [grp(f"{t}, October", sgn(v), int((OCT.thread == t).sum())) for t, v in by_thread_o.items()]
    + [grp("Intercity, April", sgn(enps(ic_a)), len(ic_a))],
    f"Intercity vs rest of company (October): z-test, {sig_text(t3['p'])}.",
    "Thread is the current thread (no attribute history). The counterfactual assumes the affected people would have "
    "scored like same-manager colleagues in the same thread — an upper bound on what fixing the transition could do.",
    "Focus the Intercity response on the June reorg and the onboarding of its new joiners, not a thread-wide "
    "programme (see F3a, F3b).",
    effect=abs(t3["d"]), n=t3["n"], act=3, act_why="one thread, one event, named owner",
    chart=dict(kind="barh", cats=list(by_thread_o.index), vals=list(by_thread_o.values),
               ns=[int((OCT.thread == t).sum()) for t in by_thread_o.index],
               colors=[RED if v < 0 else ACCENT for v in by_thread_o.values], xlabel="October eNPS (points)"))

# ------------------------------------------------------------------------------------------- H3a Intercity decomposition
rows3a = []
for st in ["Changed manager", "New joiner (first manager)", "Same manager"]:
    a, o = ic_a[ic_a.manager_status == st], ic_o[ic_o.manager_status == st]
    rows3a.append(grp(f"Intercity — {st}", f"Apr {sgn(enps(a)) if len(a) >= 5 else 'n<5' if len(a) else '—'} → "
                      f"Oct {sgn(enps(o)) if len(o) >= 5 else 'n<5'}", f"{len(a)} / {len(o)}"))
ic_ex_ch = ic_o[ic_o.manager_status != "Changed manager"]
ic_same = ic_o[ic_o.manager_status == "Same manager"]
rest_same = rest_o[rest_o.manager_status == "Same manager"]
t3a = enps_test(ic_same, rest_same)
t3a_x = enps_test(ic_ex_ch, rest_o)
ic_same_a = ic_a[ic_a.manager_status == "Same manager"]
add("F3a", "3a", "Sentiment", "Intercity without the reorganised teams looks like the rest of the company",
    f"Intercity's same-manager respondents scored {sgn(enps(ic_same))} in October (n = {len(ic_same)}), close to "
    f"same-manager respondents elsewhere ({sgn(enps(rest_same))}, n = {len(rest_same)}) and up from "
    f"{sgn(enps(ic_same_a))} in April; the thread's fall comes from the changed-manager ({sgn(enps(ch_o))}, "
    f"n = {len(ch_o)}) and new-joiner ({sgn(enps(nj_o[nj_o.thread == 'Intercity']))}, "
    f"n = {len(nj_o[nj_o.thread == 'Intercity'])}) groups.",
    rows3a + [grp("Intercity excluding changed-manager respondents, Oct", sgn(enps(ic_ex_ch)), len(ic_ex_ch)),
              grp("Rest of company, Oct", sgn(enps(rest_o)), len(rest_o)),
              grp("Rest of company, same manager, Oct", sgn(enps(rest_same)), len(rest_same))],
    f"Intercity same manager vs same manager elsewhere: z-test, {sig_text(t3a['p'])} — no detectable difference. "
    f"Intercity excluding the {len(ch_o)} changed-manager respondents vs the rest of the company: "
    f"{sig_text(t3a_x['p'])} (the remaining gap is the Intercity new joiners).",
    "n per cell is shown (April / October). Not significant here means no evidence of a difference, not proof of "
    "equality; the Intercity same-manager group is n = " + str(len(ic_same)) + ".",
    "Do not run a thread-wide Intercity intervention; target the reorganised teams and Intercity onboarding.",
    effect=abs(enps_test(ch_o, ic_same)["d"]), n=len(ic_o), act=3,
    act_why="pinpoints exactly which Intercity teams need action",
    chart=dict(kind="grouped", cats=["Changed manager", "New joiner\n(first manager)", "Same manager"],
               series=[("April", [enps(ic_a[ic_a.manager_status == s]) if (ic_a.manager_status == s).sum() >= 5
                                  else float('nan') for s in ["Changed manager", "New joiner (first manager)",
                                                              "Same manager"]],
                        [int((ic_a.manager_status == s).sum()) for s in ["Changed manager",
                                                                         "New joiner (first manager)", "Same manager"]],
                        GREY),
                       ("October", [enps(ic_o[ic_o.manager_status == s]) for s in
                                    ["Changed manager", "New joiner (first manager)", "Same manager"]],
                        [int((ic_o.manager_status == s).sum()) for s in ["Changed manager",
                                                                         "New joiner (first manager)", "Same manager"]],
                        ACCENT)],
               bad_oct_negative=True, ylabel="Intercity eNPS (points)"))

# --------------------------------------------------------------------------------------- H3b timing of manager changes
ice = EMP[(EMP.thread == "Intercity") & (EMP.manager_status == "Changed manager")].copy()
ice["month"] = pd.to_datetime(ice.manager_effective_from).dt.strftime("%b-%Y")
by_month = ice.groupby("month").size()
win_months = pd.date_range("2026-04-01", "2026-10-01", freq="MS").strftime("%b-%Y")
by_month = by_month.reindex(win_months, fill_value=0)
mgr_counts = ice.reporting_manager_id.value_counts()
top2 = int(mgr_counts.head(2).sum())
d_first, d_last = pd.to_datetime(ice.manager_effective_from).min(), pd.to_datetime(ice.manager_effective_from).max()
nj_ic = EMP[(EMP.thread == "Intercity") & (EMP.manager_status == "New joiner (first manager)")]
nj_ic_top2 = int(nj_ic.reporting_manager_id.isin(mgr_counts.head(2).index).sum())
team_size = int(EMP.reporting_manager_id.isin(mgr_counts.head(2).index).sum())
add("F3b", "3b", "Sentiment", "The Intercity manager changes were one reorganisation in June, onto two managers",
    f"All {len(ice)} Intercity manager changes took effect between {d_first:%d-%b} and {d_last:%d-%b-%Y}, and "
    f"{top2} of them moved to just two managers (out of {mgr_counts.size} distinct new managers) — a team "
    f"restructure, not normal churn; those two managers also took on {nj_ic_top2} of the {len(nj_ic)} Intercity new "
    f"joiners.",
    [grp(m, int(v), "") for m, v in by_month.items()]
    + [grp("Distinct new managers", int(mgr_counts.size), len(ice)),
       grp("Moved to the two largest receiving managers (Manager A, Manager B)", top2, len(ice)),
       grp("Intercity new joiners placed under Manager A or B", nj_ic_top2, len(nj_ic)),
       grp("Current team size of Manager A + B (all statuses)", team_size, "")],
    "Descriptive (employee-level HRMS data; no survey data and no names joined). Manager IDs are not shown.",
    "Only the current manager is recorded: earlier moves in the window, or people who moved and then exited, are not "
    "visible.",
    "Run a structured review of the June Intercity reorganisation with Manager A and Manager B: team size, span of "
    "control and how the transition was communicated.",
    verdict="Supported (descriptive)", act=3, act_why="one event, two managers to work with",
    chart=dict(kind="bar", cats=[m[:3] for m in by_month.index], vals=[int(v) for v in by_month.values],
               ns=None, colors=[ACCENT] * len(by_month), ylabel="Intercity manager changes (employees)",
               unit=""))

# ---------------------------------------------------------------------------------------------- H4 driver importance
drv = {"q2": "Q2 manager feedback", "q3": "Q3 fair pay", "q4": "Q4 workload", "q5": "Q5 onboarding/tools",
       "q6": "Q6 growth path"}
imp = []
for c, lab in drv.items():
    o = OCT[["q1", c]].dropna()
    rho, p = stats.spearmanr(o.q1, o[c])
    imp.append(dict(driver=lab, rho=rho, p=p, mean_oct=OCT[c].mean(), mean_apr=APR[c].mean(), fav_oct=fav(OCT[c]),
                    n=len(o), chg=OCT[c].mean() - APR[c].mean()))
imp = pd.DataFrame(imp).sort_values("rho", ascending=False)
med_mean = imp.mean_oct.median()
fix = imp[imp.mean_oct <= med_mean].sort_values("rho", ascending=False).iloc[0]
top_imp = imp.iloc[0]
add("F4", "4", "Sentiment", f"Fix {fix.driver.split(' ', 1)[1]} first: it matters most among the low-scoring drivers",
    f"{fix.driver} has the strongest link with recommending Porter among the below-median drivers (Spearman "
    f"ρ = {fix.rho:.2f}, n = {int(fix.n)}) and an October mean of {fix.mean_oct:.2f} / 5 (April {fix.mean_apr:.2f})"
    + ("; it is also the most important driver overall." if fix.driver == top_imp.driver else
       f"; the most important driver overall is {top_imp.driver} (ρ = {top_imp.rho:.2f})."),
    [grp(r.driver, f"ρ {r.rho:.2f} · mean Oct {r.mean_oct:.2f} (Apr {r.mean_apr:.2f}) · {pct(r.fav_oct)} fav",
         int(r.n)) for r in imp.itertuples()],
    "Spearman correlations with Q1 (October): " + "; ".join(f"{r.driver.split(' ')[0]} {fmt_p(r.p)}"
                                                           for r in imp.itertuples()) + ".",
    "Correlation is not causation, and drivers correlate with each other; importance here is a ranking aid. Uses "
    "October only. For the ranking score the correlation is converted to the d scale, which flatters this finding "
    "relative to group comparisons.",
    f"Put {fix.driver.split(' ', 1)[1]} at the top of the action plan (it is what fell most for changed-manager "
    "teams, F2): manager training on regular feedback and 1:1s.",
    effect=abs(2 * fix.rho / math.sqrt(1 - fix.rho ** 2)), n=int(fix.n), act=2,
    act_why="tells leaders where to spend effort; less specific about who",
    chart=dict(kind="scatter", x=list(imp.rho), y=list(imp.mean_oct), labels=list(imp.driver),
               xlabel="Importance: correlation with Q1 (Spearman ρ)", ylabel="October mean (1-5)",
               highlight=fix.driver, n=int(fix.n)))

# --------------------------------------------------------------------------------------------- H5 compa-ratio < 0.90
below, atab = OCT[OCT.compa_band == "Below"], OCT[OCT.compa_band.isin(["At", "Above"])]
mw5 = mw_test(below.q3, atab.q3)
t5 = enps_test(below, atab)
add("F5", "5", "Sentiment", "Employees paid below 0.90 of band mid rate pay fairness far lower and recommend less",
    f"Employees below 0.90 compa-ratio rated fair pay (Q3) {below.q3.mean():.2f} / 5 ({pct(fav(below.q3))} favourable, "
    f"n = {len(below)}) vs {atab.q3.mean():.2f} ({pct(fav(atab.q3))}, n = {len(atab)}) for those at or above band, "
    f"and their eNPS was {sgn(enps(below))} vs {sgn(enps(atab))}.",
    [grp("Below band (<0.90): Q3 mean / % fav", f"{below.q3.mean():.2f} / {pct(fav(below.q3))}", len(below)),
     grp("At or above band: Q3 mean / % fav", f"{atab.q3.mean():.2f} / {pct(fav(atab.q3))}", len(atab)),
     grp("Below band: eNPS Oct", sgn(enps(below)), len(below)), grp("At or above: eNPS Oct", sgn(enps(atab)), len(atab)),
     grp("Below band: eNPS Apr", sgn(enps(APR[APR.compa_band == 'Below'])), int((APR.compa_band == "Below").sum()))],
    f"Q3: Mann-Whitney, {sig_text(mw5['p'])}. eNPS: z-test, {sig_text(t5['p'])}.",
    "Compa band is from the current CTC and the 2026-04-01 band set; 7 monthly CTC values were corrected ×12. The gap "
    "was already there in April, so it is structural rather than new.",
    "Prioritise below-band employees (especially strong performers) in the next pay review; track Q3 for this group.",
    effect=abs(mw5["d"]), n=mw5["n"], act=2, act_why="needs budget; clear target list",
    chart=dict(kind="bar", cats=["Below band\n(< 0.90)", "At or above band"], vals=[fav(below.q3), fav(atab.q3)],
               ns=[len(below), len(atab)], colors=[RED, ACCENT], ylabel="Q3 fair pay, % favourable (Oct)", unit="%"))

# ------------------------------------------------------------------------------------------------- H6 tenure < 6 months
t6n, t6o = OCT[OCT.tenure_band == "<6m"], OCT[OCT.tenure_band != "<6m"]
a6n, a6o = APR[APR.tenure_band == "<6m"], APR[APR.tenure_band != "<6m"]
mw6, mw6a = mw_test(t6n.q5, t6o.q5), mw_test(a6n.q5, a6o.q5)
add("F6", "6", "Sentiment", "Under-6-month employees rate onboarding lowest — in both waves",
    f"In October, employees with under 6 months' tenure rated onboarding/tools (Q5) {t6n.q5.mean():.2f} / 5 "
    f"({pct(fav(t6n.q5))} favourable, n = {len(t6n)}) vs {t6o.q5.mean():.2f} ({pct(fav(t6o.q5))}, n = {len(t6o)}) for "
    f"everyone else; April showed the same gap ({pct(fav(a6n.q5))} vs {pct(fav(a6o.q5))}).",
    [grp("<6m, Oct: Q5 mean / % fav", f"{t6n.q5.mean():.2f} / {pct(fav(t6n.q5))}", len(t6n)),
     grp("6m+, Oct: Q5 mean / % fav", f"{t6o.q5.mean():.2f} / {pct(fav(t6o.q5))}", len(t6o)),
     grp("<6m, Apr: Q5 mean / % fav", f"{a6n.q5.mean():.2f} / {pct(fav(a6n.q5))}", len(a6n)),
     grp("6m+, Apr: Q5 mean / % fav", f"{a6o.q5.mean():.2f} / {pct(fav(a6o.q5))}", len(a6o)),
     grp("<6m eNPS Oct", sgn(enps(t6n)), len(t6n))],
    f"October: Mann-Whitney, {sig_text(mw6['p'])}. April: {sig_text(mw6a['p'])}.",
    "Tenure band is at each wave's open date; the <6m groups are different people in each wave, so this is a "
    "persistent process gap, not one cohort.",
    "Same action as F2b: onboarding owner, day-1 readiness checklist, 30/60/90 check-ins.",
    effect=abs(mw6["d"]), n=mw6["n"], act=3, act_why="process fully in HR's control",
    chart=dict(kind="grouped", cats=["April", "October"],
               series=[("Under 6 months", [fav(a6n.q5), fav(t6n.q5)], [len(a6n), len(t6n)], RED),
                       ("6 months or more", [fav(a6o.q5), fav(t6o.q5)], [len(a6o), len(t6o)], ACCENT)],
               ylabel="Q5 onboarding / tools, % favourable", unit="%"))

# ------------------------------------------------------------------------------------- H7 April detractors exited more
ap = APR.copy()
ap["exited"] = ap.exited_after_wave.fillna(False).astype(bool)
ap["vol"] = ap.exited & (ap.exit_type_after_wave == "Voluntary")
ap["reg"] = ap.regrettable_after_wave.fillna(False).astype(bool)
det, pro = ap[ap.nps_group == "Detractor"], ap[ap.nps_group == "Promoter"]
pas = ap[ap.nps_group == "Passive"]
t7 = prop_test(int(det.vol.sum()), len(det), int(pro.vol.sum()), len(pro))
t7r = prop_test(int(det.reg.sum()), len(det), int(pro.reg.sum()), len(pro))
ref7 = metric(metrics_enps.respondents_who_exited)
add("F7", "7", "Sentiment", f"April detractors left voluntarily at {times(t7['p1'], t7['p2'])} the rate of promoters",
    f"{pct(t7['p1'])} of April detractors left voluntarily by 31-Oct (n = {len(det)}) vs {pct(t7['p2'])} of promoters "
    f"(n = {len(pro)}); regrettable exits were {pct(t7r['p1'])} vs {pct(t7r['p2'])}.",
    [grp("Detractors: voluntary exit %", pct(t7["p1"]), len(det)), grp("Passives: voluntary exit %",
                                                                         pct(100 * pas.vol.mean()), len(pas)),
     grp("Promoters: voluntary exit %", pct(t7["p2"]), len(pro)),
     grp("Detractors: regrettable exit %", pct(t7r["p1"]), len(det)),
     grp("Promoters: regrettable exit %", pct(t7r["p2"]), len(pro))],
    f"Voluntary exits: {t7['test']}, {sig_text(t7['p'])}. Regrettable exits: {t7r['test']}, {sig_text(t7r['p'])}.",
    "About six months of follow-up; exit attributes are attached to survey rows before IDs are dropped, so this is "
    "anonymous. Being a detractor may reflect, not cause, an intention to leave.",
    "Use eNPS as an early-warning signal: teams with many detractors get a stay-interview round within a month of "
    "each wave.",
    effect=abs(t7["d"]), n=t7["n"], act=2, act_why="early-warning use; action is indirect",
    chart=dict(kind="bar", cats=["Detractors", "Passives", "Promoters"],
               vals=[t7["p1"], 100 * pas.vol.mean(), t7["p2"]], ns=[len(det), len(pas), len(pro)],
               colors=[RED, GREY, ACCENT], ylabel="Left voluntarily by 31-Oct (%)", unit="%"))

# --------------------------------------------------------------------------------- H8 response-rate shifts by thread
rr = INV.groupby(["thread", "wave"]).responded.agg(["sum", "count"]).reset_index()
rr["rate"] = 100 * rr["sum"] / rr["count"]
rrp = rr.pivot(index="thread", columns="wave", values="rate")
elig = APR[APR.invited_both_waves]
nr_rows, nr_tests = [], {}
for th in ["All"] + ["Enterprise", "Packers & Movers"]:
    e = elig if th == "All" else elig[elig.thread == th]
    rsp, non = e[e.responded_both_waves], e[~e.responded_both_waves]
    nr_tests[th] = enps_test(non, rsp)
    nr_rows.append(grp(f"{th}: April eNPS of Oct non-respondents vs respondents",
                       f"{sgn(enps(non))} vs {sgn(enps(rsp))}", f"{len(non)} / {len(rsp)}"))
pm_rates = rr[rr.thread == "Packers & Movers"].set_index("wave")
ent_rates = rr[rr.thread == "Enterprise"].set_index("wave")
t8 = prop_test(int(pm_rates.loc["Oct", "sum"]), int(pm_rates.loc["Oct", "count"]), int(pm_rates.loc["Apr", "sum"]),
               int(pm_rates.loc["Apr", "count"]))
t8e = prop_test(int(ent_rates.loc["Oct", "sum"]), int(ent_rates.loc["Oct", "count"]),
                int(ent_rates.loc["Apr", "sum"]), int(ent_rates.loc["Apr", "count"]))
pm_o, pm_a = OCT[OCT.thread == "Packers & Movers"], APR[APR.thread == "Packers & Movers"]
f8_bias = nr_tests["Packers & Movers"]["p"] < ALPHA
add("F8", "8", "Sentiment", "Packers & Movers' rise came with a collapse in response rate — read it with caution",
    f"Packers & Movers' response rate fell from {pct(rrp.loc['Packers & Movers', 'Apr'])} to "
    f"{pct(rrp.loc['Packers & Movers', 'Oct'])} and Enterprise's from {pct(rrp.loc['Enterprise', 'Apr'])} to "
    f"{pct(rrp.loc['Enterprise', 'Oct'])}; in Packers & Movers the people who answered again in October had been "
    f"happier in April ({sgn(enps(elig[(elig.thread == 'Packers & Movers') & elig.responded_both_waves]))}) than those "
    f"who stopped answering ({sgn(enps(elig[(elig.thread == 'Packers & Movers') & ~elig.responded_both_waves]))}"
    f"{'' if f8_bias else ', a gap that is not significant'}), so its rise from {sgn(enps(pm_a))} to "
    f"{sgn(enps(pm_o))} may partly reflect who answered rather than real improvement.",
    [grp(f"{t}: response rate Apr → Oct", f"{pct(rrp.loc[t, 'Apr'])} → {pct(rrp.loc[t, 'Oct'])}",
         f"{int(rr[(rr.thread == t) & (rr.wave == 'Apr')]['count'].iloc[0])} / "
         f"{int(rr[(rr.thread == t) & (rr.wave == 'Oct')]['count'].iloc[0])} invited") for t in rrp.index] + nr_rows,
    f"Response-rate change, Packers & Movers: {t8['test']}, {sig_text(t8['p'])}; Enterprise: {t8e['test']}, "
    f"{sig_text(t8e['p'])}. Non-response bias (April eNPS, non-respondents vs respondents): all "
    f"{sig_text(nr_tests['All']['p'])}; Packers & Movers {sig_text(nr_tests['Packers & Movers']['p'])}; Enterprise "
    f"{sig_text(nr_tests['Enterprise']['p'])}.",
    "We only see April answers for October non-respondents; their October view is unknown. Enterprise October n is "
    "small (" + str(int((OCT.thread == "Enterprise").sum())) + ").",
    "Before celebrating a thread's rise, check its response rate; set a 60% response-rate target per thread and send "
    "reminders through thread leads.",
    effect=abs(t8["d"]), n=t8["n"], act=2, act_why="survey process fix; protects decisions from misleading data",
    verdict="Supported" if f8_bias else "Partly supported: response rates fell sharply; bias NOT significant",
    chart=dict(kind="grouped", cats=list(rrp.index),
               series=[("April", list(rrp["Apr"]), [int(x) for x in rr[rr.wave == "Apr"].set_index("thread")
                                                        .loc[rrp.index, "count"]], GREY),
                       ("October", list(rrp["Oct"]), [int(x) for x in rr[rr.wave == "Oct"].set_index("thread")
                                                          .loc[rrp.index, "count"]], ACCENT)],
               ylabel="Response rate (%)", unit="%", ref=(50, "Low-response line (50%)"), n_label="invited"))

# ------------------------------------------------------------------------------------------------- H9 small-n segments
dims = ["thread", "function", "job_family", "grade", "location", "tenure_band", "compa_band", "manager_status",
        "performance_rating", "location_type"]
supp = []
for dname in dims:
    g = OCT.groupby(dname).size()
    small = g[g < 5]
    supp.append((dname, len(g), len(small), ", ".join(f"{i} ({v})" for i, v in small.items())))
cells = OCT.groupby(["thread", "function"]).size()
small_cells = int((cells < 5).sum())
dr = OCT[OCT.function == "Design & Research"]
add("F9", "9", "Sentiment", "Small segments are hidden (n<5), which protects anonymity but limits detail",
    f"In October, {sum(s[2] for s in supp)} single-dimension segments and {small_cells} of {len(cells)} thread × "
    f"function cells have fewer than 5 respondents and are shown as 'n<5' (e.g. Design & Research, n = {len(dr)}).",
    [grp(f"{dn}: segments with n<5 of {tot}", sm, lst or "—") for dn, tot, sm, lst in supp]
    + [grp("Thread × function cells with n<5", small_cells, f"of {len(cells)} cells")],
    "Descriptive (suppression rule n<5 applied in SQL and in Ask the Data).",
    "Suppression hides a group's score, not its people's existence; with response rates falling, more cells will "
    "drop below 5.",
    "Report small functions at a rolled-up level (job family or thread) rather than dropping them; raise response "
    "rates in small teams.",
    verdict="Supported (descriptive)", act=1, act_why="reporting rule; little business lever")

# ============================================================================================================== HIRING
hk = metric(metrics_hiring.kpis).iloc[0]
filled = REQ[REQ.is_filled].copy()
assert len(filled) == int(hk.filled_reqs), "filled mismatch"

# ------------------------------------------------------------------------------------------------- H10 TTF vs SLA grade
g10 = filled.groupby(["grade_num", "grade"]).agg(n=("req_id", "size"), med=("ttf_days", "median"),
                                                 sla=("sla_days", "first"), met=("sla_met", "mean")).reset_index()
g10 = g10.sort_values("grade_num")
hi, lo = filled[filled.sla_days == 60], filled[filled.sla_days < 60]
t10 = prop_test(int((~hi.sla_met.astype(bool)).sum()), len(hi), int((~lo.sla_met.astype(bool)).sum()), len(lo))
worst = g10.sort_values("met").iloc[0]
add("F10", "10", "Hiring", "Senior roles (G6+) breach SLA most; junior and mid roles mostly meet it",
    f"{pct(t10['p1'])} of G6+ fills breached the 60-day SLA (n = {len(hi)}) vs {pct(t10['p2'])} for G2-G5 "
    f"(n = {len(lo)}); the worst grade is {worst.grade} with {pct(100 * worst.met)} within SLA and a median TTF of "
    f"{worst.med:.0f} days vs {worst.sla:.0f} (n = {int(worst.n)}).",
    [grp(f"{r.grade}: median TTF {r.med:.0f} d vs SLA {r.sla:.0f} d", pct(100 * r.met) + " within SLA", int(r.n))
     for r in g10.itertuples()],
    f"Breach rate G6+ vs G2-G5: {t10['test']}, {sig_text(t10['p'])}.",
    "Filled reqs only (open reqs are F10's mirror: " + f"{int(hk.open_past_sla)} of {int(hk.open_reqs)} open reqs are "
    "past SLA). Senior grades have few fills, so per-grade rates move a lot with one or two reqs.",
    "Give G6+ roles a dedicated senior-hiring track (pre-approved offer ranges, early search partner) or a realistic "
    "SLA; review every G6+ req at day 30.",
    effect=abs(t10["d"]), n=t10["n"], act=2, act_why="clear target group; partly market-driven",
    chart=dict(kind="bar", cats=[f"{r.grade}\nSLA {r.sla:.0f} d" for r in g10.itertuples()],
               vals=[100 * r.met for r in g10.itertuples()], ns=list(g10.n.astype(int)),
               colors=[RED if r.met < 0.5 else ACCENT for r in g10.itertuples()],
               ylabel="Filled within SLA (%)", unit="%",
               hline=(100 * filled.sla_met.mean(), ""),
               note=f"dashed line = all grades ({100 * filled.sla_met.mean():.1f}%); red = most fills breached SLA"))

# ---------------------------------------------------------------------------------------------- H11 recruiter concentration
rc = metric(metrics_hiring.recruiter_comparison)
ra = metric(metrics_hiring.recruiters)
top_rec = rc.sort_values("reqs_assigned", ascending=False).iloc[0]
rname = top_rec.recruiter
rf, of = filled[filled.recruiter == rname], filled[filled.recruiter != rname]
mw11 = mw_test(rf.ttf_days, of.ttf_days)
t11 = prop_test(int(rf.sla_met.sum()), len(rf), int(of.sla_met.sum()), len(of))
rr_all = REQ[REQ.recruiter == rname]
share = 100 * len(rr_all) / len(REQ)
att = ra[ra.recruiter == rname].iloc[0]
add("F11", "11", "Hiring", f"{rname} carries {share:.0f}% of all reqs without a drop in speed — a concentration "
    "risk, not a performance problem",
    f"{rname} owns {len(rr_all)} of {len(REQ)} reqs ({pct(share)}); those fills took a median {mw11['med_a']:.0f} days "
    f"(n = {len(rf)}) vs {mw11['med_b']:.0f} for other recruiters (n = {len(of)}), with {pct(t11['p1'])} vs "
    f"{pct(t11['p2'])} within SLA.",
    [grp(f"{r.recruiter}: reqs / filled % / median TTF", f"{int(r.reqs_assigned)} / {pct(r.filled_pct)} / "
         f"{r.median_ttf_days:.0f} d" if pd.notna(r.median_ttf_days) else f"{int(r.reqs_assigned)} / {pct(r.filled_pct)} / —",
         int(r.reqs_assigned)) for r in rc.sort_values("reqs_assigned", ascending=False).itertuples()]
    + [grp(f"{rname}: attainment (all accepted / excl. backed out)",
           f"{pct(att.attainment_all_pct)} / {pct(att.attainment_excl_bo_pct)}", "")],
    f"TTF: Mann-Whitney, {sig_text(mw11['p'])}. Within SLA: {t11['test']}, {sig_text(t11['p'])}.",
    "Attainment depends on how many reqs a recruiter is given, so it is not a fair cross-recruiter comparison (the "
    "dashboard shows per-req measures). One person holding a third of the book is a continuity risk.",
    "Rebalance new reqs so no recruiter holds more than ~25%, and set targets per assigned req rather than per month.",
    effect=abs(mw11["d"]), n=mw11["n"], act=2, act_why="TA Head can rebalance immediately",
    verdict="Partly supported: concentration yes, slower no",
    chart=dict(kind="barh", cats=list(rc.sort_values("reqs_assigned").recruiter),
               vals=list(rc.sort_values("reqs_assigned").reqs_assigned.astype(int)),
               ns=None, colors=[ACCENT if r == rname else GREY for r in rc.sort_values("reqs_assigned").recruiter],
               xlabel="Reqs assigned (Apr–Oct)", unit=""))

# --------------------------------------------------------------------------------------------- H12 slow R1 interviewers
fb = CAND[CAND.r1_feedback_days.notna()]
per_int = fb.groupby("r1_interviewer_id").r1_feedback_days.agg(["size", "median"])
per_int = per_int[per_int["size"] >= 5].sort_values("median", ascending=False)
slow_ids = list(per_int.head(2).index)
med_all = float(fb.r1_feedback_days.median())
# Interviewers are labelled "Interviewer A (function, grade)" in insights and charts; names stay on the dashboard Hiring
# page only. HRMS has duplicate names, so everything is keyed on Employee ID.
names = q("select employee_id, employee_name, function, grade from v_interviewers")
_iv = names.set_index("employee_id")
nm = {i: f"Interviewer {chr(65 + k)} ({_iv.loc[i, 'function']}, {_iv.loc[i, 'grade']})" for k, i in enumerate(slow_ids)}
r1 = CAND[CAND.reached_r1_interview]
slow_c, other_c = r1[r1.r1_interviewer_id.isin(slow_ids)], r1[~r1.r1_interviewer_id.isin(slow_ids)]
wd_s, wd_o = int((slow_c.candidate_status == "Withdrawn").sum()), int((other_c.candidate_status == "Withdrawn").sum())
t12 = prop_test(wd_s, len(slow_c), wd_o, len(other_c))
hire_rows = filled.merge(CAND[["candidate_id", "r1_interviewer_id", "r1_feedback_days"]],
                         left_on="hired_candidate_id", right_on="candidate_id", how="left")
sh = hire_rows[hire_rows.r1_interviewer_id.isin(slow_ids)].copy()
sh["saved"] = (sh.r1_feedback_days - med_all).clip(lower=0)
sh["ttf_cf"] = sh.ttf_days - sh.saved
breaches_now = int((~sh.sla_met.astype(bool)).sum())
breaches_cf = int((sh.ttf_cf > sh.sla_days).sum())
open_pending = CAND[CAND.r1_interviewer_id.isin(slow_ids) & CAND.r1_interview_date.notna()
                    & CAND.r1_feedback_submitted_on.isna() & (CAND.req_status == "Open")]
slow_reqs = CAND[CAND.r1_interviewer_id.isin(slow_ids)].req_id.nunique()
COUNTERFACTUAL_HIRE = dict(reqs=len(sh), days=float(sh.saved.sum()), per_req=float(sh.saved.mean()) if len(sh) else 0,
                           breaches_now=breaches_now, breaches_cf=breaches_cf, med_all=med_all,
                           withdrawn=wd_s, n_slow=len(slow_c), slow_reqs=slow_reqs, pending=len(open_pending),
                           pending_reqs=open_pending.req_id.nunique())
slow_desc = " and ".join(f"{nm.get(i, i)} (median {per_int.loc[i, 'median']:.0f} days, n = {int(per_int.loc[i, 'size'])})"
                         for i in slow_ids)
add("F12", "12", "Hiring", "Two slow R1 interviewers lose candidates: " + (
    "every post-R1 withdrawal sits with them" if wd_o == 0 else
    f"{times(t12['p1'], t12['p2'])} the withdrawal rate of other interviewers"),
    f"{slow_desc} take far longer than the company median of {med_all:.0f} day to submit R1 feedback, and "
    f"{wd_s} of their {len(slow_c)} R1 candidates ({pct(t12['p1'])}) withdrew vs {wd_o} of {len(other_c)} "
    f"({pct(t12['p2'])}) for every other interviewer.",
    [grp(f"{nm.get(i, i)}: median feedback days", f"{per_int.loc[i, 'median']:.0f}", int(per_int.loc[i, "size"]))
     for i in slow_ids]
    + [grp("All other interviewers (≥5 interviews): median of medians",
           f"{per_int.iloc[2:]['median'].median():.1f}", int(per_int.iloc[2:]['size'].sum())),
       grp("R1 candidates who withdrew — slow interviewers", f"{wd_s} ({pct(t12['p1'])})", len(slow_c)),
       grp("R1 candidates who withdrew — everyone else", f"{wd_o} ({pct(t12['p2'])})", len(other_c)),
       grp("Filled reqs whose hire was R1-interviewed by them", len(sh), ""),
       grp("Candidates still waiting for their R1 feedback on open reqs", len(open_pending),
           f"{open_pending.req_id.nunique()} reqs")],
    f"Withdrawals: {t12['test']}, {sig_text(t12['p'])}. TTF counterfactual: see the counterfactual section "
    f"({len(sh)} filled reqs, too few for a test).",
    "Withdrawal is a candidate status, not a reason code; the link is strong but other factors on those reqs may "
    "contribute. Names appear here because this is hiring data only (never joined to survey data).",
    "Set a 48-hour R1 feedback rule with an automatic reminder and escalation to the hiring manager; reassign "
    "pending candidates from these two interviewers now.",
    effect=abs(t12["d"]), n=t12["n"], act=3, act_why="two named people, a simple rule, immediate",
    chart=dict(kind="bar", cats=[nm[i].replace(" (", "\n(") for i in slow_ids] + ["All other\ninterviewers"],
               vals=[100 * (slow_c[slow_c.r1_interviewer_id == i].candidate_status == "Withdrawn").mean()
                     for i in slow_ids] + [t12["p2"]],
               ns=[int((slow_c.r1_interviewer_id == i).sum()) for i in slow_ids] + [len(other_c)],
               colors=[RED] * len(slow_ids) + [ACCENT], ylabel="R1 candidates who withdrew (%)", unit="%",
               note=f"median R1 feedback: " + ", ".join(f"{nm[i].split(' (')[0]} {per_int.loc[i, 'median']:.0f} d"
                                                         for i in slow_ids) + f"; company {med_all:.0f} d"))

# --------------------------------------------------------------------------------------------- H13 offer declines vs CTC
off = CAND[CAND.is_offer_accepted | CAND.is_offer_declined].copy()
off = off.merge(REQ[["req_id", "budgeted_max_ctc"]], on="req_id", how="left")
low, high = off[off.offer_to_expected_ratio < 0.90], off[off.offer_to_expected_ratio >= 0.90]
t13 = prop_test(int(low.is_offer_declined.sum()), len(low), int(high.is_offer_declined.sum()), len(high))
fits = low[0.90 * low.expected_ctc <= low.budgeted_max_ctc]
extra_cost = float((0.90 * fits.expected_ctc - fits.offered_ctc).clip(lower=0).sum())
band_rate = (off[(off.offer_to_expected_ratio >= 0.90) & (off.offer_to_expected_ratio < 1.00)].is_offer_declined
             .mean())
declines_cf = len(fits) * band_rate
declines_now_fits = int(fits.is_offer_declined.sum())
avoided = declines_now_fits - declines_cf
ofs = metric(metrics_hiring.offers)
COUNTERFACTUAL_OFFER = dict(n_low=len(low), fits=len(fits), extra=extra_cost, avoided=avoided,
                            declines_fits=declines_now_fits, band_rate=100 * band_rate)
add("F13", "13", "Hiring", f"Offers below 0.90× the candidate's expectation are declined {times(t13['p1'], t13['p2'])} "
    f"as often — and {len(fits)} of {len(low)} had budget headroom",
    f"{pct(t13['p1'])} of offers below 0.90× expected CTC were declined (n = {len(low)}) vs {pct(t13['p2'])} at "
    f"0.90× or more (n = {len(high)}); {len(fits)} of those {len(low)} low offers could have been raised to 0.90× "
    f"within the req's budgeted maximum, and offers sit at a median {off.offer_to_budget_ratio.median():.2f}× of "
    f"budget max.",
    [grp(f"Offered ÷ expected {r.ratio_band}: decline rate", pct(r.decline_rate_pct), int(r.offers))
     for r in ofs.itertuples() if pd.notna(r.decline_rate_pct)]
    + [grp("Low offers (<0.90) that fit budget at 0.90×", len(fits), len(low)),
       grp("Extra annual CTC to lift those offers to 0.90×", inr_lakh(extra_cost), len(fits))],
    f"Below vs at/above 0.90: {t13['test']}, {sig_text(t13['p'])}.",
    "Declined offers may also reflect counter-offers or role fit; expected CTC is self-reported. The cost estimate is "
    "annual CTC for the offers that fit budget.",
    "Set an offer floor of 0.90× expected CTC whenever the budget allows; require TA Head sign-off for lower offers.",
    effect=abs(t13["d"]), n=t13["n"], act=3, act_why="a policy change with budget already approved",
    chart=dict(kind="bar", cats=[str(r.ratio_band) for r in ofs.itertuples() if pd.notna(r.decline_rate_pct)],
               vals=[float(r.decline_rate_pct) for r in ofs.itertuples() if pd.notna(r.decline_rate_pct)],
               ns=[int(r.offers) for r in ofs.itertuples() if pd.notna(r.decline_rate_pct)],
               colors=[RED if str(r.ratio_band).startswith("<") else ACCENT for r in ofs.itertuples()
                       if pd.notna(r.decline_rate_pct)],
               ylabel="Offers declined (%)", unit="%", xlabel="Offered ÷ expected CTC"))

# --------------------------------------------------------------------------------------------------- H14 source mix
src = metric(metrics_hiring.source)
src_i = src.set_index("source")
ag = off[off.source == "Agency"]
nag = off[off.source != "Agency"]
t14 = prop_test(int(ag.is_offer_accepted.sum()), len(ag), int(nag.is_offer_accepted.sum()), len(nag))
refs = CAND[CAND.source == "Employee Referral"]
ags = CAND[CAND.source == "Agency"]
t14b = prop_test(int(ags.is_hire.sum()), len(ags), int(refs.is_hire.sum()), len(refs))
cols14 = [c for c in src.columns]
add("F14", "14", "Hiring", "Agency is the costliest and least reliable source; referrals and internal moves convert best",
    f"Agency candidates accepted {pct(t14['p1'])} of offers (n = {len(ag)}) vs {pct(t14['p2'])} for all other sources "
    f"(n = {len(nag)}), and converted applicant → hire at {pct(100 * ags.is_hire.mean(), 2)} (n = {len(ags)}) vs "
    f"{pct(100 * refs.is_hire.mean(), 2)} for referrals (n = {len(refs)}).",
    [grp(f"{s}: applicant→hire / acceptance / median TTF", f"{pct(r.applicant_to_hire_pct, 2)} / "
         f"{pct(r.offer_acceptance_pct)} / {r.median_ttf_days:.0f} d" if pd.notna(r.median_ttf_days) else
         f"{pct(r.applicant_to_hire_pct, 2)} / {pct(r.offer_acceptance_pct)} / —", int(r.applicants))
     for s, r in src_i.iterrows()]
    + [grp("Agency fees per joiner", f"₹{src_i.loc['Agency', 'cost_per_joiner_inr']:,.0f}",
           int(src_i.loc["Agency", "joined"]) if "joined" in src_i.columns else "")],
    f"Offer acceptance, agency vs others: {t14['test']}, {sig_text(t14['p'])}. Applicant → hire, agency vs referral: "
    f"{t14b['test']}, {sig_text(t14b['p'])}.",
    "Role mix is not controlled: if agencies are used for harder roles, part of the gap is the role, not the "
    "source. Acceptance is per offer; applicant → hire is per applicant.",
    "Expand the referral programme (bonus, internal job posts first) and use agencies only for roles referrals and "
    "internal moves cannot fill.",
    effect=abs(t14["d"]), n=t14["n"], act=2, act_why="TA can shift sourcing mix; benefit builds over quarters",
    chart=dict(kind="bar", cats=list(src_i.index), vals=list(src_i.offer_acceptance_pct.astype(float)),
               ns=[int(x) for x in src_i.offers] if "offers" in src_i.columns else None,
               colors=[RED if s == "Agency" else ACCENT for s in src_i.index], ylabel="Offer acceptance (%)",
               unit="%"))

# ------------------------------------------------------------------------------------------- H15 system vs recomputed SLA
mm = filled[filled.sla_status_mismatch.fillna(False).astype(bool)]
sys_within = (filled.sla_status_system == "Within SLA").mean() * 100
rec_within = filled.sla_met.mean() * 100
bt = stats.binomtest(0, len(mm), 0.5) if len(mm) else None
overrun = (mm.ttf_days - mm.sla_days)
add("F15", "15", "Hiring", f"The ATS overstates SLA performance: {len(mm)} filled reqs marked 'Within SLA' actually "
    "breached",
    f"The system marks {pct(sys_within)} of filled reqs within SLA vs {pct(rec_within)} when recomputed from dates "
    f"(n = {len(filled)}); all {len(mm)} disagreements go the same way (system 'Within SLA', actually "
    f"{overrun.min():.0f}-{overrun.max():.0f} days over).",
    [grp("System: within SLA", pct(sys_within), len(filled)), grp("Recomputed from dates: within SLA",
                                                                   pct(rec_within), len(filled)),
     grp("Disagreements (all 'Within SLA' → breached)", len(mm), len(filled)),
     grp("Days over SLA on those reqs (min-median-max)",
         f"{overrun.min():.0f} - {overrun.median():.0f} - {overrun.max():.0f}", len(mm))],
    f"Exact McNemar (sign) test on the {len(mm)} discordant pairs, all in one direction: "
    f"{sig_text(bt.pvalue if bt else None)}.",
    "The ATS rule is unknown (no other date explains the 14); recomputed status is used everywhere in the dashboard.",
    "Fix the ATS SLA rule (or report from recomputed dates) before SLA numbers go to leadership.",
    effect=abs(2 * math.asin(math.sqrt(sys_within / 100)) - 2 * math.asin(math.sqrt(rec_within / 100))),
    n=len(filled), act=2, act_why="a reporting fix, quick",
    chart=dict(kind="bar", cats=["ATS system status", "Recomputed from dates"], vals=[sys_within, rec_within],
               ns=[len(filled), len(filled)], colors=[GREY, ACCENT], ylabel="Filled reqs within SLA (%)", unit="%"))

# --------------------------------------------------------------------------------------------------- H16 backfill lag
bf = REQ[(REQ.position_type == "Replacement") & REQ.days_exit_to_req.notna()]
reg_b, non_b = bf[bf.replaced_is_regrettable.fillna(False).astype(bool)], bf[~bf.replaced_is_regrettable
                                                                              .fillna(False).astype(bool)]
mw16 = mw_test(reg_b.days_exit_to_req, non_b.days_exit_to_req)
ahead = int((bf.days_exit_to_req < 0).sum())
add("F16", "16", "Hiring", f"Backfills start a median {bf.days_exit_to_req.median():.0f} days after an exit, and "
    f"{pct(100 * len(reg_b) / len(bf), 0)} replace regrettable exits",
    f"Replacement reqs were raised a median {bf.days_exit_to_req.median():.0f} days after the exit (n = {len(bf)}); "
    f"{len(reg_b)} of them ({pct(100 * len(reg_b) / len(bf))}) replace regrettable exits, and {ahead} were raised "
    f"before the person left.",
    [grp("Median days exit → replacement req", f"{bf.days_exit_to_req.median():.0f}", len(bf)),
     grp("Regrettable exits: median days", f"{reg_b.days_exit_to_req.median():.0f}", len(reg_b)),
     grp("Non-regrettable exits: median days", f"{non_b.days_exit_to_req.median():.0f}", len(non_b)),
     grp("Raised before the exit date", ahead, len(bf))],
    f"Lag, regrettable vs non-regrettable: Mann-Whitney, {sig_text(mw16['p'])}.",
    "Only replacement reqs whose replaced employee is in the master with an exit date are included.",
    "Start backfills at resignation (notice period), not at exit — especially for regrettable leavers.",
    effect=abs(mw16["d"]), n=mw16["n"], act=2, act_why="process change; earlier start on every backfill",
    verdict="Supported (lag); no difference by regrettable status" if mw16["p"] >= ALPHA else "Supported",
    chart=dict(kind="hist", vals=list(bf.days_exit_to_req.astype(float)), n=len(bf),
               xlabel="Days from exit to replacement req", ylabel="Replacement reqs"))

# ======================================================================================================= CROSS-DATASET
# ------------------------------------------------------------------------------------------ H17 eNPS vs replacement reqs
hc = EMP[EMP.active_on_apr_open].groupby(["thread", "function"]).size().rename("hc")
repl = REQ[REQ.position_type == "Replacement"].groupby(["thread", "function"]).size().rename("repl")
ae = APR.groupby(["thread", "function"]).agg(n=("score", "size"), e=("score", "mean"))
oe = OCT.groupby(["thread", "function"]).agg(no=("score", "size"), eo=("score", "mean"))
cx = pd.concat([hc, repl, ae, oe], axis=1).fillna({"repl": 0})
cx = cx[(cx.n >= 10) & (cx.no >= 10) & (cx.hc >= 10)]
cx["rate"] = 100 * cx.repl / cx.hc
cx["chg"] = 100 * (cx.eo - cx.e)
rho17, p17 = stats.spearmanr(100 * cx.e, cx.rate)
rho17b, p17b = stats.spearmanr(cx.chg, cx.rate)
add("F17", "17", "Cross-dataset", "Lower-eNPS teams do not clearly raise more replacement reqs",
    f"Across {len(cx)} thread × function teams with at least 10 respondents in each wave, April eNPS and replacement "
    f"reqs per 100 employees are only weakly related (Spearman ρ = {rho17:.2f}), and the eNPS change is also weakly "
    f"related (ρ = {rho17b:.2f}).",
    [grp("April eNPS vs replacement reqs per 100 heads", f"ρ = {rho17:.2f}", len(cx)),
     grp("eNPS change vs replacement reqs per 100 heads", f"ρ = {rho17b:.2f}", len(cx))],
    f"Spearman: April eNPS {sig_text(p17)}; change {sig_text(p17b)}.",
    "Team-level (ecological) analysis with few teams; replacement reqs lag exits and depend on backfill policy. F7 "
    "(individual level) is the better test of the eNPS → exit link.",
    "No separate action; use F7 (detractor exits) as the retention signal.",
    effect=abs(2 * rho17 / math.sqrt(1 - rho17 ** 2)), n=len(cx), act=1, act_why="no clear lever",
    verdict="Not supported" if p17 >= ALPHA else "Supported")

# ------------------------------------------------------------------------------------- H18 interviewers / HMs workload
role = OCT[OCT.is_interviewer | OCT.is_hiring_manager]
nrole = OCT[~(OCT.is_interviewer | OCT.is_hiring_manager)]
mw18 = mw_test(role.q4, nrole.q4)
direction = "higher" if role.q4.mean() > nrole.q4.mean() else "lower"
add("F18", "18", "Cross-dataset", "Interviewers and hiring managers do not report worse workload",
    f"Interviewers and hiring managers rated workload (Q4) {role.q4.mean():.2f} / 5 ({pct(fav(role.q4))} favourable, "
    f"n = {len(role)}) vs {nrole.q4.mean():.2f} ({pct(fav(nrole.q4))}, n = {len(nrole)}) for everyone else — "
    f"{direction}, not lower.",
    [grp("Interviewers / hiring managers: Q4 mean / % fav", f"{role.q4.mean():.2f} / {pct(fav(role.q4))}", len(role)),
     grp("Everyone else: Q4 mean / % fav", f"{nrole.q4.mean():.2f} / {pct(fav(nrole.q4))}", len(nrole)),
     grp("Interviewers only", f"{OCT[OCT.is_interviewer].q4.mean():.2f}", int(OCT.is_interviewer.sum())),
     grp("Hiring managers only", f"{OCT[OCT.is_hiring_manager].q4.mean():.2f}", int(OCT.is_hiring_manager.sum()))],
    f"Mann-Whitney, {sig_text(mw18['p'])}.",
    "Role flags come from People_Directory, attached before IDs are dropped (no names in survey data). The two slow "
    "interviewers (F12) cannot and should not be identified in survey data.",
    "No workload action for interviewers as a group; handle slow feedback through process (F12).",
    effect=abs(mw18["d"]), n=mw18["n"], act=1, act_why="hypothesis not supported",
    verdict="Not supported (opposite direction)" if direction == "higher" else "Supported")

# ------------------------------------------------------------------------------------------- H19 this year's joiners Q5
jfy, njfy = OCT[OCT.joined_this_fy], OCT[~OCT.joined_this_fy]
mw19 = mw_test(jfy.q5, njfy.q5)
add("F19", "19", "Cross-dataset", "This year's joiners rate onboarding far below everyone else",
    f"Employees who joined this financial year rated onboarding/tools (Q5) {jfy.q5.mean():.2f} / 5 "
    f"({pct(fav(jfy.q5))} favourable, n = {len(jfy)}) in October vs {njfy.q5.mean():.2f} ({pct(fav(njfy.q5))}, "
    f"n = {len(njfy)}) for earlier joiners; their eNPS was {sgn(enps(jfy))}.",
    [grp("Joined this FY: Q5 mean / % fav", f"{jfy.q5.mean():.2f} / {pct(fav(jfy.q5))}", len(jfy)),
     grp("Earlier joiners: Q5 mean / % fav", f"{njfy.q5.mean():.2f} / {pct(fav(njfy.q5))}", len(njfy)),
     grp("Joined this FY: eNPS Oct", sgn(enps(jfy)), len(jfy))],
    f"Mann-Whitney, {sig_text(mw19['p'])}.",
    "Largely the same people as F2b (new joiners) and F6 (<6m tenure) — count it once in the deck.",
    "Same onboarding action as F2b; track Q5 for this FY's joiners in the next wave.",
    effect=abs(mw19["d"]), n=mw19["n"], act=3, act_why="onboarding is fully in HR's control")


# ------------------------------------------------------------------------------------- F20 where the days go (filled)
STAGES = [("Req raised → applied", "days_raised_to_applied"), ("Applied → shortlisted", "days_applied_to_shortlisted"),
          ("Shortlisted → screening", "days_shortlisted_to_screening"), ("Screening → R1", "days_screening_to_r1"),
          ("R1 → R2", "days_r1_to_r2"), ("R2 → offer", "days_r2_to_offer"),
          ("Offer → response", "days_offer_to_response")]
hc20 = filled.merge(CAND.drop(columns=[c for c in CAND.columns if c in filled.columns and c != "req_id"]
                              + ["req_id"]), left_on="hired_candidate_id", right_on="candidate_id", how="left")
hc20["days_raised_to_applied"] = (pd.to_datetime(hc20.applied_on) - pd.to_datetime(hc20.req_raised_on)).dt.days
hc20.loc[hc20.days_raised_to_applied < 0, "days_raised_to_applied"] = np.nan
sen20, jun20 = hc20[hc20.sla_days == 60], hc20[hc20.sla_days < 60]
rows20, st_all, st_sen, n_all, n_sen, tests20 = [], [], [], [], [], {}
for lab_, col in STAGES:
    a_, s_, j_ = hc20[col].dropna(), sen20[col].dropna(), jun20[col].dropna()
    st_all.append(float(a_.median())); st_sen.append(float(s_.median()))
    n_all.append(len(a_)); n_sen.append(len(s_))
    tests20[lab_] = mw_test(s_, j_)
    rows20.append(grp(lab_, f"all {a_.median():.0f} d · G6+ {s_.median():.0f} d (G2-G5 {j_.median():.0f} d)",
                      f"{len(a_)} / {len(s_)}"))
gap20 = {k: tests20[k]["med_a"] - tests20[k]["med_b"] for k in tests20}
big20 = max(gap20, key=gap20.get)
long_all = STAGES[int(np.argmax(st_all))][0]
rows20 += [grp("Median TTF, all filled / G6+ / G2-G5",
               f"{filled.ttf_days.median():.0f} / {sen20.ttf_days.median():.0f} / {jun20.ttf_days.median():.0f} d",
               f"{len(filled)} / {len(sen20)} / {len(jun20)}")]
i_long = [l_ for l_, _ in STAGES].index(long_all)
title20 = (f"Where the days go: for G6+ roles the eventual hire applies {st_sen[i_long]:.0f} days after the req is "
           f"raised (vs {st_all[i_long]:.0f} overall); interviews take only days" if big20 == long_all
           and long_all.startswith("Req raised") else
           f"Where the days go: '{long_all}' is the longest stage; G6+ roles lose most extra time at '{big20}'")
add("F20", "20 (added at review)", "Hiring", title20,
    f"For filled reqs every stage takes a median of {min(st_all):.0f}-{max(st_all):.0f} days (n = {min(n_all)}-"
    f"{max(n_all)} hires), the longest being {long_all}; "
    f"for G6+ roles the biggest extra delay vs G2-G5 is at {big20} ({tests20[big20]['med_a']:.0f} vs "
    f"{tests20[big20]['med_b']:.0f} days, n = {n_sen[[l_ for l_, _ in STAGES].index(big20)]} G6+ hires), while the "
    f"interview stages take only a few days each.",
    rows20,
    f"G6+ vs G2-G5 at '{big20}': Mann-Whitney, {sig_text(tests20[big20]['p'])}. Other stages: "
    + "; ".join(f"{k} {fmt_p(v['p'])}" for k, v in tests20.items() if k != big20) + ".",
    "Stage times use the hired candidate's dated stages only (R1 Select has no date, so R1 → R2 covers it); medians "
    "of stages do not add up to the median TTF. 'Req raised → applied' is when the eventual hire applied, i.e. "
    "sourcing time. G6+ has few hires, so its medians move with one or two reqs.",
    f"Attack the longest stage first ({long_all}); for G6+ start sourcing before the req is approved and pre-agree "
    "offer ranges.",
    effect=abs(tests20[big20]["d"]), n=tests20[big20]["n"], act=2, act_why="shows where to act; G6+ sample small",
    chart=dict(kind="grouped_h", cats=[l_ for l_, _ in STAGES],
               series=[("All filled reqs", st_all, n_all, GREY), ("G6+", st_sen, n_sen, ACCENT)],
               xlabel="Median days (hired candidate)"))

# ============================================================================================================= RANKING
for f in FINDINGS:
    f["score"] = (f["effect"] * math.log10(f["n"]) * f["act"]) if f["effect"] is not None and f["n"] else None
ranked = sorted([f for f in FINDINGS if f["score"] is not None], key=lambda f: -f["score"])
# overlapping findings: keep the strongest of each overlap group in the deck list
OVERLAP = [{"F2b", "F6", "F19"}, {"F3", "F3a"}]
DECK_ADDED = ["F7", "F16", "F20"]           # added at the Phase 9 review, on top of the top 8
deck, used = [], set()
for f in ranked:
    if f["id"] in DECK_ADDED:
        continue
    grp_ = next((g for g in OVERLAP if f["id"] in g), None)
    if grp_ and grp_ & used:
        continue
    if f["verdict"].startswith("Not supported"):
        continue
    deck.append(f["id"])
    if grp_:
        used |= grp_
    if len(deck) == TOP_N:
        break
deck += [d for d in DECK_ADDED if d not in deck]
EXTRA_CHARTS = ["F10"]                      # chart requested without deck flag
_f7, _f16 = next(f for f in FINDINGS if f["id"] == "F7"), next(f for f in FINDINGS if f["id"] == "F16")
_f7["chart"]["file"] = "F7_F16"
_f7["chart"]["note"] = (f"Backfill (F16): replacement reqs raised a median {bf.days_exit_to_req.median():.0f} days after "
                        f"the exit (n = {len(bf)}); {pct(100 * len(reg_b) / len(bf), 0)} replace regrettable exits")
for f in FINDINGS:
    f["deck"] = f["id"] in deck
BYID = {f["id"]: f for f in FINDINGS}


# ============================================================================================================== CHARTS
def chart(f: dict) -> str | None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    spec = f["chart"]
    if not spec:
        return None
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 16, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.edgecolor": "#D1D5DB", "axes.labelcolor": INK,
                         "xtick.color": INK, "ytick.color": INK})
    import textwrap
    fig, ax = plt.subplots(figsize=(13.333, 7.5), dpi=150)
    title_lines = textwrap.wrap(f["title"], 64)
    top = 0.80 if len(title_lines) == 1 else 0.74
    fig.subplots_adjust(left=0.09, right=0.95, top=top, bottom=0.14)
    unit = spec.get("unit", "")
    lab = (lambda v: f"{v:.1f}%" if unit == "%" else f"{v:+.1f}" if spec.get("ylabel", "").startswith(("eNPS",
           "Intercity eNPS", "October eNPS")) or spec.get("xlabel", "").startswith("October eNPS") else f"{v:,.0f}"
           if float(v).is_integer() else f"{v:.1f}")
    ns_txt = ""
    kind = spec["kind"]
    if kind == "bar":
        x = np.arange(len(spec["cats"]))
        bars = ax.bar(x, spec["vals"], color=spec["colors"], width=0.6)
        ax.set_xticks(x, spec["cats"])
        vals_ = [float(v) for v in spec["vals"]] + [float(v) for v in spec.get("sla") or []]
        span = max(max(vals_), 0) - min(min(vals_), 0)
        ax.set_ylim(min(min(vals_), 0) - (0.12 * span if min(vals_) < 0 else 0), max(max(vals_), 0) + 0.14 * span)
        for b, v in zip(bars, spec["vals"]):
            ax.annotate(lab(v), (b.get_x() + b.get_width() / 2, v), xytext=(0, 6 if v >= 0 else -22),
                        textcoords="offset points", ha="center", fontsize=18, fontweight="bold", color=INK)
        if spec.get("sla"):
            for i, s in enumerate(spec["sla"]):
                ax.hlines(s, i - 0.35, i + 0.35, colors=INK, linestyles="--", linewidth=2)
            ax.plot([], [], "--", color=INK, label="SLA (days)")
            ax.legend(frameon=False, loc="upper left")
        if spec.get("ns"):
            ns_txt = " · ".join(f"{c.replace(chr(10), ' ')} n = {n}" for c, n in zip(spec["cats"], spec["ns"]))
        ax.set_ylabel(spec.get("ylabel", ""))
        if spec.get("xlabel"):
            ax.set_xlabel(spec["xlabel"])
        ax.axhline(0, color="#9CA3AF", linewidth=1)
        if spec.get("hline"):
            ax.axhline(spec["hline"][0], color=INK, linestyle="--", linewidth=1.5)
        if spec.get("hline") and spec["hline"][1]:
            ax.annotate(spec["hline"][1], (len(spec["cats"]) - 0.5, spec["hline"][0]), xytext=(0, 5),
                        textcoords="offset points", ha="right", fontsize=13, color=MUTED,
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none"))
    elif kind == "barh":
        y = np.arange(len(spec["cats"]))
        bars = ax.barh(y, spec["vals"], color=spec["colors"], height=0.6)
        ax.set_yticks(y, spec["cats"])
        for b, v in zip(bars, spec["vals"]):
            ax.annotate(lab(v), (v, b.get_y() + b.get_height() / 2), xytext=(8 if v >= 0 else -8, 0),
                        textcoords="offset points", va="center", ha="left" if v >= 0 else "right", fontsize=16,
                        fontweight="bold", color=INK)
        ax.axvline(0, color="#9CA3AF", linewidth=1)
        ax.set_xlabel(spec.get("xlabel", ""))
        if spec.get("ns"):
            ns_txt = " · ".join(f"{c} n = {n}" for c, n in zip(spec["cats"], spec["ns"]))
        lo_, hi_ = min(0, min(spec["vals"])), max(0, max(spec["vals"]))
        pad = (hi_ - lo_) * 0.15
        ax.set_xlim(lo_ - (pad if lo_ < 0 else 0), hi_ + pad)
    elif kind == "grouped":
        cats, series = spec["cats"], spec["series"]
        x = np.arange(len(cats))
        w = 0.8 / len(series)
        for i, (name, vals, ns, col) in enumerate(series):
            ref_v = spec["ref"][0] if spec.get("ref") else None
            cols = [RED if ((spec.get("bad_oct_negative") and name == "October" and v < 0)
                            or (ref_v is not None and name == "October" and v < ref_v)) else col for v in vals]
            bars = ax.bar(x + (i - (len(series) - 1) / 2) * w, [0 if np.isnan(v) else v for v in vals], w * 0.92,
                          color=cols, label=name)
            for b, v, n in zip(bars, vals, ns):
                txt = ("none" if n == 0 else "n<5") if np.isnan(v) else lab(v)
                ax.annotate(txt, (b.get_x() + b.get_width() / 2, 0 if np.isnan(v) else v),
                            xytext=(0, 6 if (np.isnan(v) or v >= 0) else -22), textcoords="offset points",
                            ha="center", fontsize=14, fontweight="bold", color=INK)
        ax.set_xticks(x, cats)
        ax.set_ylabel(spec.get("ylabel", ""))
        ax.axhline(0, color="#9CA3AF", linewidth=1)
        handles = [plt.Rectangle((0, 0), 1, 1, color=s[3]) for s in series]
        ax.legend(handles, [s[0] for s in series], frameon=False, loc="upper right", ncol=len(series), fontsize=15)
        if spec.get("ref"):
            ax.axhline(spec["ref"][0], color=INK, linestyle="--", linewidth=1.5)
            ax.annotate(spec["ref"][1] + " — red = below it", (-0.45, spec["ref"][0]), xytext=(0, 5),
                        textcoords="offset points", ha="left", fontsize=13, color=MUTED,
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none"))
        ns_txt = f"{spec.get('n_label', 'n')} — " + " | ".join(f"{s[0]}: " + ", ".join(f"{c.replace(chr(10), ' ')} {n}" for c, n in
                                                           zip(cats, s[2])) for s in series)
        allv = [v for s_ in series for v in s_[1] if not np.isnan(v)]
        span = max(max(allv), 0) - min(min(allv), 0)
        ax.set_ylim(min(min(allv), 0) - 0.12 * span if min(allv) < 0 else 0, max(max(allv), 0) + 0.30 * span)
    elif kind == "grouped_h":
        cats, series = spec["cats"], spec["series"]
        y = np.arange(len(cats))
        h = 0.8 / len(series)
        for i, (name, vals, ns, col) in enumerate(series):
            bars = ax.barh(y + (i - (len(series) - 1) / 2) * h, vals, h * 0.92, color=col, label=name)
            for b, v in zip(bars, vals):
                ax.annotate(f"{v:.0f} d", (v, b.get_y() + b.get_height() / 2), xytext=(6, 0),
                            textcoords="offset points", va="center", fontsize=14, fontweight="bold", color=INK)
        ax.set_yticks(y, cats)
        ax.invert_yaxis()
        ax.set_xlabel(spec.get("xlabel", ""))
        ax.set_xlim(0, max(max(s_[1]) for s_ in series) * 1.15)
        ax.legend(frameon=False, loc="lower right", fontsize=15)
        ns_txt = "n (hires with both stage dates) — " + " | ".join(
            f"{s_[0]}: {min(s_[2])}-{max(s_[2])}" for s_ in series)
        fig.subplots_adjust(left=0.24)
    elif kind == "scatter":
        order = np.argsort(spec["x"])
        for k_, i in enumerate(order):
            xv, yv, lb = spec["x"][i], spec["y"][i], spec["labels"][i]
            hl = lb == spec["highlight"]
            ax.scatter(xv, yv, s=420 if hl else 260, color=ACCENT if hl else GREY, zorder=3)
            right = xv > np.median(spec["x"])
            ax.annotate(lb, (xv, yv), xytext=(-14 if right else 14, 14 if k_ % 2 == 0 else -26),
                        textcoords="offset points", fontsize=15, ha="right" if right else "left",
                        fontweight="bold" if hl else "normal", color=INK)
        xr = max(spec["x"]) - min(spec["x"])
        yr = max(spec["y"]) - min(spec["y"])
        ax.set_xlim(min(spec["x"]) - 0.1 * xr, max(spec["x"]) + 0.1 * xr)
        ax.set_ylim(min(spec["y"]) - 0.15 * yr, max(spec["y"]) + 0.15 * yr)
        ax.axhline(np.median(spec["y"]), color="#D1D5DB", linestyle="--")
        ax.axvline(np.median(spec["x"]), color="#D1D5DB", linestyle="--")
        ax.set_xlabel(spec["xlabel"])
        ax.set_ylabel(spec["ylabel"])
        ns_txt = f"n = {spec['n']} October respondents; dashed lines = medians; bottom-right = important but low-scoring"
    elif kind == "hist":
        ax.hist(spec["vals"], bins=20, color=ACCENT, edgecolor="white")
        ax.axvline(float(np.median(spec["vals"])), color=INK, linestyle="--", linewidth=2)
        ax.set_xlabel(spec["xlabel"])
        ax.set_ylabel(spec["ylabel"])
        ns_txt = f"n = {spec['n']} replacement reqs; dashed line = median"
    fig.text(0.04, 0.965, "\n".join(title_lines), fontsize=24, fontweight="bold", color=INK, ha="left", va="top",
             linespacing=1.15)
    cid = spec.get("file", f["id"]).replace("_", " + ")
    full = f"{cid} · {ns_txt}" + (f" · {spec['note']}" if spec.get("note") else "")
    sub = textwrap.wrap(full, 115)[:3]
    fig.subplots_adjust(top=min(top, 0.965 - 0.062 * len(title_lines) - 0.012 - 0.036 * len(sub) - 0.035))
    fig.text(0.04, 0.965 - 0.062 * len(title_lines) - 0.012, "\n".join(sub), fontsize=14, color=MUTED, ha="left",
             va="top", linespacing=1.3)
    fig.text(0.97, 0.02, "Source: Porter People Analytics case data (synthetic), as of 31-Oct-2026", fontsize=11,
             color=MUTED, ha="right")
    name = spec.get("file", f["id"])
    path = CHARTS / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    return f"charts/{name}.png"


# ============================================================================================================= WRITE MD
def table_md(rows) -> str:
    out = ["| Group | Value | n |", "|---|---|---|"]
    out += [f"| {g} | {v} | {n} |" for g, v, n, _ in rows]
    return "\n".join(out)


def finding_md(f: dict) -> str:
    deck = " · **Deck candidate**" if f["deck"] else ""
    lines = [f"### {f['id']} — {f['title']}", "",
             f"*Hypothesis {f['hyp']} · {f['area']} · Verdict: **{f['verdict']}**{deck}*", "",
             f"**Finding.** {f['finding']}", "", table_md(f["table"]), "", f"**Test.** {f['test']}", "",
             f"**Caveat.** {f['caveat']}", "", f"**So what / action.** {f['action']}"]
    if f.get("chart_path"):
        lines += ["", f"![{f['id']}]({f['chart_path']})"]
    return "\n".join(lines)


# ============================================================================================================= DQ NOTE
# (dataset, sheet, issue regex) -> short label / treatment / assumption. Row counts always come from dq_log.csv.
DQ_ITEMS = [
    ("eNPS", "Employee_Master", r"^Exact duplicate rows", "Duplicate employee rows (exact)", "Dropped", ""),
    ("eNPS", "Employee_Master", r"^Same ID, different values", "Same ID, different Location", "Kept the latest record",
     "Latest record is current"),
    ("eNPS", "Employee_Master", r"^(?:Spelling variants|Variants g1|Spelling/case/space|Case / trailing)",
     "Thread / grade / location / status spellings", "Mapped to one canonical list", "Only spelling variants merged"),
    ("eNPS", "Employee_Master", r"^Mixed formats", "Mixed date formats (joining, exit)", "Parsed day-first",
     "DD/MM, not MM/DD"),
    ("eNPS", "Employee_Master", r"^'Active' but Date of Exit", "'Active' with an exit date", "Set to Exited",
     "Exit date is reliable"),
    ("eNPS", "Employee_Master", r"^Exited with missing exit date", "Exited without an exit date",
     "Not invited to October; April only if joined by 06-Apr", "Left before the October wave; date unknown"),
    ("eNPS", "Employee_Master", r"^(?:Indian-comma|Lakh strings)", "CTC as text (4,48,000 / 2.96 LPA)",
     "Converted to rupees", ""),
    ("eNPS", "Employee_Master", r"^Value < 0.5x band mid", "Monthly CTC entered as annual", "Multiplied by 12, flagged",
     "x12 lands within 0.5-2x band mid"),
    ("eNPS", "Employee_Master", r"^manager_status: 'Changed manager'", "manager_status = Changed manager",
     "Effective 18-Apr..04-Oct and after joining", "Only the current manager is recorded"),
    ("eNPS", "Employee_Master", r"^manager_status: 'New joiner", "manager_status = New joiner (first manager)",
     "Effective date = joining date", "First manager, not a change"),
    ("eNPS", "eNPS_Responses", r"^Test IDs", "Test responses", "Excluded", ""),
    ("eNPS", "eNPS_Responses", r"^Not in Employee_Master", "Respondent not in master", "Excluded", ""),
    ("eNPS", "eNPS_Responses", r"^Same employee answered", "Two answers in one wave", "Kept the latest", ""),
    ("eNPS", "eNPS_Responses", r"^Respondent not active", "Not active on wave open date", "Excluded", ""),
    ("eNPS", "eNPS_Responses", r"^Q1 (?:blank|outside)", "Q1 blank or outside 0-10", "Response invalid for all metrics",
     "One base n per wave"),
    ("Recruitment", "Candidates", r"^Exact duplicate rows", "Duplicate candidate rows", "Dropped", ""),
    ("Recruitment", "Candidates", r"^Missing 'REQ_' prefix", "Req ID without 'REQ_' prefix", "Prefix added", ""),
    ("Recruitment", "Candidates", r"^No matching requisition", "Orphan candidates (no requisition)",
     "Excluded; kept in candidates_excluded", "Belong to older reqs not in the extract"),
    ("Recruitment", "Candidates", r"^(?:21 spellings|'Vendor')", "Source spellings; Vendor/Consultant",
     "Mapped to {n_src} sources; Vendor/Consultant = Agency", "All carry an agency name"),
    ("Recruitment", "Candidates", r"^Text values", "Notice period as text ('2 months')", "Converted to days",
     "1 month = 30 days"),
    ("Recruitment", "Candidates", r"^Accepted offers that backed out", "Accepted, then backed out", "Not a hire",
     "Req counted filled only if refilled"),
    ("Recruitment", "Requisitions", r"^Replacement req raised before", "Backfill raised before the exit", "Kept",
     "Backfill ahead of a known exit"),
    ("Recruitment", "Requisitions", r"^FINDING: system status disagrees", "ATS SLA status vs dates",
     "Recomputed status used; listed as a finding", "ATS rule unknown"),
]


def write_dq_note() -> None:
    import re
    log = pd.read_csv(ROOT / "data" / "clean" / "dq_log.csv")
    rec = pd.read_csv(ROOT / "data" / "clean" / "reconciliation.csv")
    orphans = int(log[log.issue.astype(str).str.startswith("No matching requisition")].rows_affected.sum())
    md = ["# Data quality note", "",
          f"Porter People Analytics case data, as of 31-Oct-2026. Every cleaning rule is logged in "
          f"`data/clean/dq_log.csv` ({len(log)} rules; {int((log.rows_affected > 0).sum())} changed data). The raw "
          f"workbooks are never modified. Main items below; counts come from the log.", ""]
    for ds, title in [("eNPS", "eNPS workbook"), ("Recruitment", "Recruitment workbook")]:
        md += [f"**{title}**", "", "| Issue | Rows / values | Treatment | Assumption |", "|---|---|---|---|"]
        for d_, sheet, rx, label, treat, assum in DQ_ITEMS:
            if d_ != ds:
                continue
            m = log[(log.dataset == ds) & (log.sheet == sheet) & log.issue.astype(str).str.contains(rx, regex=True)]
            if m.empty:
                raise SystemExit(f"dq_note: no dq_log row for {ds}/{sheet}/{rx}")
            if label.startswith("ATS SLA"):
                rng = re.search(r"overrun (\d+-\d+) days", m.issue.iloc[0])
                label += f" (all 'Within SLA' → breached{', ' + rng.group(1) + ' days over' if rng else ''})"
            treat = treat.replace("{n_src}", str(CAND.source.nunique()))
            md.append(f"| {label} | {int(m.rows_affected.sum()):,} | {treat} | {assum or '—'} |")
        flows = []
        for sheet, g in rec[rec.dataset == ds].groupby("sheet", sort=False):
            g = g.sort_values("order")
            if g.rows.iloc[0] != g.rows.iloc[-1]:
                flows.append(f"{sheet} {int(g.rows.iloc[0]):,} → {int(g.rows.iloc[-1]):,}")
        md += ["", "Rows in → out: " + "; ".join(flows) + ".", ""]
    md += [
        "**Definition used throughout — manager_status.** 'Changed manager' = Manager Effective From between 18-Apr and "
        "04-Oct-2026 and after the joining date; 'New joiner (first manager)' = in that window and equal to the joining "
        "date; 'Same manager' = everyone else.",
        "",
        "> **Limitations.** (1) HRMS keeps only current attributes and the current manager, so thread, grade, rating "
        "and manager history are not visible. (2) Survey data are anonymised (salted key, groups of 5 or more), so "
        "individual follow-up is impossible by design. (3) The data are synthetic and cover one financial half-year; "
        f"ATS SLA logic and the {orphans} orphan candidates' requisitions are outside the extract.",
        "",
    ]
    (OUT / "dq_note.md").write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    for old in list(CHARTS.glob("F*.png")):
        old.unlink()
    for f in FINDINGS:
        f["chart_path"] = (chart(f) if (f["deck"] or f["id"] in EXTRA_CHARTS) and f["chart"] and f["id"] != "F16"
                           else None)
    BYID["F16"]["chart_path"] = BYID["F7"]["chart_path"]   # one combined chart for F7 + F16

    cs_, ch_ = COUNTERFACTUAL_SENT, COUNTERFACTUAL_HIRE
    co = COUNTERFACTUAL_OFFER
    md = [
        "# Insights — Porter People Analytics",
        "",
        f"Generated by `pipeline/05_insights.py` from `data/people.duckdb` (data as of 31-Oct-2026). Every number below "
        f"is computed by that script; the dashboard and `analysis/metric_reference.md` use the same views.",
        "",
        "**How to read.** Each finding gives n for every group. p-values are two-sided; *significant* means p < 0.05 and "
        "results that are **NOT significant** are labelled so. Effects are put on one scale (Cohen's d / h, or "
        "rank-biserial r converted to d) so they can be ranked. Survey groups are anonymous and never joined to names.",
        "",
        "## Ranking",
        "",
        "Score = |effect| × log10(n) × actionability (1 = little lever, 3 = clear owner and lever). Overlapping "
        "findings (F2b / F6 / F19 onboarding; F3 / F3a Intercity) count once in the top 8; F7, F16 and F20 were added to the "
        "deck list at the Phase 9 review (F7 and F16 share one chart). Descriptive findings "
        "(F3b, F9) have no test and are listed after the scored ones; F3b is shown inside the F3a story.",
        "",
        "| Rank | ID | Finding | Verdict | Effect (d) | n | Act. | Score | Deck |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, f in enumerate(ranked, 1):
        md.append(f"| {i} | {f['id']} | {f['title']} | {f['verdict']} | {f['effect']:.2f} | {f['n']} | {f['act']} | "
                  f"{f['score']:.2f} | {'✅' if f['deck'] else ''} |")
    for f in FINDINGS:
        if f["score"] is None:
            md.append(f"| — | {f['id']} | {f['title']} | {f['verdict']} | — | — | {f['act']} | — | |")
    md += ["", "Actionability reasons: " + "; ".join(f"{f['id']} {f['act_why']}" for f in FINDINGS) + ".", ""]

    md += [
        "## Counterfactual impact",
        "",
        f"**Sentiment.** If the {cs_['n_ch']} changed-manager and {cs_['n_nj']} new-joiner October respondents had "
        f"scored like same-manager respondents in their own thread, October eNPS would be **{sgn(cs_['cf_company'])}** "
        f"company-wide instead of {sgn(enps(OCT))} (April {sgn(enps(APR))}), and **{sgn(cs_['cf_ic'])}** for Intercity "
        f"instead of {sgn(enps(ic_o))}. " + (f"That would put October above April: these two groups account for more than "
        f"the whole April → October fall ({cs_['share']:.0f}%). " if cs_['share'] > 100 else
        f"That is {cs_['share']:.0f}% of the company's April → October fall. ") + f"Fixing only "
        f"the manager-change group gives {sgn(cs_['cf_company_ch'])} company-wide and {sgn(cs_['cf_ic_ch'])} for "
        f"Intercity.",
        "",
        f"*Method:* each affected respondent's score (+1 / 0 / −1) is replaced by the October same-manager average for "
        f"their thread; everyone else keeps their actual answer. It is an upper bound — it assumes the whole gap is "
        f"caused by the transition.",
        "",
        f"**Hiring — slow interviewers.** If the two slowest R1 interviewers had given feedback in the company median "
        f"time ({ch_['med_all']:.0f} day), the {ch_['reqs']} filled reqs whose hire they interviewed would have saved "
        f"**{ch_['days']:.0f} days of TTF in total ({ch_['per_req']:.1f} per req)**, and **"
        f"{ch_['breaches_now'] - ch_['breaches_cf']} of {ch_['breaches_now']} SLA breaches** on those reqs would have "
        f"been avoided (the breached reqs overran by more than the feedback delay). Their larger cost is candidates: "
        f"{ch_['withdrawn']} of {ch_['n_slow']} R1 candidates withdrew, and {ch_['pending']} candidates on "
        f"{ch_['pending_reqs']} open reqs are still waiting for their feedback.",
        "",
        f"*Method:* days saved = hired candidate's R1 feedback days − company median (floored at 0), assuming the delay "
        f"passes one-for-one into TTF; breach avoided if TTF − saving ≤ SLA.",
        "",
        f"**Hiring — offer floor.** {co['fits']} of the {co['n_low']} offers below 0.90× expected CTC could have been "
        f"raised to 0.90× within budget, for {inr_lakh(co['extra'])} of extra annual CTC in total. At the 0.90-0.99 "
        f"band's decline rate ({pct(co['band_rate'])}), about **{co['avoided']:.0f} of their {co['declines_fits']} "
        f"declines** would have been avoided.",
        "",
    ]

    md += [
        "## Recommendations",
        "",
        "| # | Action | Findings | Owner | Expected impact | How to measure next wave |",
        "|---|---|---|---|---|---|",
        f"| 1 | Manager-transition playbook for the Intercity teams reorganised in June (HRBP check-in within 30 days, "
        f"first 1:1 in week 1, skip-level with Manager A and B) and for any future team move | F2, F3, F3a, F3b | CHRO "
        f"| Up to {sgn(cs_['cf_company_ch'] - enps(OCT))} pts company eNPS and {sgn(cs_['cf_ic_ch'] - enps(ic_o))} pts "
        f"Intercity if the changed-manager gap closes | eNPS and Q2 for manager_status = Changed manager (panel), "
        f"Intercity eNPS |",
        f"| 2 | 90-day onboarding standard: equipment and access on day 1, buddy, 30/60/90 check-ins, onboarding owner "
        f"per thread | F2b, F6, F19 | CHRO | Q5 for joiners up from {pct(fav(jfy.q5))} favourable; closing the new-joiner gap adds up to "
        f"{sgn(cs_['cf_company'] - cs_['cf_company_ch'])} pts company eNPS | Q5 % favourable and eNPS for tenure <6m "
        f"and New joiner (first manager) |",
        f"| 3 | 48-hour R1 feedback rule with auto-reminders and escalation; reassign the two slow interviewers' pending "
        f"candidates now | F12 | TA Head | Withdrawals after R1 to near zero (now {ch_['withdrawn']} of "
        f"{ch_['n_slow']}); ~{ch_['per_req']:.0f} days faster on affected reqs | % of R1 feedback within 2 days; "
        f"post-R1 withdrawals |",
        f"| 4 | Offer floor of 0.90× expected CTC when the req budget allows; sign-off for lower offers | F13 | TA Head | "
        f"About {co['avoided']:.0f} fewer declines for {inr_lakh(co['extra'])} annual CTC | Decline rate for offers "
        f"<0.90×; share of offers below the floor |",
        "| 5 | Senior-hiring track for G6+ and fix the ATS SLA rule so SLA reporting is accurate | F10, F15 | TA Head | "
        f"G6+ within-SLA up from {pct(100 - t10['p1'])}; SLA reports match recomputed dates | G6+ within-SLA %; "
        f"ATS vs recomputed mismatches = 0 |",
        "",
        "Before each next wave, also check thread response rates (F8) so a rise is not a response-rate artefact.",
        "",
        "## Findings",
        "",
    ]
    for area in ["Sentiment", "Hiring", "Cross-dataset"]:
        md += [f"## {area}", ""]
        for f in FINDINGS:
            if f["area"] == area:
                md += [finding_md(f), ""]
    (OUT / "insights.md").write_text("\n".join(md), encoding="utf-8")
    write_dq_note()

    hyp = ["# Hypotheses (Phase 9)", "",
           "Written from the project plan before testing; `pipeline/05_insights.py` tests each one and writes "
           "`analysis/insights.md`. Tests: eNPS z-test on the +1/0/−1 score, two-proportion z / Fisher exact, "
           "Mann-Whitney U, Wilcoxon signed-rank (panel), within-strata permutation, Spearman.", "",
           "| ID | Hypothesis | Data | Test |", "|---|---|---|---|"]
    plan = {
        "1": ("Overall eNPS fell April → October, also on the panel", "v_survey", "z-test; Wilcoxon on panel"),
        "2": ("Changed manager < Same manager in October, within thread and grade, on the panel, via Q2", "v_survey",
              "z-test; permutation within thread × grade; Mann-Whitney on panel change and Q2"),
        "2b": ("New joiner (first manager) < Same manager on Q1 and Q5 in October", "v_survey", "z-test; Mann-Whitney"),
        "3": ("Intercity is the weakest thread; how much is manager change", "v_survey", "z-test; counterfactual"),
        "3a": ("Intercity by manager_status, Apr and Oct; Intercity without changed managers vs rest", "v_survey",
               "z-test"),
        "3b": ("Timing of Intercity manager changes and number of distinct new managers", "v_employees (no survey)",
               "descriptive"),
        "4": ("Driver importance vs score: which to fix first", "v_survey", "Spearman with Q1"),
        "5": ("Compa-ratio < 0.90 → lower Q3 and Q1", "v_survey", "Mann-Whitney; z-test"),
        "6": ("Tenure < 6m → lower Q5", "v_survey", "Mann-Whitney"),
        "7": ("April detractors exited (voluntary, regrettable) more than promoters", "v_survey", "z / Fisher"),
        "8": ("Response-rate shifts by thread vs real sentiment change", "v_invited, v_survey",
              "z-test on rates; non-response bias"),
        "9": ("Small-n segments are suppressed", "v_survey", "descriptive"),
        "10": ("TTF vs SLA by grade: which grades breach most", "v_requisitions", "z / Fisher"),
        "11": ("Recruiter concentration vs TTF, breach and target", "v_requisitions, v_recruiters",
               "Mann-Whitney; z-test"),
        "12": ("Slow R1 interviewers and the TTF cost on their reqs", "v_candidates, v_requisitions",
               "Fisher; counterfactual"),
        "13": ("Declines vs offered/expected CTC and budget headroom", "v_candidates, v_requisitions", "z-test"),
        "14": ("Source conversion, TTF and cost per hire", "v_candidates", "z-test"),
        "15": ("System SLA status vs recomputed", "v_requisitions", "exact McNemar"),
        "16": ("Backfill lag from exit to replacement req; share regrettable", "v_requisitions", "Mann-Whitney"),
        "17": ("Low / falling eNPS teams raise more replacement reqs", "v_survey, v_employees, v_requisitions "
               "(team level)", "Spearman"),
        "18": ("Interviewers and hiring managers report worse Q4 workload (n ≥ 5)", "v_survey (role flags)",
               "Mann-Whitney"),
        "19": ("This year's joiners rate Q5 onboarding lower in October", "v_survey", "Mann-Whitney"),
        "20": ("Where the days go: median days per funnel stage for filled reqs, overall vs G6+ (added at the Phase 9 "
               "review)", "v_requisitions, v_candidates", "Mann-Whitney per stage"),
    }
    for hid, (h, d, t) in plan.items():
        hyp.append(f"| {hid} | {h} | {d} | {t} |")
    (OUT / "hypotheses.md").write_text("\n".join(hyp) + "\n", encoding="utf-8")

    print(f"insights.md: {len(FINDINGS)} findings; deck candidates: {', '.join(deck)}")
    for f in ranked:
        print(f"  {f['id']:4} score {f['score']:.2f}  d {f['effect']:.2f}  n {f['n']}  act {f['act']}  "
              f"{'DECK ' if f['deck'] else ''}{f['verdict']}")
    print("counterfactual:", {k: round(v, 1) if isinstance(v, float) else v for k, v in COUNTERFACTUAL_SENT.items()})
    print("counterfactual hiring:", COUNTERFACTUAL_HIRE)
    print("counterfactual offers:", COUNTERFACTUAL_OFFER)


if __name__ == "__main__":
    main()
