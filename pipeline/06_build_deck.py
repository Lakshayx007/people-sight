"""
06_build_deck.py
----------------
Builds docs/Porter_People_Insights.pptx, the 12-slide insight deck for the CHRO and the TA Head, and
docs/deck_number_trace.md, which lists every number on every slide (headlines, text, drawings, speaker notes) with the
line of docs/insights.md (docs/data_quality.md for the last slide) where the same value appears. The build stops if a
number cannot be traced.

Look: the template in pipeline/assets/deck (theme, light and dark layouts) filled with python-pptx; charts and diagrams
are drawn by pipeline/sketch.py in a hand-drawn style and embedded in the deck. Numbers come from
pipeline/05_insights.py, formatted with the same helpers, so a slide number and its insights.md line are the same string.

Run after 05_insights.py:  python pipeline/06_build_deck.py
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
from sketch import GREEN, GREY, INK, LAVENDER, PURPLE, RED, SOFTRED, YELLOW, Sketch  # noqa: E402

DOCS = ROOT / "docs"
DECK = DOCS / "Porter_People_Insights.pptx"
TRACE = DOCS / "deck_number_trace.md"
ART = Path(tempfile.gettempdir()) / "people_sight_deck_art"     # drawings are embedded in the deck
TEMPLATE = ROOT / "pipeline" / "assets" / "deck" / "template.pptx"

spec = importlib.util.spec_from_file_location("insights05", ROOT / "pipeline" / "05_insights.py")
I = importlib.util.module_from_spec(spec)
spec.loader.exec_module(I)

C_INK, C_MUTED, C_PURPLE, C_RED, C_GREEN, C_WHITE = "1E2A3A", "5B6475", "6A2BC2", "D9472F", "13866F", "FFFFFF"
C_SOFT, C_LINE, C_DARKTXT = "F3F5F8", "D9DEE7", "C9D1DE"
HEAD, BODY = "+mj-lt", "+mn-lt"     # theme heading font (Cambria) and body font (Calibri)
TOTAL = 12


def rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h)


# ── number tracing ────────────────────────────────────────────────────────────
INS_LINES = (DOCS / "insights.md").read_text(encoding="utf-8").splitlines()
DQ_LINES = (DOCS / "data_quality.md").read_text(encoding="utf-8").splitlines()
IGNORE = [r"\b20\d\d-\d\d-\d\d\b", r"\bG\d+(?:\+|-G\d+| to G\d+)?", r"\bQ\d\b", r"\bF\d+[ab]?\b",
          r"\b\d{1,2}-[A-Z][a-z]{2}(?:-\d{4})?\b", r"\b(?:30/60/90|48-hour|48 hours|90-day|1:1s?|16:9)\b",
          r"\bslides? \d+(?:[-–]\d+)?(?:, \d+)*\b", r"\b20\d\d\b", r"\bInterviewer [AB]\b", r"\b0\.90×",
          r"\bp < 0\.001\b", r"\bn<5\b", r"\b5 respondents\b", r"\b(?:first|one|two|three|five) ", r"\bweek 1\b",
          r"\b30 days\b", r"\b\d{1,2} (?:to|and) \d{1,2} (?:June|Jun)\b", r"\b\d{1,2}\s?(?:June|Jun)\b",
          r"\bsix threads\b", r"\b12 slides\b", r"^\d$", r"\b[1-5]\b(?= ?[·.)] )", r"\(\d\)", r"\bstep \d\b",
          r"\b0-10\b", r"\b1-5\b", r"\b(?:4|5) or (?:4|5)\b", r"\b9-10\b", r"\b0-6\b", r"\b7-8\b"]
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


def trace(slide_no: int, where: str, text: str, sources: list[str], dq: bool = False) -> str:
    clean = text.replace("−", "-")
    for pat in IGNORE:
        clean = re.sub(pat, " ", clean)
    lines = DQ_LINES if dq else INS_LINES
    order = []
    if not dq:
        for s in sources:
            order += list(_named(s) if s in ("Counterfactual impact", "Recommendations", "Ranking") else _section(s))
    order += list(range(len(lines)))
    for tok in dict.fromkeys(NUM.findall(clean)):
        core = tok.lstrip("+")
        pat = re.compile(r"(?<![\d.,])" + re.escape(tok if tok.startswith(("+", "-")) else core) + r"(?![\d])")
        hit = next((i for i in order if pat.search(lines[i])), None)
        if hit is None and "," in tok:          # display uses thousands separators; the source may not
            bare = re.compile(r"(?<![\d.,])" + re.escape(core.replace(",", "")) + r"(?![\d])")
            hit = next((i for i in order if bare.search(lines[i])), None)
        if hit is None:
            raise SystemExit(f"slide {slide_no}: number '{tok}' in {where} not found in "
                             f"{'data_quality.md' if dq else 'insights.md'}\n  text: {text}")
        TRACE_ROWS.append((slide_no, where, tok, "data_quality.md" if dq else "insights.md", hit + 1,
                           lines[hit].strip()[:140]))
    return text


def m(x: str) -> str:
    """Typographic minus for display (tracing treats it as '-')."""
    return x.replace("-", "−") if re.match(r"^-\d", x) else x


# ── slide helpers ─────────────────────────────────────────────────────────────
METRIC_TWIN = Path("/usr/share/fonts/truetype/crosextra/Caladea-Bold.ttf")   # same widths as Cambria Bold


def fits_one_line(title: str, n: int, width_in: float = 12.1, size_pt: int = 28) -> None:
    """Headlines must fit on one line; checked with Caladea (metric twin of Cambria) when it is installed."""
    if not METRIC_TWIN.exists():
        return
    from PIL import ImageFont
    w = ImageFont.truetype(str(METRIC_TWIN), size_pt * 10).getlength(title) / 10 / 72
    if w > width_in:
        raise SystemExit(f"slide {n}: headline is {w:.1f} in wide (max {width_in}): {title}")


class Deck:
    def __init__(self):
        self.prs = Presentation(str(TEMPLATE))
        ids = self.prs.slides._sldIdLst
        for sid in list(ids):                       # drop the template's sample slides
            self.prs.part.drop_rel(sid.rId)
            ids.remove(sid)
        self.layout = {l.name: l for l in self.prs.slide_layouts}

    def slide(self, n: int, eyebrow: str, title: str, sources: list[str], layout: str = "Content", dq: bool = False):
        s = self.prs.slides.add_slide(self.layout[layout])
        for ph in s.placeholders:
            if ph.placeholder_format.idx == 100:
                ph.text_frame.text = eyebrow.upper()
            elif ph.placeholder_format.idx == 101:
                ph.text_frame.text = title
        trace(n, "headline", title, sources, dq)
        if layout != "Opening":
            fits_one_line(title, n)
        if layout != "Opening":
            text(s, 12.23, 7.06, 0.5, 0.28, str(n), size=9, color="8A93A3", align=PP_ALIGN.RIGHT, name="Slide number")
        return s


def text(slide, x, y, w, h, paras, size=14, color=C_INK, bold=False, font=None, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, space_after=0, line=None, name=None, italic=False):
    """paras: str, or list of paragraphs; a paragraph is a str or a list of (text, {size, bold, color, font}) runs."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate(paras if isinstance(paras, list) else [paras]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        if line:
            p.line_spacing = line
        for run_text, o in ([(para, {})] if isinstance(para, str) else para):
            r = p.add_run()
            r.text = run_text
            f = r.font
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", italic)
            f.color.rgb = rgb(o.get("color", color))
            if o.get("font", font):
                f.name = o.get("font", font)
    return tb


