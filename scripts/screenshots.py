"""
screenshots.py — full-page Playwright screenshots of /sentiment: unfiltered, Thread = Intercity, and after a
drill-down click (Intercity, then the first function row), at 1366px and 390px widths.
Usage (app running on :8000):  python scripts/screenshots.py [out_dir] [scale] [base_url]
Prints console errors / page errors and the URL reached by the drill-down.
"""
import asyncio, sys, json
from playwright.async_api import async_playwright

BASE = "http://localhost:8000"
OUT = sys.argv[1] if len(sys.argv) > 1 else "analysis/screenshots"
SCALE = float(sys.argv[2]) if len(sys.argv) > 2 else 2
BASE = sys.argv[3] if len(sys.argv) > 3 else BASE

async def settle(page):
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1200)

async def shot(page, path):
    await page.evaluate("window.scrollTo(0, 0)")
    await page.mouse.move(0, 0)
    await page.wait_for_timeout(400)
    await page.screenshot(path=path, full_page=True)

async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        errors = []
        for width, tag in [(1366, "desktop"), (390, "mobile")]:
            ctx = await b.new_context(viewport={"width": width, "height": 900 if width > 500 else 844}, device_scale_factor=SCALE)
            page = await ctx.new_page()
            page.on("console", lambda m: errors.append(f"{tag} console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda e: errors.append(f"{tag} pageerror: {e}"))
            # 1 unfiltered
            await page.goto(f"{BASE}/sentiment"); await settle(page)
            await shot(page, f"{OUT}/sentiment_unfiltered_{tag}.png")
            # 2 thread = Intercity
            await page.goto(f"{BASE}/sentiment?thread=Intercity"); await settle(page)
            await shot(page, f"{OUT}/sentiment_intercity_{tag}.png")
            # 3 drill-down: switch the segment chart to Function and click the first row label
            await page.select_option("select[aria-label='Break down by']", "function"); await settle(page)
            # find the October dot of the first function row via the chart instance and click it
            xy = await page.evaluate("""() => {
              const h = [...document.querySelectorAll('h3')].find(e => e.textContent.startsWith('eNPS by function'));
              const dom = h.closest('section').querySelector('div[_echarts_instance_]'); dom.scrollIntoView({block: 'center'});
              const inst = dom.__chart; const opt = inst.getOption();
              const oct = opt.series.find(s => s.name === 'October');
              const d = oct.data[0]; const px = inst.convertToPixel({seriesName: 'October'}, d.value);
              const r = dom.getBoundingClientRect();
              return {x: r.left + px[0], y: r.top + px[1], seg: d.seg};
            }""")
            await page.mouse.click(xy["x"], xy["y"])
            errors.append(f"{tag} clicked {xy['seg']}")
            await settle(page)
            url = page.url
            await shot(page, f"{OUT}/sentiment_drilldown_{tag}.png")
            errors.append(f"{tag} drill url: {url}")
            await ctx.close()
        await b.close()
        print("\n".join(errors) or "no console errors")

asyncio.run(run())
