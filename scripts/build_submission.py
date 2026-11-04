"""
build_submission.py
-------------------
Builds the submission pack in submission/:
  01_Dashboards.pdf          live links, a full-page screenshot of /sentiment and /hiring, and a short "how to use"
  03_Data_Quality_Note.pdf   analysis/dq_note.md on one A4 page
  04_Working.zip             pipeline/, backend/, tests/, README.md, data/clean/dq_log.csv, analysis/profile.md

Usage (server running locally, e.g. uvicorn backend.main:app --port 8000):
  python scripts/build_submission.py --url https://<service>.onrender.com [--base http://localhost:8000]
Without --url the PDF shows a clearly marked placeholder; re-run with the live URL once Render is up.
Screenshots come from --base (the same code and data as the live site).
Needs: playwright (Chromium), markdown, pypdf, Pillow (requirements-analysis.txt).
"""
from __future__ import annotations

import argparse
import base64
import html as htmlmod
import io
import re
import zipfile
from datetime import date
from pathlib import Path

import markdown
from PIL import Image
from playwright.sync_api import sync_playwright
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "submission"
PLACEHOLDER = "https://<your-service>.onrender.com"

CSS = """
@page { size: A4; margin: 12mm; }
* { box-sizing: border-box; }
body { font-family: 'DejaVu Sans', Arial, sans-serif; color: #111827; margin: 0; font-size: 10pt; line-height: 1.4; }
h1 { font-size: 18pt; margin: 0 0 4pt; } h2 { font-size: 13pt; margin: 10pt 0 4pt; color: #1F2937; }
p { margin: 0 0 5pt; } a { color: #2563EB; text-decoration: none; }
.muted { color: #6B7280; } .warn { background: #FEF3C7; color: #92400E; padding: 4pt 6pt; border-radius: 4pt; }
.links td { padding: 3pt 8pt 3pt 0; font-size: 11pt; } .page { page-break-before: always; }
.shot { width: 100%; display: block; border: 1px solid #E5E7EB; margin-top: 4pt; }
ul { margin: 2pt 0 6pt 14pt; padding: 0; } li { margin: 0 0 2.5pt; }
table.t { border-collapse: collapse; width: 100%; } table.t th, table.t td { border: 1px solid #E5E7EB; padding: 2pt 4pt;
  text-align: left; vertical-align: top; } table.t th { background: #F3F4F6; }
blockquote { margin: 6pt 0 0; padding: 5pt 7pt; border-left: 3pt solid #2563EB; background: #EFF6FF; }
"""


def pages_of(pdf: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf)).pages)


def full_page(page, url: str, path: Path) -> Path:
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(2500)
    page.screenshot(path=str(path), full_page=True)
    return path