def panel(slide, x, y, w, h, fill=C_SOFT, line=None, name=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = 0.08
    shp.fill.solid()
    shp.fill.fore_color.rgb = rgb(fill)
    if line:
        shp.line.color.rgb = rgb(line)
        shp.line.width = Pt(0.75)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    if name:
        shp.name = name
    return shp


def stat(slide, n, x, y, w, big, label, sources, color=C_PURPLE, big_size=44, label_size=14, label_h=0.75):
    trace(n, "stat", big + " " + label, sources)
    text(slide, x, y, w, 0.8, m(big), size=big_size, bold=True, color=color, font=HEAD, name="Stat value")
    text(slide, x, y + big_size / 72 + 0.12, w, label_h, label, size=label_size, color=C_MUTED, name="Stat label")


def picture(slide, path: Path, x, y, w, h, alt: str):
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    pic.name = path.stem
    pic._element.nvPicPr.cNvPr.set("descr", alt)
    return pic


def notes(slide, n, body, sources, dq=False):
    slide.notes_slide.notes_text_frame.text = body
    trace(n, "speaker notes", body, sources, dq)


def draw_text(n, sources, *strings):
    """Trace numbers that appear inside a drawing."""
    trace(n, "drawing", " · ".join(strings), sources)


# ── values (all from 05_insights.py) ─────────────────────────────────────────
sgn, pct, fav, enps, fmt_p, inr, times = I.sgn, I.pct, I.fav, I.enps, I.fmt_p, I.inr_lakh, I.times
cs, chh, co = I.COUNTERFACTUAL_SENT, I.COUNTERFACTUAL_HIRE, I.COUNTERFACTUAL_OFFER
ic_nj = I.nj_o[I.nj_o.thread == "Intercity"]
src = I.src_i


# ── drawings ──────────────────────────────────────────────────────────────────
def draw_sources(path: Path) -> Path:
    """Title slide: three sources feeding one cleaned view (light strokes for the dark background)."""
    s = Sketch(5.9, 5.3, seed=3)
    W, Y, D = "#F3F5F8", "#FFD84D", "#9AA4B5"
    items = [("Pulse survey", "April and October waves"), ("HRMS", "people, managers, exits"),
             ("Hiring tracker", "openings, candidates, offers")]
    for i, (a, b) in enumerate(items):
        y = 0.2 + i * 1.12
        s.box(0.15, y, 2.55, 0.86, stroke=W, lw=1.5)
        s.text(1.42, y + 0.36, a, size=17, color=W, weight="Bold", ha="center")
        s.text(1.42, y + 0.66, b, size=12, color=D, ha="center")
        s.arrow(2.82, y + 0.43, 3.62, 1.5 + 0.22 * (i - 1), color=D, bend=0.08 * (1 - i))
    s.box(3.7, 1.0, 2.0, 1.0, stroke=Y, lw=2.0, hachure="#FFD84D55", gap=0.09)
    s.text(4.7, 1.45, "People Sight", size=19, color=W, weight="Bold", ha="center")
    s.text(4.7, 1.77, "one clean view", size=13, color=Y, ha="center")
    s.text(4.7, 2.42, "every number traced\nto its query", size=12, color=D, ha="center", va="top")
    s.arrow(3.85, 2.15, 3.2, 3.95, color=Y, bend=0.25)
    s.text(0.2, 4.3, "why is sentiment moving?", size=17, color=Y, weight="Bold")
    s.text(0.2, 4.75, "what is slowing hiring?", size=17, color=Y, weight="Bold")
    return s.save(path)


def draw_threads(path: Path, n_slide: int) -> Path:
    """Slide 3: October eNPS by thread, diverging from zero."""
    o = I.OCT
    data = [(t, enps(o[o.thread == t]), int((o.thread == t).sum())) for t in I.by_thread_o.index]
    s = Sketch(7.4, 4.9, seed=11)
    zero, scale, top, gap = 3.05, 0.045, 0.45, 0.7
    s.line(zero, 0.3, zero, top + gap * len(data) - 0.1, color=GREY, lw=1.2, passes=1)
    s.text(zero, 0.2, "0", size=12, color=GREY, ha="center")
    for i, (t, v, n) in enumerate(data):
        y = top + i * gap
        bad = t == "Intercity"
        col = RED if bad else PURPLE
        x0, x1 = (zero + v * scale, zero) if v < 0 else (zero, zero + v * scale)
        s.box(x0, y, max(x1 - x0, 0.06), 0.42, stroke=col, lw=1.4, hachure=col, gap=0.07, rough=0.6)
        s.text(1.45, y + 0.2, t, size=14, color=INK, weight="Bold" if bad else "Regular", ha="right")
        s.text(1.45, y + 0.42, f"n {n}", size=11, color=GREY, ha="right")
        lx = x0 - 0.08 if v < 0 else x1 + 0.08
        s.text(lx, y + 0.29, m(sgn(v)), size=15, color=col, weight="Bold", ha="right" if v < 0 else "left")
        draw_text(n_slide, ["F3"], t, sgn(v), str(n))
    s.text(zero + 0.25, top + 0.3, "the only thread well below zero", size=13, color=RED)
    s.arrow(zero + 0.22, top + 0.22, zero - 0.12, top + 0.1, color=RED, bend=0.35, head=0.08, lw=1.3)
    pm = "Packers & Movers"
    rr_a, rr_o = I.rrp.loc[pm, "Apr"], I.rrp.loc[pm, "Oct"]
    y_pm = top + gap * (len(data) - 1)
    note = f"its response rate fell from\n{pct(rr_a)} to {pct(rr_o)}: read with care"
    s.sticky(4.85, y_pm - 1.75, 2.5, 1.2)
    s.text(5.02, y_pm - 1.38, "Packers & Movers up?", size=13, color=INK, weight="Bold")
    s.text(5.02, y_pm - 1.25, note, size=12, color=INK, va="top")
    s.arrow(5.6, y_pm - 0.5, 5.2, y_pm + 0.08, color=GREY, bend=0.25, head=0.09)
    draw_text(n_slide, ["F8"], note)
    return s.save(path)


def draw_reorg(path: Path, n_slide: int) -> Path:
    """Slide 4 left: the June reorganisation between the two survey waves."""
    bm = I.by_month
    s = Sketch(5.4, 4.7, seed=5)
    base, left, step = 3.45, 0.35, 0.68
    peak = max(bm.values)
    s.text(0.3, 0.32, "Intercity manager changes by month", size=13, color=GREY)
    s.line(left - 0.1, base, left + step * len(bm) - 0.1, base, color=INK, lw=1.4, passes=1)
    xs = {}
    for i, (mo, v) in enumerate(bm.items()):
        x = left + i * step
        xs[mo] = x
        h = 2.3 * v / peak if peak else 0
        if v:
            s.box(x, base - h, 0.42, h, stroke=PURPLE, hachure=PURPLE, gap=0.07, rough=0.6)
            s.text(x + 0.21, base - h - 0.12, str(int(v)), size=17, color=PURPLE, weight="Bold", ha="center")
        else:
            s.line(x + 0.02, base - 0.03, x + 0.38, base - 0.03, color=GREY, lw=1.2, passes=1)
        s.text(x + 0.21, base + 0.3, mo[:3], size=13, color=INK, ha="center")
    for i, lab in [(0, "April survey"), (len(bm) - 1, "October survey")]:
        x = left + i * step + 0.21
        s.line(x, base + 0.42, x, base + 0.58, color=GREY, lw=1.1, passes=1)
        s.text(x, base + 0.8, lab, size=12, color=GREY, ha="center", va="top")
    peak_mo = bm.idxmax()
    xp = xs[peak_mo]
    s.text(xp + 0.85, 1.45, f"{I.top2} of {len(I.ice)} moved", size=16, color=RED, weight="Bold")
    s.text(xp + 0.85, 1.76, "onto just two managers", size=13, color=RED)
    s.arrow(xp + 0.8, 1.55, xp + 0.5, 1.6 + 0.25, color=RED, bend=-0.3, head=0.09, lw=1.4)
    draw_text(n_slide, ["F3b"], f"{I.top2} of {len(I.ice)}", *[str(int(v)) for v in bm.values if v])
    return s.save(path)


def draw_intercity(path: Path, n_slide: int) -> Path:
    """Slide 4 right: Intercity eNPS April → October by manager status."""
    rows = [("Changed manager", I.ch_a, I.ch_o, RED), ("New joiner", None, ic_nj, RED),
            ("Same manager", I.ic_same_a, I.ic_same, PURPLE)]
    s = Sketch(6.6, 4.7, seed=9)
    lo, hi, L, R = -70, 30, 2.35, 6.35
    X = lambda v: L + (v - lo) / (hi - lo) * (R - L)  # noqa: E731
    s.text(0.15, 0.32, "Intercity eNPS, April to October", size=13, color=GREY)
    for v, lab in [(-60, "−60"), (-30, "−30"), (0, "0"), (30, "+30")]:
        s.line(X(v), 0.6, X(v), 3.55, color="#D9DEE7", lw=1.0, passes=1, dash=None if v == 0 else (3, 3))
        s.text(X(v), 3.82, lab, size=11, color=GREY, ha="center")
    for i, (lab, a, o, col) in enumerate(rows):
        y = 1.05 + i * 0.98
        s.text(0.15, y + 0.05, lab, size=15, color=INK, weight="Bold")
        va, vo = (enps(a) if a is not None and len(a) else None), enps(o)
        ns = f"n {len(a)} / {len(o)}" if va is not None else f"n {len(o)}, joined after April"
        s.text(0.15, y + 0.32, ns, size=11, color=GREY)
        if va is not None:
            s.line(X(va), y, X(vo), y, color=col, lw=2.0, rough=0.4)
            s.ellipse(X(va), y, 0.06, 0.06, color=GREY, lw=2.4)
            s.text(X(va), y + 0.33, f"Apr {m(sgn(va))}", size=12, color=GREY, ha="center")
        s.ellipse(X(vo), y, 0.08, 0.08, color=col, lw=3.0)
        near = abs(X(vo) - X(enps(I.rest_same))) < 0.75          # keep clear of the green reference line
        s.text(X(vo) + (0.08 if near else 0), y - 0.2, f"Oct {m(sgn(vo))}", size=16, color=col, weight="Bold",
               ha="right" if near else "center")
        draw_text(n_slide, ["F3a", "F2"], lab, sgn(vo), (sgn(va) if va is not None else ""), ns)
    xr = X(enps(I.rest_same))
    s.line(xr, 0.6, xr, 3.55, color=GREEN, lw=1.4, passes=1, dash=(5, 3))
    lab_r = f"green line: same-manager staff elsewhere, {sgn(enps(I.rest_same))}"
    s.text(R, 4.35, lab_r, size=11.5, color=GREEN, ha="right")
    draw_text(n_slide, ["F3a"], sgn(enps(I.rest_same)))
    return s.save(path)


def draw_onboarding(path: Path, n_slide: int) -> Path:
    """Slide 5: Q5 onboarding % favourable, under 6 months vs everyone else, both waves."""
    groups = [("April", I.a6n, I.a6o), ("October", I.t6n, I.t6o)]
    s = Sketch(6.9, 4.75, seed=13)
    base, scale = 3.85, 0.055
    s.line(0.3, base, 6.6, base, color=INK, lw=1.4, passes=1)
    for g, (wave, new, old) in enumerate(groups):
        for k, (df, col, lab) in enumerate([(new, RED, "under 6 months"), (old, PURPLE, "6 months or more")]):
            v = fav(df.q5)
            x = 0.65 + g * 3.15 + k * 1.25
            h = v * scale
            s.box(x, base - h, 0.95, h, stroke=col, hachure=col, gap=0.075, rough=0.6)
            s.text(x + 0.47, base - h - 0.14, pct(v), size=19, color=col, weight="Bold", ha="center")
            s.text(x + 0.47, base + 0.28, f"n {len(df)}", size=11, color=GREY, ha="center")
            draw_text(n_slide, ["F6"], pct(v), str(len(df)))
        s.text(0.65 + g * 3.15 + 1.1, base + 0.66, wave, size=16, color=INK, weight="Bold", ha="center")
    s.text(0.35, 0.3, "rate onboarding & tools favourably (Q5: 4 or 5)", size=13, color=GREY)
    s.box(0.4, 0.6, 0.22, 0.18, stroke=RED, hachure=RED, gap=0.05, lw=1.1, rough=0.3)
    s.text(0.72, 0.75, "under 6 months", size=13, color=RED)
    s.box(2.45, 0.6, 0.22, 0.18, stroke=PURPLE, hachure=PURPLE, gap=0.05, lw=1.1, rough=0.3)
    s.text(2.77, 0.75, "6 months or more", size=13, color=PURPLE)
    return s.save(path)


def draw_quadrant(path: Path, n_slide: int) -> Path:
    """Slide 6 left: driver importance (link with Q1) vs October score."""
    imp = I.imp
    s = Sketch(6.3, 4.8, seed=17)
    L, R, T, B = 0.75, 6.0, 0.45, 3.95
    r0, r1 = float(imp.rho.min()) - 0.015, float(imp.rho.max()) + 0.02
    m0, m1 = float(imp.mean_oct.min()) - 0.05, float(imp.mean_oct.max()) + 0.06
    X = lambda r: L + (r - r0) / (r1 - r0) * (R - L)  # noqa: E731
    Yv = lambda v: B - (v - m0) / (m1 - m0) * (B - T)  # noqa: E731
    xm, ym = X(float(imp.rho.median())), Yv(float(imp.mean_oct.median()))
    s._poly(xm, ym, R - xm, B - ym, "#FFE89A99")
    s.text(R - 0.1, B - 0.14, "fix first", size=15, color=RED, weight="Bold", ha="right")
    s.line(L, B, R, B, color=INK, lw=1.3, passes=1)
    s.line(L, T, L, B, color=INK, lw=1.3, passes=1)
    s.line(xm, T, xm, B, color=GREY, lw=1.0, passes=1, dash=(4, 3))
    s.line(L, ym, R, ym, color=GREY, lw=1.0, passes=1, dash=(4, 3))
    s.text((L + R) / 2 - 0.25, B + 0.42, "more linked to recommending Porter", size=12, color=GREY, ha="center")
    s.arrow((L + R) / 2 + 1.55, B + 0.36, (L + R) / 2 + 2.15, B + 0.36, color=GREY, bend=0, head=0.08, lw=1.2)
    s.text(L - 0.3, (T + B) / 2 + 0.25, "higher score", size=12, color=GREY, ha="center", va="center", rotation=90)
    s.arrow(L - 0.3, (T + B) / 2 - 0.4, L - 0.3, (T + B) / 2 - 0.95, color=GREY, bend=0, head=0.08, lw=1.2)
    placed = []          # label boxes (x0, y0, x1, y1), to avoid overlaps
    pts = [(X(float(r.rho)), Yv(float(r.mean_oct)), r) for _, r in imp.iterrows()]
    for x, y, _ in pts:
        placed.append((x - 0.09, y - 0.09, x + 0.09, y + 0.09))
    for x, y, r in sorted(pts, key=lambda p: -p[0]):
        is_fix = r.driver == I.fix.driver
        col = RED if is_fix else PURPLE
        s.ellipse(x, y, 0.07, 0.07, color=col, lw=3.0)
        name = r.driver.split(" ", 1)[1]
        size = 13.5 if is_fix else 12.5
        w = Sketch.width(name, size, "Bold" if is_fix else "Regular")
        for dx, dy, ha in [(0.13, -0.08, "left"), (0.13, 0.3, "left"), (-0.13, -0.08, "right"), (-0.13, 0.3, "right"),
                           (0.13, -0.3, "left"), (-0.13, -0.3, "right")]:
            x0 = x + dx if ha == "left" else x + dx - w
            box = (x0, y + dy - 0.18, x0 + w, y + dy + 0.03)
            clash = any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in placed)
            if not clash and box[0] > L and box[2] < R + 0.25:
                break
        placed.append(box)
        s.text(x + dx, y + dy, name, size=size, color=col, weight="Bold" if is_fix else "Regular", ha=ha)
    draw_text(n_slide, ["F4"], f"ρ = {I.fix.rho:.2f}")
    return s.save(path)


