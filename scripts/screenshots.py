"""
screenshots.py — full-page Playwright screenshots at 1366px (desktop) and 390px (phone).

  sentiment: unfiltered · Thread = Intercity · drill-down (Intercity, then the first function row)
  hiring:    unfiltered · Recruiter = Rhea Kapoor AND Source = Agency · drill-down (click a grade bar)
  dq:        data-quality page
  ask:       Ask the Data panel open on /sentiment with one answered demo question (live Groq call)

Usage (app running on :8000):  python scripts/screenshots.py [out_dir] [scale] [pages] [base_url]
  pages = comma list of sentiment,hiring,dq (default: all). Prints console / page errors and drill URLs.
"""
import asyncio
import sys

from playwright.async_api import async_playwright

OUT = sys.argv[1] if len(sys.argv) > 1 else "analysis/screenshots"
SCALE = float(sys.argv[2]) if len(sys.argv) > 2 else 2
PAGES = (sys.argv[3] if len(sys.argv) > 3 else "sentiment,hiring,dq,ask").split(",")
BASE = sys.argv[4] if len(sys.argv) > 4 else "http://localhost:8000"

# Find a data point through the chart instance the app exposes on its DOM node and return its screen position.
POINT_JS = """([title, seriesName, idx]) => {
  const h = [...document.querySelectorAll('h3')].find(e => e.textContent.startsWith(title));
  const dom = h.closest('section').querySelector('div[_echarts_instance_]');
  dom.scrollIntoView({block: 'center'});
  const inst = dom.__chart; const opt = inst.getOption();
  const sIdx = opt.series.findIndex(s => s.name === seriesName);
  const s = opt.series[sIdx]; const d = s.data[idx];
  let v = d && d.value !== undefined ? d.value : d;
  if (!Array.isArray(v)) { const cats = (opt.xAxis[0].type === 'category' ? opt.xAxis[0] : opt.yAxis[0]).data; v = opt.xAxis[0].type === 'category' ? [cats[idx], v] : [v, cats[idx]]; }
  const px = inst.convertToPixel({seriesIndex: sIdx}, v);
  const r = dom.getBoundingClientRect();
  return {x: r.left + px[0], y: r.top + px[1] + (opt.xAxis[0].type === 'category' ? 6 : 0), label: (d && d.seg) || v[0]};
}"""


ASK_CHIP = "Intercity eNPS by manager status in October"


async def settle(page):
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1200)


async def shot(page, path):
    await page.evaluate("window.scrollTo(0, 0)")
    await page.mouse.move(0, 0)
    await page.wait_for_timeout(400)
    await page.screenshot(path=path, full_page=True)


async def run():
    log = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for width, tag in [(1366, "desktop"), (390, "mobile")]:
            ctx = await b.new_context(viewport={"width": width, "height": 900 if width > 500 else 844}, device_scale_factor=SCALE)
            page = await ctx.new_page()
            page.on("console", lambda m: log.append(f"{tag} console {m.type}: {m.text}") if m.type == "error" and "ERR_TUNNEL" not in m.text else None)
            page.on("pageerror", lambda e: log.append(f"{tag} pageerror: {e}"))

            if "sentiment" in PAGES:
                await page.goto(f"{BASE}/sentiment"); await settle(page)
                await shot(page, f"{OUT}/sentiment_unfiltered_{tag}.png")
                await page.goto(f"{BASE}/sentiment?thread=Intercity"); await settle(page)
                await shot(page, f"{OUT}/sentiment_intercity_{tag}.png")
                await page.select_option("select[aria-label='Break down by']", "function"); await settle(page)
                xy = await page.evaluate(POINT_JS, ["eNPS by function", "October", 0])
                await page.mouse.click(xy["x"], xy["y"]); await settle(page)
                log.append(f"{tag} sentiment drill ({xy['label']}): {page.url.replace(BASE, '')}")
                await shot(page, f"{OUT}/sentiment_drilldown_{tag}.png")

            if "hiring" in PAGES:
                await page.goto(f"{BASE}/hiring"); await settle(page)
                await shot(page, f"{OUT}/hiring_unfiltered_{tag}.png")
                await page.goto(f"{BASE}/hiring?recruiter=Rhea+Kapoor&source=Agency"); await settle(page)
                await shot(page, f"{OUT}/hiring_rhea_agency_{tag}.png")
                await page.goto(f"{BASE}/hiring"); await settle(page)
                xy = await page.evaluate(POINT_JS, ["Median time to fill by grade", "Median TTF", 6])
                await page.mouse.click(xy["x"], xy["y"]); await settle(page)
                log.append(f"{tag} hiring drill ({xy['label']}): {page.url.replace(BASE, '')}")
                await shot(page, f"{OUT}/hiring_drilldown_{tag}.png")

            if "dq" in PAGES:
                await page.goto(f"{BASE}/data-quality"); await settle(page)
                await shot(page, f"{OUT}/data_quality_{tag}.png")
            if "ask" in PAGES:
                await page.goto(f"{BASE}/sentiment"); await settle(page)
                await page.get_by_role("button", name="Ask" if width < 500 else "Ask the data", exact=True).first.click()
                await page.wait_for_timeout(600)
                await page.get_by_role("button", name=ASK_CHIP).click()
                await page.wait_for_selector("text=SQL that ran", timeout=90000)
                await page.wait_for_timeout(1500)
                panel = page.locator("aside[aria-hidden='false']")
                await page.screenshot(path=f"{OUT}/ask_answer_{tag}.png")
                body = panel.locator("div.overflow-y-auto").first
                await body.evaluate("el => el.scrollTo(0, el.scrollHeight * 0.45)")
                await page.wait_for_timeout(500)
                await page.screenshot(path=f"{OUT}/ask_answer_sql_{tag}.png")
                log.append(f"{tag} ask: answered '{ASK_CHIP}'")
            await ctx.close()
            if "ask" in PAGES and width > 500:
                await asyncio.sleep(30)   # Groq free tier: stay under the tokens-per-minute limit
        await b.close()
    print("\n".join(log) or "no errors")


asyncio.run(run())
