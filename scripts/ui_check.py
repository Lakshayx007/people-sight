"""
ui_check.py — clicks through the Sentiment page: heatmap drill-down, breadcrumb reset, wave drill-down,
chip removal, Show SQL, KPI card under filters, dark theme, and direct links /hiring /data-quality / /x.
Usage (app running on :8000):  python scripts/ui_check.py
"""
import asyncio
from playwright.async_api import async_playwright
B="http://localhost:8000"
CLICK_JS = """([title, series, idx]) => {
  const h = [...document.querySelectorAll('h3')].find(e => e.textContent.startsWith(title));
  const dom = h.closest('section').querySelector('div[_echarts_instance_]'); dom.scrollIntoView({block:'center'});
  const inst = dom.__chart; const s = inst.getOption().series[series]; const d = s.data[idx];
  const v = Array.isArray(d) ? d : (d.value ?? d);
  const px = inst.convertToPixel({seriesIndex: series}, Array.isArray(v) ? v : [v, idx]);
  const r = dom.getBoundingClientRect(); return {x: r.left + px[0], y: r.top + px[1]};
}"""
SCROLL_JS = """(title) => { const h = [...document.querySelectorAll('h3')].find(e => e.textContent.startsWith(title));
  h.closest('section').scrollIntoView({block:'center'}); }"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width":1366,"height":900})
        errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
        async def idle(): await pg.wait_for_load_state("networkidle"); await pg.wait_for_timeout(900)
        await pg.goto(B+"/sentiment"); await idle()
        # heatmap cell click (series 0, first non-suppressed cell)
        await pg.evaluate(SCROLL_JS, "eNPS by thread × function"); await pg.wait_for_timeout(900)
        xy = await pg.evaluate(CLICK_JS, ["eNPS by thread × function", 0, 0]); await pg.mouse.click(xy["x"], xy["y"]); await idle()
        print("heatmap drill ->", pg.url.split("?")[1])
        # breadcrumb: back to all employees
        await pg.get_by_role("button", name="All employees").click(); await idle(); print("breadcrumb reset ->", pg.url)
        # mix chart: click October bar (promoters series index 2, data index 1)
        await pg.evaluate(SCROLL_JS, "Promoters, passives"); await pg.wait_for_timeout(900)
        xy = await pg.evaluate(CLICK_JS, ["Promoters, passives", 2, 1]); await pg.mouse.click(xy["x"]-20, xy["y"]); await idle()
        print("mix drill ->", pg.url.split("?")[1] if "?" in pg.url else pg.url)
        # chip remove
        await pg.locator("button[aria-label^='Remove']").first.click(); await idle(); print("chip removed ->", pg.url)
        # filter via dropdown + Show SQL
        await pg.goto(B+"/sentiment?thread=Intercity&manager_status=Changed+manager"); await idle()
        await pg.get_by_role('button', name='SQL').first.click()
        sql = await pg.locator("pre.sql").first.inner_text(); print("SQL shown:", sql.splitlines()[0][:110])
        kp = await pg.locator("text=eNPS · Oct").locator("xpath=../..").inner_text(); print("KPI card:", kp.replace("\n"," | "))
        # dark theme
        await pg.get_by_role("button", name="Dark theme").click(); await pg.wait_for_timeout(800)
        await pg.evaluate("window.scrollTo(0,0)"); pass
        for path in ["/hiring", "/data-quality", "/", "/nonexistent"]:
            r = await pg.goto(B+path); await idle(); print(path, r.status, "->", pg.url.replace(B, ""))
        print("page errors:", errs or "none")
        await b.close()
asyncio.run(main())