def draw_themes(path: Path, n_slide: int) -> Path:
    """Slide 6 right: comment themes, April → October."""
    tp = I.thm_p
    show = [(I.th1, RED), (I.th2, RED), ("Positive", GREY)]
    s = Sketch(5.0, 3.0, seed=19)
    xa, xo = 2.05, 3.85
    s.text(xa, 0.3, "April", size=13, color=GREY, ha="center")
    s.text(xo, 0.3, "October", size=13, color=GREY, ha="center")
    Y = lambda v: 2.8 - (v - 5) / 35 * 2.25  # noqa: E731

    def spread(vals):
        """Label y positions at least 0.24 in apart, in the order of the values."""
        order = sorted(range(len(vals)), key=lambda i: Y(vals[i]))
        ys, last = [0.0] * len(vals), -9.0
        for i in order:
            ys[i] = max(Y(vals[i]), last + 0.24)
            last = ys[i]
        return ys

    a_vals = [float(tp.loc[t, "Apr"]) for t, _ in show]
    o_vals = [float(tp.loc[t, "Oct"]) for t, _ in show]
    ya, yo = spread(a_vals), spread(o_vals)
    for k, (th, col) in enumerate(show):
        a, o = a_vals[k], o_vals[k]
        s.line(xa, Y(a), xo, Y(o), color=col, lw=2.0, rough=0.4)
        s.ellipse(xa, Y(a), 0.05, 0.05, color=col, lw=2.6)
        s.ellipse(xo, Y(o), 0.05, 0.05, color=col, lw=2.6)
        s.text(xa - 0.13, ya[k] + 0.06, f"{th.lower()}  {pct(a)}", size=12.5, color=col, ha="right")
        s.text(xo + 0.13, yo[k] + 0.06, pct(o), size=13, color=col, weight="Bold", ha="left")
        draw_text(n_slide, ["F4"], pct(a), pct(o))
    return s.save(path)