def slices(png: Path, aspect: float) -> list[str]:
    """Cut a tall screenshot into page-sized slices (height = width * aspect) as data URIs."""
    im = Image.open(png).convert("RGB")
    w, h = im.size
    step = int(w * aspect)
    out = []
    for top in range(0, h, step):
        part = im.crop((0, top, w, min(h, top + step)))
        buf = io.BytesIO()
        part.save(buf, "JPEG", quality=85, optimize=True)
        out.append("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
    return out


def dashboards_pdf(browser, base: str, live: str) -> Path:
    tmp = OUT / "_shots"
    tmp.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(viewport={"width": 1366, "height": 900}, device_scale_factor=1.5)
    page = ctx.new_page()
    shots = {name: full_page(page, f"{base}/{name}", tmp / f"{name}.png") for name in ["sentiment", "hiring"]}
    ctx.close()
    placeholder = live == PLACEHOLDER
    live = htmlmod.escape(live)
    warn = ('<p class="warn">Live URL not set yet — re-run <code>python scripts/build_submission.py --url '
            '&lt;render-url&gt;</code> after deploying.</p>' if placeholder else "")
    a4_aspect = (297 - 24 - 14) / (210 - 24)          # printable height / width, minus a caption line
    parts = [f"""<h1>Porter People Analytics — Dashboards</h1>
<p class="muted">Employee Sentiment (eNPS) and Hiring dashboards in one web app · data as of 31-Oct-2026 ·
generated {date.today():%d-%b-%Y}</p>{warn}
<table class="links">
<tr><td><b>Dashboard #1 — Employee Sentiment</b></td><td><a href="{live}/sentiment">{live}/sentiment</a></td></tr>
<tr><td><b>Dashboard #2 — Hiring</b></td><td><a href="{live}/hiring">{live}/hiring</a></td></tr>
<tr><td>Data quality</td><td><a href="{live}/data-quality">{live}/data-quality</a></td></tr></table>
<h2>How to use</h2>
<ul>
<li><b>Filters</b> (top bar): every filter is multi-select and applies to every KPI, chart and table on the page. Active
filters show as chips — click × to remove one, or <i>Clear all</i>. Filters live in the URL, so a filtered view can be
bookmarked or shared.</li>
<li><b>Drill-down</b>: click a bar, dot, heatmap cell, table row or month to add it as a filter; the breadcrumb shows the
path. On Hiring, click a grade, source, recruiter or month.</li>
<li><b>Show SQL</b>: every panel has a <i>SQL</i> button showing the exact query that produced it (parameter values at
the top). <b>n</b> badges give the base count; groups under 5 survey respondents show <i>n&lt;5</i> to protect
anonymity, and segments with a response rate under 50% carry a <i>Low response</i> warning.</li>
<li><b>Ask the Data</b> (sidebar, or <i>Ask</i> on a phone): type a question or pick a demo chip. The answer shows a
chart, a one-line method, the SQL that ran and the rows; tick <i>Apply current dashboard filters</i> to scope it, and
<i>Pin</i> an answer to the page. It is read-only, never shows individual survey answers and refuses questions about a
named person.</li>
<li><b>Enlarge</b> any chart with the expand icon; <b>Dark theme</b> toggle at the bottom of the sidebar. Works on phones
(filters and tables scroll sideways).</li>
</ul>"""]
    for name, title in [("sentiment", "Dashboard #1 — Employee Sentiment"), ("hiring", "Dashboard #2 — Hiring")]:
        for i, uri in enumerate(slices(shots[name], a4_aspect)):
            cap = f"{title} — full page ({live}/{name})" + (f", continued ({i + 1})" if i else "")
            parts.append(f'<div class="page"><p class="muted">{cap}</p><img class="shot" src="{uri}"></div>')
    html = f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(parts)}</body></html>"
    p = browser.new_page()
    p.set_content(html, wait_until="load")
    out = OUT / "01_Dashboards.pdf"
    out.write_bytes(p.pdf(format="A4", print_background=True))
    p.close()
    for f in tmp.glob("*.png"):
        f.unlink()
    tmp.rmdir()
    return out


def dq_pdf(browser) -> tuple[Path, int, float]:
    md = (ROOT / "analysis" / "dq_note.md").read_text(encoding="utf-8")
    body = markdown.markdown(md, extensions=["tables"])
    body = body.replace("<table>", '<table class="t">')
    base_css = CSS + "body { font-size: 8.6pt; } h1 { font-size: 14pt; } table.t { font-size: 7.8pt; margin-bottom: 3pt; }"
    page = browser.new_page()
    page.set_content(f"<html><head><meta charset='utf-8'><style>{base_css}</style></head><body>{body}</body></html>")
    for scale in [1.0, 0.95, 0.9, 0.85, 0.8, 0.75]:
        pdf = page.pdf(format="A4", print_background=True, scale=scale,
                       margin={"top": "10mm", "bottom": "10mm", "left": "11mm", "right": "11mm"})
        if pages_of(pdf) == 1:
            break
    page.close()
    out = OUT / "03_Data_Quality_Note.pdf"
    out.write_bytes(pdf)
    return out, pages_of(pdf), scale


def working_zip() -> tuple[Path, int]:
    out = OUT / "04_Working.zip"
    include = ["pipeline", "backend", "tests"]
    files = [p for d in include for p in sorted((ROOT / d).rglob("*"))
             if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    files += [ROOT / "README.md", ROOT / "data" / "clean" / "dq_log.csv", ROOT / "analysis" / "profile.md"]
    bad = [f for f in files if f.name == ".env" or "node_modules" in f.parts or "raw" in f.parts]
    assert not bad, bad
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.relative_to(ROOT).as_posix())
    return out, len(files)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=PLACEHOLDER, help="live Render URL, e.g. https://porter-people.onrender.com")
    ap.add_argument("--base", default="http://localhost:8000", help="where to take screenshots from")
    a = ap.parse_args()
    live = a.url.rstrip("/")
    if live != PLACEHOLDER and not re.match(r"^https?://", live):
        raise SystemExit("--url must start with http(s)://")
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        d = dashboards_pdf(browser, a.base.rstrip("/"), live)
        q, n_pages, scale = dq_pdf(browser)
        browser.close()
    z, n_files = working_zip()
    print(f"{d.name}: {pages_of(d.read_bytes())} pages ({'PLACEHOLDER URL' if live == PLACEHOLDER else live})")
    print(f"{q.name}: {n_pages} page(s) at scale {scale}")
    print(f"{z.name}: {n_files} files")


if __name__ == "__main__":
    main()
