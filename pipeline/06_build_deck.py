"""
06_build_deck.py
----------------
Builds docs/Porter_People_Insights.pptx (16:9, 12 slides) for the CHRO and TA Head with python-pptx, and
docs/deck_number_trace.md, which lists every number on every slide (text, tables, speaker notes) and the line of
docs/insights.md (or docs/data_quality.md for the data-quality slide) it comes from. The build stops if any number
cannot be traced.

Numbers come from pipeline/05_insights.py (the code that writes insights.md), formatted with the same helpers, so a
slide number and its insights.md line are the same string. Charts are the insight charts re-rendered without their
own title (charts/deck/), because each slide headline already states the finding.

Run after 05_insights.py:  python pipeline/06_build_deck.py
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "docs"
DECK = ANALYSIS / "Porter_People_Insights.pptx"
TRACE = ANALYSIS / "deck_number_trace.md"

spec = importlib.util.spec_from_file_location("insights05", ROOT / "pipeline" / "05_insights.py")
I = importlib.util.module_from_spec(spec)
spec.loader.exec_module(I)

# ── palette and type (one accent; red only for bad outcomes) ──────────────────
NAVY, INK, MUTED, ACCENT, RED = "0F172A", "111827", "6B7280", "2563EB", "DC2626"
TINT, TINT2, WHITE, LINE = "EFF4FF", "F3F4F6", "FFFFFF", "E5E7EB"
FONT = "Calibri"
W, H = 13.333, 7.5
TOTAL = 12


def rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h)


# ── number tracing ────────────────────────────────────────────────────────────
INS_LINES = (ANALYSIS / "insights.md").read_text(encoding="utf-8").splitlines()
DQ_LINES = (ANALYSIS / "data_quality.md").read_text(encoding="utf-8").splitlines()
IGNORE = [r"\b20\d\d-\d\d-\d\d\b", r"\bG\d+(?:\+|-G\d+)?", r"\bQ\d\b", r"\bF\d+[ab]?\b", r"\b\d{1,2}-[A-Z][a-z]{2}(?:-\d{4})?\b",
          r"\b(?:30/60/90|48-hour|90-day|1:1s?|16:9)\b", r"\bslides? \d+(?:[-–]\d+)?(?:, \d+)*\b", r"\b\d+ / 12\b",
          r"\b20\d\d\b", r"\bApr(?:il)?[-–]Oct(?:ober)?\b", r"\bInterviewer [AB]\b", r"\b0\.90×", r"\bp < 0\.001\b",
          r"\bn<5\b", r"\b5 respondents\b"]
NUM = re.compile(r"(?<![\w.])[+\-]?₹?\d+(?:,\d{3})*(?:\.\d+)?%?")
TRACE_ROWS: list[tuple] = []


def _section(fid: str) -> range:
    start = next(i for i, l in enumerate(INS_LINES) if l.startswith(f"### {fid} — "))
    end = next((i for i in range(start + 1, len(INS_LINES)) if INS_LINES[i].startswith("### ")), len(INS_LINES))
    return range(start, end)


def _named(title: str) -> range:
    start = next(i for i, l in enumerate(INS_LINES) if l.strip() == f"## {title}")
    end = next((i for i in range(start + 1, len(INS_LINES)) if INS_LINES[i].startswith("## ")), len(INS_LINES))
    return range(start, end)


def trace(slide_no: int, where: str, text: str, sources: list[str], dq: bool = False) -> None:
    clean = text
    for pat in IGNORE:
        clean = re.sub(pat, " ", clean)
    for tok in dict.fromkeys(NUM.findall(clean)):
        core = tok.lstrip("+")
        pat = re.compile(r"(?<![\d.,])" + re.escape(tok if tok.startswith(("+", "-")) else core) + r"(?![\d])")
        lines = DQ_LINES if dq else INS_LINES
        order = []
        if not dq:
            for s in sources:
                order += list(_named(s) if s in ("Counterfactual impact", "Recommendations", "Ranking") else _section(s))
        order += list(range(len(lines)))
        hit = next((i for i in order if pat.search(lines[i])), None)
        if hit is None:
            raise SystemExit(f"slide {slide_no}: number '{tok}' in {where} not found in "
                             f"{'data_quality.md' if dq else 'insights.md'}")
        TRACE_ROWS.append((slide_no, where, tok, "data_quality.md" if dq else "insights.md", hit + 1,
                           lines[hit].strip()[:140]))


# ── shape helpers ─────────────────────────────────────────────────────────────
def box(slide, x, y, w, h, fill=None, radius=0.06, name=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                                 Inches(x), Inches(y), Inches(w), Inches(h))
    if radius:
        shp.adjustments[0] = radius
    if fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(fill)
    else:
        shp.fill.background()
    shp.line.fill.background()
    shp.shadow.inherit = False
    if name:
        shp.name = name
    return shp


def text(slide, x, y, w, h, runs, size=14, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         space_after=4, name=None):
    """runs: str, or list of paragraphs; a paragraph is a str or a list of (text, {size, bold, color}) runs."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        for seg, opt in ([(para, {})] if isinstance(para, str) else para):
            r = p.add_run()
            r.text = seg
            r.font.name = FONT
            r.font.size = Pt(opt.get("size", size))
            r.font.bold = opt.get("bold", bold)
            r.font.italic = opt.get("italic", False)
            r.font.color.rgb = rgb(opt.get("color", color))
    return tb