def draw_exits(path: Path, n_slide: int) -> Path:
    """Slide 7: April group → share who left voluntarily → backfill."""
    groups = [("Detractors", I.det, RED), ("Passives", I.pas, GREY), ("Promoters", I.pro, PURPLE)]
    s = Sketch(12.1, 4.5, seed=23)
    base, scale = 3.6, 0.095
    s.text(0.3, 0.32, "share of each April survey group who left voluntarily by October", size=13, color=GREY)
    s.line(0.25, base, 5.1, base, color=INK, lw=1.4, passes=1)
    for i, (lab, df, col) in enumerate(groups):
        v = 100 * df.vol.mean()
        x = 0.5 + i * 1.55
        h = v * scale
        s.box(x, base - h, 1.0, h, stroke=col, hachure=col, gap=0.075, rough=0.6)
        s.text(x + 0.5, base - h - 0.14, pct(v), size=20, color=col, weight="Bold", ha="center")
        s.text(x + 0.5, base + 0.32, lab, size=14, color=INK, ha="center")
        s.text(x + 0.5, base + 0.6, f"n {len(df)}", size=11, color=GREY, ha="center")
        draw_text(n_slide, ["F7"], pct(v), str(len(df)))
    s.text(8.4, 0.32, "joining the survey with HRMS exits and hiring reqs", size=13, color=PURPLE, weight="Bold",
           ha="center")
    s.arrow(5.35, 2.0, 6.45, 2.0, color=GREY, bend=-0.12)
    s.box(6.55, 1.5, 2.0, 1.0, stroke=INK, fill="#FFFFFF")
    s.text(7.55, 1.93, "an exit", size=17, color=INK, weight="Bold", ha="center")
    s.text(7.55, 2.25, "HRMS", size=12, color=GREY, ha="center")
    reg = f"{pct(I.t7r['p1'])} of detractors left\nregrettably, vs {pct(I.t7r['p2'])} of promoters"
    s.text(7.55, 2.85, reg, size=12, color=RED, ha="center", va="top")
    s.arrow(8.65, 2.0, 9.6, 2.0, color=GREY, bend=0.12)
    s.box(9.7, 1.15, 2.2, 1.7, stroke=PURPLE, hachure=LAVENDER, gap=0.07)
    med = f"{I.bf.days_exit_to_req.median():.0f} days"
    s.text(10.8, 1.66, "a backfill req", size=16, color=INK, weight="Bold", ha="center")
    s.text(10.8, 2.05, "raised a median", size=13, color=INK, ha="center")
    s.text(10.8, 2.42, f"{med} later", size=16, color=PURPLE, weight="Bold", ha="center")
    pre = int((I.bf.days_exit_to_req < 0).sum())
    rb = (f"{pct(100 * len(I.reg_b) / len(I.bf))} replace regrettable exits\n"
          f"n {len(I.bf)} backfills; only {pre} were\nraised before the person left")
    s.text(10.8, 3.15, rb, size=12, color=GREY, ha="center", va="top")
    draw_text(n_slide, ["F16"], med, rb)
    draw_text(n_slide, ["F7"], reg)
    return s.save(path)


def draw_journey(path: Path, n_slide: int) -> Path:
    """Slide 8: median days per stage for the eventual hire, G2-G5 vs G6+."""
    t20 = I.tests20
    stages = [lab for lab, _ in I.STAGES]
    jun = [float(t20[lab]["med_b"]) for lab in stages]
    sen = [float(t20[lab]["med_a"]) for lab in stages]
    s = Sketch(12.1, 3.2, seed=29)
    left, scale = 1.75, 0.155
    rows = [("G2 to G5", jun, len(I.jun20)), ("G6+", sen, len(I.sen20))]
    ends = []
    for r, (lab, vals, n) in enumerate(rows):
        y = 0.6 + r * 1.3
        s.text(left - 0.18, y + 0.33, lab, size=16, color=INK, weight="Bold", ha="right")
        s.text(left - 0.18, y + 0.6, f"n {n} hires", size=11, color=GREY, ha="right")
        x = left
        for k, v in enumerate(vals):
            w = max(v, 0.6) * scale
            first = k == 0
            col = (RED if r == 1 else PURPLE) if first else GREY
            s.box(x, y, w, 0.62, stroke=col, hachure=col if first else "#C8CDD6", gap=0.075, rough=0.5, lw=1.3)
            if first:
                s.text(x + w / 2, y + 0.42, f"{v:.0f}d", size=15, color=col, weight="Bold", ha="center")
            x += w
        ends.append(x)
        draw_text(n_slide, ["F20"], *[f"{v:.0f}" for v in vals], str(n))
    s.text(left, 0.42, "from req raised until the eventual hire applies", size=12.5, color=RED, weight="Bold")
    s.text(ends[0] + 0.3, 0.6 + 0.28, "then shortlist, screening, interviews and offer:",
           size=12.5, color=GREY)
    s.text(ends[0] + 0.3, 0.6 + 0.55, "a few days each, for every grade", size=12.5, color=GREY)
    s.arrow(ends[0] + 0.25, 0.6 + 0.4, ends[0] + 0.03, 0.6 + 0.32, color=GREY, bend=0.2, head=0.07, lw=1.2)
    return s.save(path)


def draw_feedback(path: Path, n_slide: int) -> Path:
    """Slide 9: median R1 feedback days, the two slow interviewers vs the company."""
    rows = [("Interviewer A", I.per_int.loc[I.slow_ids[0], "median"], int(I.per_int.loc[I.slow_ids[0], "size"]), RED),
            ("Interviewer B", I.per_int.loc[I.slow_ids[1], "median"], int(I.per_int.loc[I.slow_ids[1], "size"]), RED),
            ("Everyone else", I.med_all, None, PURPLE)]
    s = Sketch(6.3, 3.9, seed=31)
    left, scale = 2.05, 0.25
    s.text(0.15, 0.3, "median days to submit R1 feedback", size=13, color=GREY)
    for i, (lab, v, n, col) in enumerate(rows):
        y = 0.7 + i * 0.95
        s.text(left - 0.15, y + 0.3, lab, size=15, color=INK, weight="Bold", ha="right")
        if n:
            s.text(left - 0.15, y + 0.58, f"n {n} interviews", size=11, color=GREY, ha="right")
        w = max(float(v) * scale, 0.12)
        s.box(left, y, w, 0.5, stroke=col, hachure=col, gap=0.075, rough=0.5)
        s.text(left + w + 0.12, y + 0.36, f"{float(v):.0f} day{'s' if float(v) != 1 else ''}", size=18, color=col,
               weight="Bold")
        draw_text(n_slide, ["F12"], f"{float(v):.0f}", str(n or ""))
    xg = left + 2 * scale
    s.line(xg, 0.55, xg, 3.4, color=GREEN, lw=1.3, passes=1, dash=(4, 3))
    s.text(xg + 0.1, 3.62, "a 48-hour rule", size=12, color=GREEN)
    return s.save(path)


def draw_withdrawals(path: Path, n_slide: int) -> Path:
    """Slide 9 right: candidates who withdrew after R1."""
    s = Sketch(4.6, 3.9, seed=37)
    s.text(0.1, 0.3, "R1 candidates who withdrew", size=13, color=GREY)
    a = f"{chh['withdrawn']} of {chh['n_slow']}"
    b = f"{I.wd_o} of {len(I.other_c):,}"
    s.text(0.1, 1.2, a, size=40, color=RED, weight="Bold")
    wa = Sketch.width(a, 40, "Bold")
    s.ellipse(0.1 + wa / 2, 1.02, wa / 2 + 0.22, 0.38, color=RED, lw=1.8)
    s.text(0.12, 1.72, "with the two slow interviewers", size=13, color=INK)
    s.text(0.1, 2.7, b, size=40, color=PURPLE, weight="Bold")
    s.text(0.12, 3.12, "with everyone else", size=13, color=INK)
    draw_text(n_slide, ["F12"], a, b)
    return s.save(path)


def draw_offers(path: Path, n_slide: int) -> Path:
    """Slide 10: decline rate by offered ÷ expected CTC band."""
    off = I.off
    bands = [("below 0.90×", off[off.offer_to_expected_ratio < 0.90], RED),
             ("0.90 to 0.99×", off[(off.offer_to_expected_ratio >= 0.90) & (off.offer_to_expected_ratio < 1.00)], PURPLE),
             ("1.00× or more", off[off.offer_to_expected_ratio >= 1.00], PURPLE)]
    s = Sketch(6.6, 4.6, seed=41)
    base, scale = 3.7, 0.068
    s.text(0.3, 0.3, "offers declined, by offer ÷ what the candidate expected", size=13, color=GREY)
    s.line(0.25, base, 6.3, base, color=INK, lw=1.4, passes=1)
    for i, (lab, df, col) in enumerate(bands):
        v = 100 * df.is_offer_declined.mean()
        x = 0.6 + i * 1.95
        h = v * scale
        s.box(x, base - h, 1.25, h, stroke=col, hachure=col, gap=0.075, rough=0.6)
        s.text(x + 0.62, base - h - 0.14, pct(v), size=21, color=col, weight="Bold", ha="center")
        s.text(x + 0.62, base + 0.32, lab, size=14, color=INK, ha="center")
        s.text(x + 0.62, base + 0.6, f"n {len(df)} offers", size=11, color=GREY, ha="center")
        draw_text(n_slide, ["F13"], pct(v), str(len(df)))
    return s.save(path)


def draw_dq(path: Path, n_slide: int, rows: list[tuple[str, str, str]]) -> Path:
    """Slide 12: raw → clean, on the dark background."""
    s = Sketch(6.9, 4.2, seed=43)
    W, Y, D, RAW = "#F3F5F8", "#FFD84D", "#9AA4B5", "#F08A78"
    xr, xc = 3.35, 5.9
    s.text(xr, 0.3, "as received", size=14, color=RAW, ha="center")
    s.text(xc, 0.3, "used", size=14, color=Y, ha="center")
    for i, (lab, raw, clean) in enumerate(rows):
        y = 0.95 + i * 0.78
        s.text(0.05, y, lab, size=13.5, color=W)
        s.text(xr, y, raw, size=15, color=RAW, ha="center")
        w = Sketch.width(raw, 15)
        s.line(xr - w / 2 - 0.05, y - 0.09, xr + w / 2 + 0.05, y - 0.07, color=RAW, lw=1.4, passes=1)
        s.arrow(xr + 0.75, y - 0.08, xc - 0.75, y - 0.08, color=D, bend=0.0, head=0.1)
        s.text(xc, y, clean, size=15, color=Y, weight="Bold", ha="center")
    return s.save(path)


def draw_sticky(path: Path, w: float, h: float, lines: list[tuple[str, int, str]], seed: int = 51,
                color: str = YELLOW) -> Path:
    """A sticky note with handwritten lines: (text, size, weight)."""
    s = Sketch(w, h, seed=seed)
    s.sticky(0.05, 0.05, w - 0.15, h - 0.15, color=color)
    y = 0.22
    for t, size, weight in lines:
        y += size / 72 * 1.25
        s.text(0.28, y - 0.06, t, size=size, color=INK, weight=weight)
    return s.save(path)


def draw_label(path: Path, w: float, h: float, label: str, size: int = 17, color: str = PURPLE, seed: int = 53) -> Path:
    s = Sketch(w, h, seed=seed)
    s.text(0.02, h * 0.7, label, size=size, color=color, weight="Bold")
    return s.save(path)


def draw_circle_num(path: Path, label: str, seed: int) -> Path:
    s = Sketch(0.62, 0.62, seed=seed)
    s.num_circle(0.31, 0.31, label, r=0.22, color=PURPLE, size=17)
    return s.save(path)