def plain(runs) -> str:
    paras = runs if isinstance(runs, list) else [runs]
    return " ".join(p if isinstance(p, str) else "".join(s for s, _ in p) for p in paras)


def footer(slide, n):
    text(slide, 0.6, 7.02, 9.5, 0.3, "People Sight · Porter People Analytics · data as of 31-Oct-2026 (synthetic case data)",
         size=10, color=MUTED, name="Footer")
    text(slide, 11.6, 7.02, 1.13, 0.3, f"{n} / {TOTAL}", size=10, color=MUTED, align=PP_ALIGN.RIGHT, name="Slide number")


def notes(slide, n, body, sources, dq=False):
    slide.notes_slide.notes_text_frame.text = body
    trace(n, "speaker notes", body, sources, dq)


def headline(slide, n, title, sources):
    text(slide, 0.6, 0.42, 12.1, 1.2, title, size=26, bold=True, color=NAVY, anchor=MSO_ANCHOR.TOP, name="Headline")
    trace(n, "headline", title, sources)


def chart_slide(prs, n, fid, title, stats, sowhat, sources, note_text, chart_fid=None):
    """Headline, chart (left), stat cards + 'So what' (right), n caption under the chart."""
    s = prs.slides.add_slide(prs.slide_layouts[6])
    headline(s, n, title, sources)
    f = I.BYID[chart_fid or fid]
    path = I.CHARTS / "deck" / Path(I.chart(f, bare=True)).name
    pic = s.shapes.add_picture(str(path), Inches(0.6), Inches(1.78), width=Inches(8.15))
    pic.name = f"Chart {fid}"
    pic._element.nvPicPr.cNvPr.set("descr", f"{fid}: {f['title']}")
    cap = "n — " + f["chart_ns"] if not f["chart_ns"].startswith(("n ", "n=", "n —", "invited", "n (")) else f["chart_ns"]
    text(s, 0.6, 6.42, 8.15, 0.5, cap, size=10.5, color=MUTED, name="Chart n")
    trace(n, "chart caption", cap, sources)
    y = 1.78
    for big, label, bad in stats:
        card = box(s, 9.05, y, 3.68, 1.06, fill=TINT2, name="Stat card")
        text(s, 9.25, y + 0.08, 3.3, 0.45, big, size=24, bold=True, color=RED if bad else ACCENT, name="Stat value")
        text(s, 9.25, y + 0.55, 3.3, 0.48, label, size=11.5, color=INK, name="Stat label")
        trace(n, "stat card", big + " " + label, sources)
        y += 1.16
    so = box(s, 9.05, y + 0.02, 3.68, 6.9 - y - 0.02, fill=TINT, name="So what")
    text(s, 9.25, y + 0.14, 3.3, 6.9 - y - 0.25,
         [[("So what  ", {"bold": True, "color": ACCENT, "size": 13})], sowhat], size=13, color=INK, name="So what text")
    trace(n, "so what", sowhat, sources)
    footer(s, n)
    notes(s, n, note_text, sources)
    return s


# ── content (all values from 05_insights.py) ─────────────────────────────────
sgn, pct, fav, enps, fmt_p, inr = I.sgn, I.pct, I.fav, I.enps, I.fmt_p, I.inr_lakh
cs, chh, co = I.COUNTERFACTUAL_SENT, I.COUNTERFACTUAL_HIRE, I.COUNTERFACTUAL_OFFER
ic_nj = I.nj_o[I.nj_o.thread == "Intercity"]
src = I.src_i