# ── the deck ──────────────────────────────────────────────────────────────────
def build() -> None:
    if ART.exists():
        shutil.rmtree(ART)
    ART.mkdir(parents=True)
    d = Deck()
    cp = d.prs.core_properties
    import datetime as _dt
    cp.title = "People Sight: what is moving sentiment and slowing hiring at Porter"
    cp.author = cp.last_modified_by = "Lakshay Malik"
    cp.subject = "Employee sentiment and hiring, April to October 2026"
    cp.keywords, cp.category, cp.comments = "People Sight", "People analytics", ""
    cp.created = cp.modified = _dt.datetime(2026, 11, 5)
    cp.revision = 1

    # 1 ─ opening ───────────────────────────────────────────────────────────────
    n = 1
    s = d.slide(n, "Porter · People analytics · April to October 2026",
                "What is moving sentiment and slowing hiring", [], layout="Opening")
    text(s, 0.7, 3.75, 6.1, 1.0, "Findings from the April and October pulse surveys, HRMS and the hiring tracker, "
         "written for the CHRO and the TA Head", size=18, color=C_DARKTXT)
    text(s, 0.7, 5.25, 6.2, 0.9, [[("Prepared by Lakshay Malik", {"bold": True, "color": C_WHITE})],
                                  "People Sight, Porter People Analytics"], size=15, color=C_DARKTXT, space_after=2)
    text(s, 0.7, 6.55, 6.2, 0.35, "Data as of 31-Oct-2026  ·  sample data  ·  every number shows its base n",
         size=12, color="8A93A3")
    picture(s, draw_sources(ART / "s01_sources.png"), 7.15, 1.0, 5.9, 5.3,
            "Pulse survey, HRMS and hiring tracker feeding one clean view")
    notes(s, n, "This deck answers two questions: why employee sentiment moved between the April and October 2026 "
          "pulse surveys, and what is slowing hiring. It joins the survey with HRMS (managers, tenure, exits) and the "
          "hiring tracker, always without names on survey answers. Every number on the slides comes from code and is "
          "listed in docs/deck_number_trace.md with the line of docs/insights.md it comes from.", [])

    # 2 ─ the short answer ─────────────────────────────────────────────────────
    n = 2
    s = d.slide(n, "The short answer", "Two groups explain the eNPS fall; three process gaps slow hiring",
                ["F1"])
    picture(s, draw_label(ART / "s02_l.png", 4.5, 0.5, "why sentiment fell"), 0.6, 1.55, 4.5, 0.5,
            "Why sentiment fell")
    picture(s, draw_label(ART / "s02_r.png", 4.5, 0.5, "what slows hiring"), 6.95, 1.55, 4.5, 0.5,
            "What slows hiring")
    left = [
        (sgn(enps(I.ch_o)), C_RED, ["F2", "F3b"],
         f"eNPS of people who changed manager in the June Intercity reorganisation (n = {len(I.ch_o)}), vs "
         f"{sgn(enps(I.sm_o))} with the same manager (n = {len(I.sm_o)})"),
        (pct(fav(I.t6n.q5)), C_RED, ["F6"],
         f"of under-6-month staff rate onboarding favourably (n = {len(I.t6n)}), vs {pct(fav(I.t6o.q5))} of everyone "
         f"else (n = {len(I.t6o)})"),
        (pct(I.t7["p1"]), C_PURPLE, ["F7"],
         f"of April detractors left voluntarily by October (n = {len(I.det)}), vs {pct(I.t7['p2'])} of promoters "
         f"(n = {len(I.pro)}): sentiment predicts exits"),
    ]
    right = [
        (f"{I.st_sen[I.i_long]:.0f} days", C_RED, ["F20"],
         f"before the eventual hire even applies for a G6+ role (n = {len(I.sen20)} hires), vs "
         f"{I.tests20[I.STAGES[I.i_long][0]]['med_b']:.0f} for G2 to G5; interviews take days"),
        (f"{chh['withdrawn']} of {chh['n_slow']}", C_RED, ["F12"],
         f"R1 candidates of two slow interviewers withdrew, vs {I.wd_o} of {len(I.other_c):,} for everyone else"),
        (pct(I.t13["p1"]), C_RED, ["F13"],
         f"of offers below 0.90× the candidate's expectation were declined (n = {len(I.low)}), vs "
         f"{pct(I.t13['p2'])} at 0.90× or more (n = {len(I.high)})"),
    ]
    for col, items in [(0.6, left), (6.95, right)]:
        for k, (big, color, srcs, line) in enumerate(items):
            y = 2.15 + k * 0.98
            trace(n, "summary row", big + " " + line, srcs)
            text(s, col, y, 2.0, 0.6, m(big), size=28, bold=True, color=color, font=HEAD)
            text(s, col + 2.05, y + 0.05, 3.75, 0.9, line, size=13.5, color=C_INK)
    asks = [("If we act on three things:", 17, "Bold"),
            ("1  a manager-transition playbook for the reorganised Intercity teams", 15, "Regular"),
            ("2  a 90-day onboarding standard for every new joiner", 15, "Regular"),
            ("3  a 48-hour R1 feedback rule and an offer floor of 0.90× when budget allows", 15, "Regular")]
    picture(s, draw_sticky(ART / "s02_asks.png", 7.9, 1.75, asks), 0.55, 5.12, 7.9, 1.75, "Three priority actions")
    cf = (f"October eNPS could return to {sgn(cs['cf_company'])}, above April's {sgn(enps(I.APR))}, if the two groups "
          f"scored like their same-manager colleagues (upper bound)")
    trace(n, "callout", cf, ["Counterfactual impact"])
    text(s, 8.75, 5.35, 3.95, 1.3, [[("What it is worth  ", {"bold": True, "color": C_PURPLE})], cf], size=13.5,
         color=C_INK)
    notes(s, n, "The short answer. Sentiment: two groups, people whose manager changed in the June Intercity "
          "reorganisation and new joiners, explain more than the whole April to October fall; everyone else held "
          "steady. Hiring: senior roles lose weeks before anyone applies, two slow interviewers lose candidates, and "
          "low offers get declined. The three asks are expanded with owners and expected impact on slide 11. eNPS is "
          "the share of promoters (9-10) minus detractors (0-6) on Q1.", ["F1", "Recommendations"])

    # 3 ─ where the fall sits ──────────────────────────────────────────────────
    n = 3
    s = d.slide(n, "Where the fall sits",
                f"eNPS fell {abs(enps(I.OCT) - enps(I.APR)):.1f} points, but only one thread is far below zero",
                ["F1", "F3"])
    stat(s, n, 0.6, 1.75, 4.6, f"{sgn(enps(I.APR))} → {sgn(enps(I.OCT))}",
         f"company eNPS, April to October (n = {len(I.APR)} / {len(I.OCT)})", ["F1"], color=C_RED)
    stat(s, n, 0.6, 3.35, 4.6, f"{sgn(I.pan_e_apr)} → {sgn(I.pan_e_oct)}",
         f"the same {len(I.pan)} people who answered both waves: the fall is real, not a change in who answered",
         ["F1"], color=C_PURPLE, label_h=0.8)
    stat(s, n, 0.6, 5.05, 4.6, fmt_p(I.t1["p"]),
         "not significant company-wide: look at groups, not at the headline", ["F1"], color=C_INK, big_size=36)
    picture(s, draw_threads(ART / "s03_threads.png", n), 5.55, 1.65, 7.4, 4.9, "October eNPS by thread")
    text(s, 5.75, 6.62, 7.0, 0.3, "October eNPS by thread. n = October respondents.", size=10.5, color=C_MUTED)
    notes(s, n, f"Company eNPS fell from {sgn(enps(I.APR))} to {sgn(enps(I.OCT))}. The panel of {len(I.pan)} people "
          f"who answered both waves fell by a similar amount, so it is not just a change in who answered, but neither "
          f"test is significant ({fmt_p(I.t1['p'])}). Intercity is the only thread far below zero "
          f"({sgn(enps(I.ic_o))}, n = {len(I.ic_o)}). Packers & Movers rose, but its response rate fell sharply, so "
          f"that rise should be read with care.", ["F1", "F3", "F8"])

    # 4 ─ why 1: the June reorganisation ───────────────────────────────────────
    n = 4
    s = d.slide(n, "Why sentiment fell · 1 of 2",
                "Intercity's fall sits in the teams reorganised in June", ["F3a", "F3b"])
    picture(s, draw_reorg(ART / "s04_reorg.png", n), 0.45, 1.6, 5.4, 4.7, "Intercity manager changes by month")
    text(s, 0.6, 6.45, 5.2, 0.45, f"HRMS manager-effective dates, n = {len(I.ice)} employees; no survey data",
         size=10.5, color=C_MUTED)
    trace(n, "caption", f"n = {len(I.ice)}", ["F3b"])
    picture(s, draw_intercity(ART / "s04_intercity.png", n), 6.2, 1.6, 6.6, 4.7,
            "Intercity eNPS by manager status, April and October")
    q2 = (f"Manager feedback (Q2): {pct(fav(I.ch_o.q2))} favourable after a change vs {pct(fav(I.sm_o.q2))} with the "
          f"same manager")
    trace(n, "callout", q2, ["F2"])
    picture(s, draw_sticky(ART / "s04_q2.png", 5.4, 0.9,
                           [(f"manager feedback after a change: {pct(fav(I.ch_o.q2))} favourable", 14, "Bold"),
                            (f"vs {pct(fav(I.sm_o.q2))} with the same manager (Q2, October)", 13, "Regular")], seed=55),
            7.3, 6.0, 5.4, 0.9, q2)
    notes(s, n, f"All {len(I.ice)} Intercity manager changes happened in one June reorganisation, between the two "
          f"surveys, and {I.top2} of them moved to just two managers (Manager A and Manager B, not named). People who "
          f"changed manager went from {sgn(enps(I.ch_a))} in April to {sgn(enps(I.ch_o))} in October; Intercity "
          f"colleagues who kept their manager rose to {sgn(enps(I.ic_same))}, close to same-manager staff elsewhere "
          f"({sgn(enps(I.rest_same))}). Within the same thread and grade the gap holds (permutation test, p < 0.001). "
          f"Manager changes come from HRMS; no names are joined to survey answers.", ["F3a", "F3b", "F2"])

    # 5 ─ why 2: onboarding ─────────────────────────────────────────────────────
    n = 5
    s = d.slide(n, "Why sentiment fell · 2 of 2",
                "New joiners rate onboarding lowest, in both survey waves", ["F6"])
    picture(s, draw_onboarding(ART / "s05_onboarding.png", n), 0.5, 1.6, 6.9, 4.75,
            "Q5 onboarding favourable, under 6 months vs 6 months or more")
    stat(s, n, 7.95, 1.75, 4.8, sgn(enps(I.t6n)), f"eNPS of staff under 6 months, October (n = {len(I.t6n)})",
         ["F6"], color=C_RED)
    stat(s, n, 7.95, 3.25, 4.8, sgn(enps(I.nj_o)),
         f"eNPS of new joiners on their first manager (n = {len(I.nj_o)}), vs {sgn(enps(I.sm_o))} for same-manager staff",
         ["F2b"], color=C_RED)
    picture(s, draw_sticky(ART / "s05_note.png", 4.8, 1.25,
                           [("different people each wave,", 15, "Bold"), ("the same gap: fix the process", 15, "Bold")],
                           seed=57), 7.9, 5.05, 4.8, 1.25, "Different people each wave, the same gap")
    text(s, 0.6, 6.45, 6.8, 0.45, "Q5 'I had the onboarding, tools and training I needed', share answering 4 or 5",
         size=10.5, color=C_MUTED)
    notes(s, n, f"Under-6-month staff rate onboarding favourably far less than everyone else, in April "
          f"({pct(fav(I.a6n.q5))} vs {pct(fav(I.a6o.q5))}) and in October ({pct(fav(I.t6n.q5))} vs "
          f"{pct(fav(I.t6o.q5))}). Tenure is measured at each survey date, so these are different people each time: "
          f"the onboarding process is the problem, not one cohort. New joiners overlap heavily with the under-6-month "
          f"group, so this is one signal counted once.", ["F6", "F2b"])

    # 6 ─ what to fix first ─────────────────────────────────────────────────────
    n = 6
    s = d.slide(n, "What to fix first",
                f"{I.fix.driver.split(' ', 1)[1].capitalize()} matters most, and comments about it are rising",
                ["F4"])
    picture(s, draw_quadrant(ART / "s06_quadrant.png", n), 0.45, 1.6, 6.3, 4.8,
            "Driver importance versus October score")
    text(s, 0.6, 6.5, 6.2, 0.4, f"Importance = link with Q1 (Spearman, n = {int(I.fix.n)}); score = October mean, 1 to 5",
         size=10.5, color=C_MUTED)
    trace(n, "caption", f"n = {int(I.fix.n)}", ["F4"])
    picture(s, draw_label(ART / "s06_t.png", 5.0, 0.5, "what people write about", size=16), 7.35, 1.6, 5.0, 0.5,
            "What people write about")
    picture(s, draw_themes(ART / "s06_themes.png", n), 7.35, 2.05, 5.0, 3.0, "Comment themes April to October")
    text(s, 7.4, 5.0, 5.3, 0.3, f"Share of themed comments (n = {int(I.thm_n['Apr'])} / {int(I.thm_n['Oct'])})",
         size=10.5, color=C_MUTED)
    trace(n, "caption", f"n = {int(I.thm_n['Apr'])} / {int(I.thm_n['Oct'])}", ["F4"])
    pay = (f"Pay: staff paid below 0.90 of band mid rate fair pay favourably {pct(fav(I.below.q3))} "
           f"(n = {len(I.below)}) vs {pct(fav(I.atab.q3))} (n = {len(I.atab)})")
    trace(n, "callout", pay, ["F5"])
    panel(s, 7.35, 5.5, 5.38, 1.05, fill="F6F1FE", name="Pay callout")
    text(s, 7.6, 5.63, 4.95, 0.85, [[("Second lever: pay  ", {"bold": True, "color": C_PURPLE})],
                                   f"staff below 0.90 of band mid rate fair pay favourably {pct(fav(I.below.q3))} "
                                   f"(n = {len(I.below)}) vs {pct(fav(I.atab.q3))} (n = {len(I.atab)})"],
         size=13.5, color=C_INK)
    notes(s, n, f"Importance is the Spearman correlation of each driver with Q1 in October; {I.fix.driver} has the "
          f"strongest link among the below-median drivers (ρ = {I.fix.rho:.2f}) and an October mean of "
          f"{I.fix.mean_oct:.2f} out of 5. Correlation ranks where to look; it does not prove cause. Comments about "
          f"{I.th1.lower()} rose from {pct(I.thm_p.loc[I.th1, 'Apr'])} to {pct(I.thm_p.loc[I.th1, 'Oct'])} of themed "
          f"comments and positive comments fell. Below-band pay is a structural gap that was already there in April.",
          ["F4", "F5"])

    # 7 ─ survey → HRMS → hiring ────────────────────────────────────────────────
    n = 7
    s = d.slide(n, "Sentiment, exits and hiring",
                f"April detractors left at {times(I.t7['p1'], I.t7['p2'])} the rate of promoters", ["F7", "F16"])
    picture(s, draw_exits(ART / "s07_exits.png", n), 0.6, 1.6, 12.1, 4.5, "April survey group, voluntary exits and the backfill that follows")
    text(s, 0.6, 6.3, 12.1, 0.6, [[("So what  ", {"bold": True, "color": C_PURPLE}),
                                    ("use eNPS as an early warning: a stay-interview round in teams with many detractors "
                                     "within a month of each wave, and start backfills at resignation, not at exit.", {})]],
         size=14, color=C_INK)
    notes(s, n, f"Each April survey answer carries the person's exit outcome by 31-Oct-2026, attached from HRMS before "
          f"IDs are dropped, so the link stays anonymous. {pct(I.t7['p1'])} of detractors left voluntarily vs "
          f"{pct(I.t7['p2'])} of promoters (both p < 0.001). Replacement reqs were raised a median "
          f"{I.bf.days_exit_to_req.median():.0f} days after the exit (n = {len(I.bf)}). Being a detractor may reflect, "
          f"not cause, an intention to leave; either way it is an early signal.", ["F7", "F16"])

    # 8 ─ hiring 1: where the days go ───────────────────────────────────────────
    n = 8
    s = d.slide(n, "What slows hiring · 1 of 3",
                f"Senior roles lose {I.st_sen[I.i_long]:.0f} days before the eventual hire even applies", ["F20"])
    stat(s, n, 0.6, 1.7, 3.9, pct(I.t10["p1"]), f"of G6+ fills breached SLA (n = {len(I.hi)}), vs "
         f"{pct(I.t10['p2'])} for G2 to G5 (n = {len(I.lo)})", ["F10"], color=C_RED)
    stat(s, n, 4.75, 1.7, 3.9, f"{I.sen20.ttf_days.median():.0f} vs {I.jun20.ttf_days.median():.0f} days",
         f"median time to fill, G6+ vs G2 to G5", ["F20"], color=C_INK)
    stat(s, n, 8.9, 1.7, 3.9, f"{len(I.mm)} reqs", "marked 'Within SLA' in the tracker but breached by their dates",
         ["F15"], color=C_PURPLE)
    picture(s, draw_journey(ART / "s08_journey.png", n), 0.6, 3.35, 12.1, 3.2,
            "Median days per hiring stage for the eventual hire")
    text(s, 0.6, 6.62, 12.1, 0.3, "Median days per stage for the hired candidate. Stage medians do not add up to the "
         "median time to fill.", size=10.5, color=C_MUTED)
    notes(s, n, f"Time to fill is the hired candidate's offer acceptance date minus the date the req was raised. The "
          f"biggest extra delay for G6+ is before the eventual hire applies ({I.st_sen[I.i_long]:.0f} vs "
          f"{I.tests20[I.STAGES[I.i_long][0]]['med_b']:.0f} days, p < 0.001); screening and interviews take a few days "
          f"each. The tracker's own SLA status marks {len(I.mm)} breached reqs as within SLA, so SLA reports should "
          f"use the dates.", ["F20", "F15"])

    # 9 ─ hiring 2: slow R1 feedback ────────────────────────────────────────────
    n = 9
    s = d.slide(n, "What slows hiring · 2 of 3",
                "Two slow interviewers account for every post-R1 withdrawal", ["F12"])
    picture(s, draw_feedback(ART / "s09_feedback.png", n), 0.5, 1.6, 6.3, 3.9, "Median R1 feedback days")
    picture(s, draw_withdrawals(ART / "s09_withdrawals.png", n), 7.3, 1.6, 4.6, 3.9, "Candidates who withdrew after R1")
    wait = f"{chh['pending']} candidates on {chh['pending_reqs']} open reqs are still waiting for their feedback"
    trace(n, "callout", wait, ["F12", "Counterfactual impact"])
    picture(s, draw_sticky(ART / "s09_wait.png", 6.2, 0.95,
                           [(f"right now: {chh['pending']} candidates on {chh['pending_reqs']} open reqs", 15, "Bold"),
                            ("are still waiting for their R1 feedback", 13, "Regular")], seed=59),
            6.95, 5.6, 6.2, 0.95, wait)
    text(s, 0.6, 5.75, 6.1, 0.9, "Interviewer A (Engineering, G5) and Interviewer B (Engineering, G6). Names stay on "
         "the dashboard's Hiring page and are never joined to survey data.", size=10.5, color=C_MUTED)
    notes(s, n, f"R1 feedback turnaround is the feedback date minus the interview date, for interviewers with at least "
          f"5 interviews. The company median is {I.med_all:.0f} day. {chh['withdrawn']} of the {chh['n_slow']} "
          f"candidates these two interviewed withdrew, vs {I.wd_o} of {len(I.other_c):,} for everyone else (Fisher "
          f"exact test, p < 0.001). Withdrawal is a status, not a reason code, so other factors may contribute. "
          f"Separately, one recruiter holds {I.share:.0f}% of reqs without being slower: a continuity risk to "
          f"rebalance, not a performance issue.", ["F12", "F11"])

    # 10 ─ hiring 3: low offers ─────────────────────────────────────────────────
    n = 10
    s = d.slide(n, "What slows hiring · 3 of 3",
                f"Offers below 0.90× expectation are declined {times(I.t13['p1'], I.t13['p2'])} as often", ["F13"])
    picture(s, draw_offers(ART / "s10_offers.png", n), 0.45, 1.6, 6.6, 4.6, "Decline rate by offer band")
    fit = (f"{co['fits']} of {co['n_low']} low offers fit the budget at 0.90×", 16, "Bold")
    picture(s, draw_sticky(ART / "s10_fit.png", 5.5, 1.5,
                           [fit, (f"lifting them costs {inr(co['extra'])} a year", 14, "Regular"),
                            (f"and avoids about {co['avoided']:.0f} declines", 14, "Regular")], seed=61),
            7.25, 1.75, 5.5, 1.5, "Low offers that fit the budget")
    trace(n, "callout", f"{co['fits']} of {co['n_low']} {inr(co['extra'])} about {co['avoided']:.0f} declines",
          ["F13", "Counterfactual impact"])
    stat(s, n, 7.3, 3.6, 2.6, f"{pct(I.t14['p1'])}", f"agency offers accepted (n = {len(I.ag)}), vs "
         f"{pct(I.t14['p2'])} for other sources (n = {len(I.nag)})", ["F14"], color=C_RED, big_size=32, label_size=12.5,
         label_h=1.0)
    stat(s, n, 10.2, 3.6, 2.6, f"₹{src.loc['Agency', 'cost_per_joiner_inr']:,.0f}",
         f"agency fee per joiner; referrals convert {pct(100 * I.refs.is_hire.mean(), 2)} of applicants vs "
         f"{pct(100 * I.ags.is_hire.mean(), 2)}", ["F14"], color=C_INK, big_size=32, label_size=12.5, label_h=1.0)
    text(s, 7.3, 5.75, 5.4, 0.9, [[("So what  ", {"bold": True, "color": C_PURPLE}),
                                   ("set an offer floor of 0.90× expected CTC whenever the budget allows, and grow "
                                    "referrals and internal moves before using agencies.", {})]], size=14, color=C_INK)
    notes(s, n, f"Decline rate = declined / (accepted + declined) in each band of offered ÷ expected CTC. "
          f"{co['fits']} of the {co['n_low']} low offers could have been raised to 0.90× within the req's budgeted "
          f"maximum. Declines avoided assume the 0.90 to 0.99 band's decline rate. Expected CTC is self-reported and "
          f"declines can also reflect counter-offers. Agency fee = 8.33% of offered CTC for agency joiners; role mix by "
          f"source is not controlled.", ["F13", "F14", "Counterfactual impact"])

    # 11 ─ recommendations ──────────────────────────────────────────────────────
    n = 11
    s = d.slide(n, "Recommendations", "Five actions in priority order, each measurable at the next wave",
                ["Recommendations"])
    recs = [
        ("Manager-transition playbook", "HRBP check-in within 30 days, first 1:1 in week 1, skip-level review of the June "
         "Intercity move with Manager A and B", "CHRO",
         f"up to {sgn(cs['cf_company_ch'] - enps(I.OCT))} pts company eNPS, {sgn(cs['cf_ic_ch'] - enps(I.ic_o))} pts "
         f"Intercity", "slide 4"),
        ("90-day onboarding standard", "equipment and access on day one, a buddy, 30/60/90 check-ins, an onboarding "
         "owner per thread", "CHRO",
         f"Q5 for joiners up from {pct(fav(I.jfy.q5))}; up to {sgn(cs['cf_company'] - cs['cf_company_ch'])} pts "
         f"company eNPS", "slide 5"),
        ("48-hour R1 feedback rule", "automatic reminders and escalation; reassign the waiting candidates now",
         "TA Head", f"post-R1 withdrawals near zero (now {chh['withdrawn']} of {chh['n_slow']})", "slide 9"),
        ("Offer floor of 0.90× expected CTC", "when the req budget allows; TA Head sign-off for lower offers",
         "TA Head", f"about {co['avoided']:.0f} fewer declines for {inr(co['extra'])} a year", "slide 10"),
        ("Senior-hiring track for G6+", "start sourcing before approval, pre-agree offer ranges, and fix the tracker's "
         "SLA rule", "TA Head", f"G6+ within SLA up from {pct(100 - I.t10['p1'])}", "slide 8"),
    ]
    text(s, 1.35, 1.55, 6.0, 0.3, "ACTION", size=10, bold=True, color=C_MUTED)
    text(s, 7.45, 1.55, 1.1, 0.3, "OWNER", size=10, bold=True, color=C_MUTED)
    text(s, 8.65, 1.55, 3.0, 0.3, "EXPECTED IMPACT", size=10, bold=True, color=C_MUTED)
    text(s, 11.75, 1.55, 1.0, 0.3, "EVIDENCE", size=10, bold=True, color=C_MUTED)
    for k, (act, detail, owner, impact, ev) in enumerate(recs):
        y = 1.92 + k * 1.0
        panel(s, 0.6, y, 12.13, 0.88, fill=C_WHITE, line=C_LINE, name=f"Recommendation {k + 1}")
        picture(s, draw_circle_num(ART / f"s11_n{k + 1}.png", str(k + 1), seed=70 + k), 0.72, y + 0.13, 0.62, 0.62,
                f"Priority {k + 1}")
        text(s, 1.45, y + 0.12, 5.9, 0.75, [[(act, {"bold": True, "size": 15})], detail], size=12, color=C_INK)
        panel(s, 7.45, y + 0.27, 0.95, 0.34, fill="F6F1FE" if owner == "CHRO" else "E7F4F1", name="Owner")
        text(s, 7.45, y + 0.3, 0.95, 0.3, owner, size=11.5, bold=True,
             color=C_PURPLE if owner == "CHRO" else C_GREEN, align=PP_ALIGN.CENTER)
        text(s, 8.65, y + 0.14, 3.0, 0.7, impact, size=13, bold=True, color=C_PURPLE, anchor=MSO_ANCHOR.MIDDLE)
        text(s, 11.75, y + 0.14, 0.9, 0.6, ev, size=12, color=C_MUTED, anchor=MSO_ANCHOR.MIDDLE)
        trace(n, f"recommendation {k + 1}", f"{act} {detail} {impact}", ["Recommendations", "Counterfactual impact"])
    notes(s, n, "Priority follows the ranking in insights.md: size of the effect, sample size and how directly the owner "
          "can act. Expected impacts are upper bounds: the eNPS figures assume the affected groups would score like "
          "same-manager colleagues in their thread; declines avoided use the decline rate of offers at 0.90 to 0.99 of "
          "expectation. Each one can be read on the dashboard after the next survey wave.", ["Recommendations"])

    # 12 ─ data quality and limitations ─────────────────────────────────────────
    n = 12
    log = pd.read_csv(ROOT / "data" / "clean" / "dq_log.csv")
    rec = pd.read_csv(ROOT / "data" / "clean" / "reconciliation.csv")

    def flow(ds, sheet):
        g = rec[(rec.dataset == ds) & (rec.sheet == sheet)].sort_values("order")
        return f"{int(g.rows.iloc[0]):,}", f"{int(g.rows.iloc[-1]):,}"

    def rows_of(prefix):
        return int(log[log.issue.astype(str).str.startswith(prefix)].rows_affected.sum())

    s = d.slide(n, "Data quality and limits", "What the data can and cannot tell us", [], layout="Closing", dq=True)
    flows = [("survey responses", *flow("eNPS", "eNPS_Responses")),
             ("employee records", *flow("eNPS", "Employee_Master")),
             ("candidates", *flow("Recruitment", "Candidates")),
             ("SLA status in the tracker", f"{rows_of('FINDING: system status disagrees')} wrong", "recomputed")]
    for lab, a, b in flows:
        trace(n, "drawing", f"{a} {b}", [], dq=True)
    picture(s, draw_dq(ART / "s12_dq.png", n, flows), 0.55, 1.75, 6.9, 4.2, "Rows as received and rows used")
    text(s, 0.6, 6.15, 6.6, 0.7, f"{len(log)} cleaning checks, each logged with the rows it touched and why; the "
         f"original files are never edited.", size=13, color=C_DARKTXT)
    trace(n, "caption", f"{len(log)} checks", [], dq=True)
    lim = [("History.", "HRMS keeps only today's team, grade and manager, so earlier moves are invisible."),
           ("Anonymity.", "Survey answers carry no names and groups under 5 are hidden, so follow-up is by team, never "
                          "by person."),
           ("Short window.", "One half-year of sample data: exits and backfills have only months of follow-up."),
           ("Causality.", "These are links, not experiments; the April baseline rules out most, not all, other "
                          "explanations.")]
    text(s, 7.85, 1.75, 4.9, 0.4, "Limits to keep in mind", size=18, bold=True, color="FFD84D", font=HEAD)
    text(s, 7.85, 2.35, 4.9, 4.3, [[(a + " ", {"bold": True, "color": C_WHITE}), (b, {})] for a, b in lim],
         size=14, color=C_DARKTXT, space_after=12)
    notes(s, n, "Counts come from the cleaning log and the row reconciliation (also on the dashboard's Data quality page "
          "and in docs/data_quality.md). The tracker's SLA status disagrees with the dates on some reqs, so SLA is "
          "recomputed from dates everywhere. The raw workbooks are never modified.", [], dq=True)

    d.prs.save(str(DECK))
    _fix_app_props(DECK, len(d.prs.slides))


def _fix_app_props(path: Path, n_slides: int) -> None:
    """Write the real slide count into docProps/app.xml."""
    import zipfile
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/app.xml":
                x = data.decode("utf-8")
                x = re.sub(r"<Slides>\d+</Slides>", f"<Slides>{n_slides}</Slides>", x)
                x = re.sub(r"<Notes>\d+</Notes>", f"<Notes>{n_slides}</Notes>", x)
                data = x.encode("utf-8")
            zout.writestr(item, data)
    tmp.replace(path)


def write_trace() -> None:
    out = ["# Deck number trace", "",
           "Every number on every slide of `docs/Porter_People_Insights.pptx` (headlines, text, drawings and speaker "
           "notes) with the line of `docs/insights.md` (slide 12: `docs/data_quality.md`) where the same value "
           "appears. Generated by `pipeline/06_build_deck.py`; the build stops if a number cannot be traced. Line "
           "numbers refer to the files as generated in the same run.", "",
           "| Slide | Where | Number | Source | Line | Source text (start) |", "|---|---|---|---|---|---|"]
    for sl, where, tok, file, line, src_txt in TRACE_ROWS:
        out.append(f"| {sl} | {where} | {tok} | {file} | {line} | {src_txt.replace('|', '/')} |")
    TRACE.write_text("\n".join(out) + "\n", encoding="utf-8")


SUBMISSION = ROOT / "submission" / "02_Insight_Deck.pptx"


if __name__ == "__main__":
    build()
    write_trace()
    if SUBMISSION.parent.exists():          # local submission folder (not part of the repository)
        shutil.copyfile(DECK, SUBMISSION)
    print(f"{DECK.relative_to(ROOT)}: {TOTAL} slides; {len(TRACE_ROWS)} numbers traced → {TRACE.relative_to(ROOT)}")