def build() -> None:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    prs.core_properties.title = "People Sight — Porter People Analytics insights"
    prs.core_properties.author = "Lakshay Malik"
    prs.core_properties.subject = "Employee sentiment and hiring, April–October 2026"
    import datetime as _dt
    cp = prs.core_properties
    cp.last_modified_by, cp.comments, cp.category, cp.keywords = "Lakshay Malik", "", "People analytics", "People Sight"
    cp.created = cp.modified = _dt.datetime(2026, 11, 5)
    cp.revision = 1

    # 1 ─ title ─────────────────────────────────────────────────────────────
    s = prs.slides.add_slide(prs.slide_layouts[6])
    box(s, 0, 0, W, H, fill=NAVY, radius=0, name="Background")
    text(s, 0.8, 0.9, 11.5, 1.0, "People Sight", size=54, bold=True, color=WHITE, name="Title")
    text(s, 0.8, 1.95, 11.5, 0.6, "What the April and October 2026 data say about sentiment and hiring at Porter",
         size=20, color="CBD5E1", name="Subtitle")
    chro = (f"The eNPS fall is not company-wide. It sits in the Intercity teams reorganised in June and in new joiners; "
            f"if those groups scored like their same-manager colleagues, October eNPS would be {sgn(cs['cf_company'])} "
            f"instead of {sgn(enps(I.OCT))}.")
    ta = (f"Hiring loses candidates to slow R1 feedback ({chh['withdrawn']} of {chh['n_slow']} candidates of the two "
          f"slowest interviewers withdrew) and to low offers ({pct(I.t13['p1'])} of offers below 0.90× expectation "
          f"declined); senior roles lose time before anyone applies.")
    for i, (who, ans) in enumerate([("For the CHRO", chro), ("For the TA Head", ta)]):
        x = 0.8 + i * 6.0
        box(s, x, 3.15, 5.65, 2.45, fill="1E293B", name=f"Answer card {i + 1}")
        text(s, x + 0.3, 3.38, 5.05, 0.4, who, size=15, bold=True, color="93C5FD")
        text(s, x + 0.3, 3.85, 5.05, 1.65, ans, size=16, color=WHITE)
        trace(1, f"answer: {who}", ans, ["Counterfactual impact", "F12", "F13", "F3b", "F20"])
    text(s, 0.8, 6.45, 11.5, 0.4, "For the CHRO and TA Head · data as of 31-Oct-2026 (synthetic case data) · every "
         "number shows its base n in the slides that follow", size=12, color="94A3B8", name="Footer")
    notes(s, 1, "Two one-line answers. CHRO: the counterfactual replaces each changed-manager and new-joiner "
          "respondent's score with the October same-manager average in their own thread and recomputes eNPS (an upper "
          "bound). TA Head: withdrawals are candidate status 'Withdrawn' among R1-interviewed candidates; the decline "
          "rate is declined / (accepted + declined) for offers below 0.90 of the candidate's expected CTC.",
          ["Counterfactual impact"])

    # 2 ─ executive summary ─────────────────────────────────────────────────
    s = prs.slides.add_slide(prs.slide_layouts[6])
    headline(s, 2, "Two fixable groups explain the eNPS fall, and three process gaps cost hiring speed and candidates",
             ["F1"])
    banner = (f"Company eNPS {sgn(enps(I.APR))} → {sgn(enps(I.OCT))} (n = {len(I.APR)} / {len(I.OCT)}); the same "
              f"{len(I.pan)} people: {sgn(I.pan_e_apr)} → {sgn(I.pan_e_oct)}. Not significant company-wide "
              f"({fmt_p(I.t1['p'])}) — the fall sits in specific groups.")
    box(s, 0.6, 1.42, 12.13, 0.62, fill=TINT, name="Banner")
    text(s, 0.8, 1.5, 11.8, 0.5, banner, size=14, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
    trace(2, "banner", banner, ["F1"])
    cols = [
        ("Sentiment", TINT2, INK, ["F2", "F3b", "F6", "F7"], [
            f"Manager change: eNPS {sgn(enps(I.ch_o))} (n = {len(I.ch_o)}) vs {sgn(enps(I.sm_o))} with the same manager "
            f"(n = {len(I.sm_o)}); all {len(I.ice)} Intercity changes came in one June reorganisation.",
            f"Onboarding: {pct(fav(I.t6n.q5))} of under-6-month staff rate it favourably (n = {len(I.t6n)}) vs "
            f"{pct(fav(I.t6o.q5))} of everyone else (n = {len(I.t6o)}).",
            f"Detractors leave: {pct(I.t7['p1'])} of April detractors left voluntarily (n = {len(I.det)}) vs "
            f"{pct(I.t7['p2'])} of promoters (n = {len(I.pro)})."]),
        ("Hiring", TINT2, INK, ["F12", "F13", "F10", "F20"], [
            f"Slow R1 feedback: {chh['withdrawn']} of {chh['n_slow']} candidates of the two slowest interviewers withdrew "
            f"vs 0 of {len(I.other_c)} for everyone else.",
            f"Low offers: {pct(I.t13['p1'])} of offers below 0.90× expectation declined (n = {len(I.low)}) vs "
            f"{pct(I.t13['p2'])} (n = {len(I.high)}); {co['fits']} of {co['n_low']} had budget headroom.",
            f"Senior roles: {pct(I.t10['p1'])} of G6+ fills breached SLA (n = {len(I.hi)}); the eventual hire applies "
            f"{I.st_sen[I.i_long]:.0f} days after the req is raised vs {I.st_all[I.i_long]:.0f} overall."]),
        ("Top three asks", NAVY, WHITE, ["Recommendations", "Counterfactual impact"], [
            f"CHRO: manager-transition playbook for the reorganised Intercity teams (up to "
            f"{sgn(cs['cf_company_ch'] - enps(I.OCT))} pts company eNPS).",
            "CHRO: 90-day onboarding standard for every new joiner.",
            f"TA Head: 48-hour R1 feedback rule and a 0.90× offer floor where budget allows (about "
            f"{co['avoided']:.0f} fewer declines)."]),
    ]
    for i, (head, fill, col, srcs, items) in enumerate(cols):
        x = 0.6 + i * 4.11
        box(s, x, 2.3, 3.91, 4.5, fill=fill, name=f"{head} column")
        text(s, x + 0.25, 2.48, 3.45, 0.45, head, size=18, bold=True, color=ACCENT if fill != NAVY else "93C5FD")
        text(s, x + 0.25, 3.0, 3.45, 3.7, items, size=15, color=col, space_after=12)
        trace(2, f"column: {head}", " ".join(items), srcs)
    footer(s, 2)
    notes(s, 2, "Executive summary. eNPS = % promoters (9-10) minus % detractors (0-6) on Q1. The panel is the people who "
          "answered both waves (salted respondent key). Significance: z-test on the per-person +1/0/-1 score and Wilcoxon "
          "on the panel's Q1 change. Each line points to the slide with the evidence; asks are on slide 11.",
          ["F1"])

    # 3 ─ overall change (F1) ───────────────────────────────────────────────
    chart_slide(prs, 3, "F1", I.BYID["F1"]["title"],
                [(f"{sgn(enps(I.APR))} → {sgn(enps(I.OCT))}", f"Company eNPS, n = {len(I.APR)} / {len(I.OCT)}", True),
                 (f"{sgn(I.pan_e_apr)} → {sgn(I.pan_e_oct)}", f"Same {len(I.pan)} people (panel)", True),
                 (fmt_p(I.t1["p"]), "Company-wide change: not significant at 5%", False)],
                "Do not run a company-wide programme. The next slides show the fall sits in two groups that can be "
                "fixed directly.",
                ["F1"],
                "eNPS per wave from all valid responses (Q1 blank or outside 0-10 excluded). Panel = respondents in both "
                "waves, matched on a salted key; no IDs or names are stored with survey answers. The z-test treats the "
                "two waves as independent, which overlapping respondents make conservative; the Wilcoxon test on the "
                "panel is the cleaner check. Neither reaches p < 0.05.")

    # 4 ─ biggest driver: manager change (F2, F3a, F3b) ─────────────────────
    chart_slide(prs, 4, "F2", I.BYID["F2"]["title"],
                [(f"{sgn(enps(I.ch_o))}", f"Changed manager, October (n = {len(I.ch_o)}); "
                                          f"{sgn(enps(I.ch_a))} in April (n = {len(I.ch_a)})", True),
                 (f"{len(I.ice)} in June", f"Intercity manager changes, {I.top2} onto two managers", False),
                 (f"{sgn(enps(I.ic_same))}", f"Intercity, same manager (n = {len(I.ic_same)}) vs "
                                             f"{sgn(enps(I.rest_same))} elsewhere — no real gap", False)],
                f"Closing the changed-manager gap alone would lift October eNPS to {sgn(cs['cf_company_ch'])} company-wide "
                f"and {sgn(cs['cf_ic_ch'])} in Intercity.",
                ["F2", "F3b", "F3a", "Counterfactual impact"],
                "Changed manager = Manager Effective From between 18-Apr and 04-Oct-2026 and after the joining date. "
                "Within the same thread and grade the gap holds (permutation test, manager status shuffled within "
                "thread x grade 5,000 times, p < 0.001). The April baseline shows no gap before the change. Manager "
                "changes are counted from HRMS (no survey join); the two receiving managers are not named.",
                chart_fid="F2")

    # 5 ─ weakest segments: newcomers and onboarding (F6, F2b, F3, F5) ──────
    chart_slide(prs, 5, "F6", I.BYID["F6"]["title"],
                [(f"{sgn(enps(I.t6n))}", f"eNPS, tenure under 6 months (n = {len(I.t6n)})", True),
                 (f"{sgn(enps(I.nj_o))}", f"eNPS, new joiners on their first manager (n = {len(I.nj_o)})", True),
                 (f"{sgn(enps(I.ic_o))}", f"Intercity, weakest thread (n = {len(I.ic_o)}); below-band pay "
                                          f"{sgn(enps(I.below))} (n = {len(I.below)})", True)],
                f"The gap was already there in April, so it is the onboarding process, not one cohort. Closing the "
                f"new-joiner gap adds up to {sgn(cs['cf_company'] - cs['cf_company_ch'])} pts company eNPS.",
                ["F6", "F2b", "F3", "F5", "Recommendations"],
                "Q5 = onboarding / tools, favourable = 4 or 5 on the 1-5 scale. Tenure band is computed at each wave's open "
                "date, so the under-6-month groups are different people in April and October. New joiners overlap heavily "
                "with the under-6-month group; they are one signal, counted once.")

    # 6 ─ drivers 2x2 + comment themes (F4, F5) ─────────────────────────────
    chart_slide(prs, 6, "F4", I.BYID["F4"]["title"],
                [(f"ρ = {I.fix.rho:.2f}", f"{I.fix.driver}: link with recommending Porter (n = {int(I.fix.n)})", False),
                 (f"{pct(I.thm_p.loc[I.th1, 'Apr'])} → {pct(I.thm_p.loc[I.th1, 'Oct'])}",
                  f"Comments about {I.th1} (n = {int(I.thm_n['Apr'])} / {int(I.thm_n['Oct'])})", True),
                 (f"{pct(fav(I.below.q3))} vs {pct(fav(I.atab.q3))}",
                  f"Fair pay favourable: below band (n = {len(I.below)}) vs at or above (n = {len(I.atab)})", True)],
                f"Train managers on regular feedback and 1:1s first; comments about {I.th2.lower()} also rose from "
                f"{pct(I.thm_p.loc[I.th2, 'Apr'])} to {pct(I.thm_p.loc[I.th2, 'Oct'])}. Prioritise below-band staff in "
                "the next pay review.",
                ["F4", "F5"],
                "Importance = Spearman correlation of each driver (Q2-Q6) with Q1 in October; the chart plots it against "
                "the October mean, with medians as dashed lines. Correlation is a ranking aid, not proof of cause. Comment "
                "shares are each theme's share of themed comments per wave. Compa band uses the 2026-04-01 pay bands.")

    # 7 ─ exits and backfills (F7, F16) ─────────────────────────────────────
    chart_slide(prs, 7, "F7", I.BYID["F7"]["title"],
                [(f"{pct(I.t7['p1'])} vs {pct(I.t7['p2'])}", f"Left voluntarily: detractors (n = {len(I.det)}) vs "
                                                              f"promoters (n = {len(I.pro)})", True),
                 (f"{pct(I.t7r['p1'])} vs {pct(I.t7r['p2'])}", "Regrettable exits, same groups", True),
                 (f"{I.bf.days_exit_to_req.median():.0f} days", f"Median exit → replacement req (n = {len(I.bf)}); "
                  f"{pct(100 * len(I.reg_b) / len(I.bf), 0)} replace regrettable exits", False)],
                "Use eNPS as an early warning: stay interviews in teams with many detractors after each wave, and start "
                "backfills at resignation rather than at exit.",
                ["F7", "F16"],
                "Exit outcome by 31-Oct-2026 is attached to each April survey row before IDs are dropped, so the analysis "
                "stays anonymous. Voluntary and regrettable flags come from HRMS. Backfill lag = replacement req raised "
                "date minus the replaced employee's exit date, for replacement reqs whose employee has an exit date.",
                chart_fid="F7")

    # 8 ─ TTF vs SLA by grade and where the days go (F20, F10, F15) ─────────
    chart_slide(prs, 8, "F20", I.BYID["F20"]["title"],
                [(f"{pct(I.t10['p1'])} vs {pct(I.t10['p2'])}", f"Fills breaching SLA: G6+ (n = {len(I.hi)}) vs G2-G5 "
                                                                f"(n = {len(I.lo)})", True),
                 (f"{I.sen20.ttf_days.median():.0f} vs {I.jun20.ttf_days.median():.0f} days",
                  f"Median time to fill, G6+ vs G2-G5 (n = {len(I.sen20)} / {len(I.jun20)})", True),
                 (f"{len(I.mm)} reqs", "Marked 'Within SLA' in the ATS but breached by dates", True)],
                "Interviews take days, not weeks. For G6+ start the search before the req is approved and pre-agree "
                "offer ranges; fix the ATS SLA rule so reports match the dates.",
                ["F20", "F10", "F15"],
                "Time to fill = hired candidate's offer response date minus req raised date. SLA: 30 days up to G2, 45 for "
                "G3-G5, 60 for G6+. Stage times use the hired candidate's dated stages; 'req raised to applied' is when "
                "the eventual hire applied. Medians of stages do not add up to the median time to fill.")

    # 9 ─ recruiter load and slow interviewers (F12, F11) ───────────────────
    chart_slide(prs, 9, "F12", I.BYID["F12"]["title"],
                [(f"{I.per_int.loc[I.slow_ids[0], 'median']:.0f} and {I.per_int.loc[I.slow_ids[1], 'median']:.0f} days",
                  f"Median R1 feedback, Interviewer A and B (n = {int(I.per_int.loc[I.slow_ids[0], 'size'])} and "
                  f"{int(I.per_int.loc[I.slow_ids[1], 'size'])}); company {I.med_all:.0f} day", True),
                 (f"{chh['pending']} waiting", f"Candidates on {chh['pending_reqs']} open reqs still waiting for their "
                                               "feedback", True),
                 (f"{I.share:.0f}% of reqs", f"Held by one recruiter ({len(I.rr_all)} of {len(I.REQ)}); time to fill "
                  f"{I.mw11['med_a']:.0f} vs {I.mw11['med_b']:.0f} days — no slowdown", False)],
                f"Set a 48-hour R1 feedback rule and reassign the waiting candidates now. Faster feedback would have "
                f"saved {chh['days']:.0f} days on {chh['reqs']} filled reqs; keeping candidates matters more.",
                ["F12", "F11", "Counterfactual impact"],
                "R1 feedback turnaround = feedback submitted date minus R1 interview date, per interviewer with at least 5 "
                "interviews. Withdrawals = candidate status 'Withdrawn' among R1-interviewed candidates (Fisher exact test, "
                "p < 0.001). Interviewers are labelled by function and grade; names stay on the dashboard Hiring page. "
                "Recruiter load is a continuity risk, not a performance issue.")

    # 10 ─ offer declines and source cost (F13, F14) ────────────────────────
    chart_slide(prs, 10, "F13", I.BYID["F13"]["title"],
                [(f"{co['fits']} of {co['n_low']}", f"Low offers that fit the budget at 0.90×; {inr(co['extra'])} extra "
                                                    "annual CTC in total", False),
                 (f"{pct(I.t14['p1'])} vs {pct(I.t14['p2'])}", f"Offer acceptance: agency (n = {len(I.ag)}) vs all other "
                                                                f"sources (n = {len(I.nag)})", True),
                 (f"₹{src.loc['Agency', 'cost_per_joiner_inr']:,.0f}", f"Agency fee per joiner; referrals convert "
                  f"{pct(100 * I.refs.is_hire.mean(), 2)} of applicants vs {pct(100 * I.ags.is_hire.mean(), 2)}", True)],
                f"Set an offer floor of 0.90× expected CTC when the budget allows — about {co['avoided']:.0f} fewer "
                "declines — and grow referrals and internal moves before using agencies.",
                ["F13", "F14", "Counterfactual impact"],
                "Decline rate = declined / (accepted + declined) by offered / expected CTC band. Headroom = 0.90 x expected "
                "CTC is within the req's budgeted maximum. Declines avoided assume the 0.90-0.99 band's decline rate. "
                "Agency fee = 8.33% of offered CTC for agency joiners. Role mix by source is not controlled.")

    # 11 ─ recommendations ──────────────────────────────────────────────────
    s = prs.slides.add_slide(prs.slide_layouts[6])
    headline(s, 11, "Five actions, in priority order, each tied to its evidence and measurable in the next wave",
             ["Recommendations"])
    rows = [
        ("Action", "Owner", "Expected impact", "Measure next wave", "Evidence"),
        ("Manager-transition playbook for the June Intercity reorganisation and any future team move", "CHRO",
         f"Up to {sgn(cs['cf_company_ch'] - enps(I.OCT))} pts company eNPS, "
         f"{sgn(cs['cf_ic_ch'] - enps(I.ic_o))} pts Intercity", "eNPS and Q2 for changed-manager staff (panel)",
         "Slide 4"),
        ("90-day onboarding standard: tools on day 1, buddy, 30/60/90 check-ins", "CHRO",
         f"Q5 for joiners up from {pct(fav(I.jfy.q5))} favourable; up to "
         f"{sgn(cs['cf_company'] - cs['cf_company_ch'])} pts company eNPS", "Q5 and eNPS for tenure under 6 months",
         "Slide 5"),
        ("48-hour R1 feedback rule with reminders and escalation", "TA Head",
         f"Post-R1 withdrawals near zero (now {chh['withdrawn']} of {chh['n_slow']})",
         "Share of R1 feedback within 2 days", "Slide 9"),
        ("Offer floor of 0.90× expected CTC when the req budget allows", "TA Head",
         f"About {co['avoided']:.0f} fewer declines for {inr(co['extra'])} annual CTC",
         "Decline rate for offers below 0.90×", "Slide 10"),
        ("Senior-hiring track for G6+ and a fixed ATS SLA rule", "TA Head",
         f"G6+ within SLA up from {pct(100 - I.t10['p1'])}; accurate SLA reports",
         "G6+ within-SLA %; ATS mismatches", "Slide 8"),
    ]
    widths = [4.35, 1.15, 3.05, 2.55, 1.03]
    tbl = s.shapes.add_table(len(rows), 5, Inches(0.6), Inches(1.55), Inches(sum(widths)), Inches(5.2)).table
    for j, wd in enumerate(widths):
        tbl.columns[j].width = Inches(wd)
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(0.5 if i == 0 else 0.92)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(NAVY if i == 0 else (TINT2 if i % 2 else WHITE))
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            r = p.add_run()
            r.text = val
            r.font.name = FONT
            r.font.size = Pt(13 if i == 0 else 12.5)
            r.font.bold = i == 0 or j == 0
            r.font.color.rgb = rgb(WHITE if i == 0 else INK)
        if i:
            trace(11, f"table row {i}", " ".join(row[:4]), ["Recommendations", "Counterfactual impact"])
    footer(s, 11)
    notes(s, 11, "Priority = size of the effect, sample size and how directly the owner can act (the ranking in "
          "insights.md). Expected impacts are counterfactual upper bounds: eNPS impacts replace the affected groups' "
          "scores with same-manager colleagues in their thread; declines avoided use the 0.90-0.99 band's decline rate. "
          "Each measure can be read from the dashboard after the next wave.", ["Recommendations"])

    # 12 ─ data quality and limitations (data_quality.md) ────────────────────────
    s = prs.slides.add_slide(prs.slide_layouts[6])
    import pandas as pd
    log = pd.read_csv(ROOT / "data" / "clean" / "dq_log.csv")
    rec = pd.read_csv(ROOT / "data" / "clean" / "reconciliation.csv")

    def flow(ds, sheet):
        g = rec[(rec.dataset == ds) & (rec.sheet == sheet)].sort_values("order")
        return f"{int(g.rows.iloc[0]):,} → {int(g.rows.iloc[-1]):,}"

    def rows_of(prefix):
        return int(log[log.issue.astype(str).str.startswith(prefix)].rows_affected.sum())

    dq_head = (f"Every cleaning step is logged ({len(log)} rules), and the known gaps are stated, not hidden")
    text(s, 0.6, 0.42, 12.1, 1.2, dq_head, size=26, bold=True, color=NAVY, name="Headline")
    trace(12, "headline", dq_head, [], dq=True)
    cards = [(flow("eNPS", "eNPS_Responses"), "Survey responses in → valid"),
             (flow("eNPS", "Employee_Master"), "Employee records in → unique"),
             (flow("Recruitment", "Candidates"), "Candidates in → kept"),
             (f"{rows_of('No matching requisition')}", "Orphan candidates (requisition not in the extract) excluded"),
             (f"{rows_of('FINDING: system status disagrees')}", "ATS 'Within SLA' reqs that breached by dates"),
             (f"{rows_of('Exited with missing exit date')}", "Exited employees without an exit date (left before October)")]
    for k, (big, lab) in enumerate(cards):
        x, y = 0.6 + (k % 3) * 2.62, 1.6 + (k // 3) * 1.75
        box(s, x, y, 2.45, 1.55, fill=TINT2, name="DQ card")
        text(s, x + 0.18, y + 0.15, 2.15, 0.55, big, size=22, bold=True, color=ACCENT)
        text(s, x + 0.18, y + 0.72, 2.15, 0.78, lab, size=11.5, color=INK)
        trace(12, "dq card", big + " " + lab, [], dq=True)
    ms = ("manager_status: Changed manager = Manager Effective From between 18-Apr and 04-Oct-2026 and after joining; "
          "New joiner (first manager) = in that window and equal to the joining date; Same manager = everyone else.")
    box(s, 0.6, 5.2, 7.69, 1.6, fill=TINT, name="Definition")
    text(s, 0.8, 5.33, 7.3, 1.4, [[("Definition used throughout  ", {"bold": True, "color": ACCENT})], ms], size=13)
    lim = ["HRMS keeps only current attributes and the current manager: no history of thread, grade, rating or "
           "earlier manager moves.",
           "Survey answers are anonymous (salted key, groups of 5 or more), so individual follow-up is impossible by "
           "design.",
           "Synthetic data covering one half-year; the ATS SLA rule and the orphan candidates' requisitions are outside "
           "the extract."]
    box(s, 8.55, 1.6, 4.18, 5.2, fill=NAVY, name="Limitations")
    text(s, 8.8, 1.8, 3.7, 0.45, "Limitations", size=18, bold=True, color="93C5FD")
    text(s, 8.8, 2.35, 3.7, 4.3, lim, size=14, color=WHITE, space_after=12)
    footer(s, 12)
    notes(s, 12, "Counts come from data/clean/dq_log.csv and reconciliation.csv (also on the dashboard's Data quality page "
          "and in docs/data_quality.md). Raw workbooks are never modified; recomputed SLA status is used everywhere and the ATS "
          "disagreement is reported as a finding.", [], dq=True)

    prs.save(str(DECK))
    _fix_app_props(DECK, len(prs.slides))


def _fix_app_props(path: Path, n_slides: int) -> None:
    """python-pptx keeps its template's docProps/app.xml (4:3, 0 slides); write the real format and slide count."""
    import zipfile
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/app.xml":
                x = data.decode("utf-8")
                x = x.replace("On-screen Show (4:3)", "Widescreen")
                x = re.sub(r"<Slides>\d+</Slides>", f"<Slides>{n_slides}</Slides>", x)
                x = re.sub(r"<Notes>\d+</Notes>", f"<Notes>{n_slides}</Notes>", x)
                data = x.encode("utf-8")
            zout.writestr(item, data)
    tmp.replace(path)


def write_trace() -> None:
    out = ["# Deck number trace", "",
           "Every number on every slide of `docs/Porter_People_Insights.pptx` — headlines, stat cards, chart "
           "captions, tables and speaker notes — with the line of `docs/insights.md` (slide 12: "
           "`docs/data_quality.md`) where the same value appears. Generated by `pipeline/06_build_deck.py`; the build "
           "stops if a number cannot be traced. Line numbers refer to the files as generated in the same run.", "",
           "| Slide | Where | Number | Source | Line | Source text (start) |", "|---|---|---|---|---|---|"]
    for sl, where, tok, file, line, src_txt in TRACE_ROWS:
        out.append(f"| {sl} | {where} | {tok} | {file} | {line} | {src_txt.replace('|', '/')} |")
    TRACE.write_text("\n".join(out) + "\n", encoding="utf-8")


SUBMISSION = ROOT / "submission" / "02_Insight_Deck.pptx"


if __name__ == "__main__":
    import shutil
    build()
    write_trace()
    if SUBMISSION.parent.exists():          # local submission folder (not part of the repository)
        shutil.copyfile(DECK, SUBMISSION)
    print(f"{DECK.relative_to(ROOT)}: {TOTAL} slides; {len(TRACE_ROWS)} numbers traced → {TRACE.relative_to(ROOT)}")
