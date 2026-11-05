"""
main.py
-------
FastAPI app for Porter People Analytics (pattern adapted from Onco-Sight: lifespan, CORS, global exception
handler, built frontend served with an SPA fallback so /sentiment, /hiring and /data-quality work as direct links).

Every API response is {"data": [...], "sql": "<exact SQL run>", "n": <base count>}.
The "sql" text starts with a "-- params: {...}" comment holding the parameter values; that full text is what ran.

Run locally:  uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import ai_service, ask, db, narrative
from backend import metrics_enps as E
from backend import metrics_hiring as H
from backend.filters import FilterError, build_where

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger("people.main")

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    log.info("DuckDB opened read-only: %s", db.DB_PATH)
    yield
    db.close()


app = FastAPI(title="Porter People Analytics API", version="1.0.0", lifespan=lifespan)

# ── hardening ────────────────────────────────────────────────────────────────
# The built frontend is served by this same app, so production needs no CORS. Set CORS_ORIGINS (comma-separated) only
# if the frontend is hosted elsewhere.
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)

MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(256 * 1024)))
AI_RATE_PER_MIN = int(os.getenv("AI_RATE_PER_MIN", "10"))     # per client IP, for the two Groq-backed endpoints
AI_PATHS = {"/api/ask", "/api/chart-insight"}
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def rate_limited(key: str, limit: int, window: float = 60.0) -> bool:
    """Sliding-window limiter (in memory; one Render instance). True when the call should be refused."""
    now = time.monotonic()
    with _hits_lock:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return True
        q.append(now)
        return False


@app.middleware("http")
async def guard_and_headers(request: Request, call_next):
    if request.method == "POST":
        try:
            size = int(request.headers.get("content-length", "0"))
        except ValueError:
            size = 0
        if size > MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Request too large."})
        if request.url.path in AI_PATHS and rate_limited(f"{_client_ip(request)}|ai", AI_RATE_PER_MIN):
            return JSONResponse(status_code=429, content={
                "detail": "Too many AI requests from this browser. Please wait a minute and try again."})
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"   # hashed file names
    elif not path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"                               # index.html: always fresh
    else:
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(FilterError)
@app.exception_handler(ValueError)
async def bad_request(request: Request, exc: Exception):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class Body(BaseModel):
    filters: dict[str, Any] = Field(default_factory=dict)


def respond(metric: tuple[str, dict], n_sql: str, n_params: dict, endpoint: str | None = None,
            ctx: dict | None = None) -> dict:
    """{data, sql, n} plus `takeaway`: one plain-language sentence written by code from the same rows (or null)."""
    sql, params = metric
    full = db.annotate(sql, params)
    data = db.query(full, params)
    return {"data": data, "sql": full, "n": db.scalar(n_sql, n_params),
            "takeaway": narrative.takeaway(endpoint, data, ctx) if endpoint else None}


def run(metric: tuple[str, dict]) -> tuple[list[dict], str]:
    sql, params = metric
    full = db.annotate(sql, params)
    return db.query(full, params), full


# ── base counts (n) ──────────────────────────────────────────────────────────

def survey_n(w, extra: str = "", extra_params: dict | None = None):
    return f"SELECT count(*) FROM v_survey WHERE {w[0]}{extra}", {**w[1], **(extra_params or {})}


def req_n(wr, extra: str = ""):
    return f"SELECT count(*) FROM v_requisitions WHERE {wr[0]}{extra}", wr[1]


def cand_n(wc, extra: str = ""):
    return f"SELECT count(*) FROM v_candidates WHERE {wc[0]}{extra}", wc[1]


# ── Employee Sentiment ───────────────────────────────────────────────────────

def _w(body: Body):
    return build_where(body.filters, "survey")


@app.post("/api/enps/kpis")
def enps_kpis(body: Body = Body()):
    w = _w(body)
    return respond(E.kpis(w), *survey_n(w))


@app.post("/api/enps/by-wave")
def enps_by_wave(body: Body = Body()):
    w = _w(body)
    return respond(E.by_wave(w), *survey_n(w), endpoint="enps/by-wave")


@app.post("/api/enps/panel")
def enps_panel(body: Body = Body()):
    w = _w(body)
    return respond(E.panel(w), *survey_n(w, " AND responded_both_waves"))


@app.post("/api/enps/segment")
def enps_segment(body: Body = Body(), dim: str = Query("thread")):
    w = _w(body)
    return respond(E.segment(dim, w), *survey_n(w), endpoint="enps/segment", ctx={"dim": dim})


@app.post("/api/enps/drivers")
def enps_drivers(body: Body = Body()):
    w = _w(body)
    return respond(E.drivers(w), *survey_n(w), endpoint="enps/drivers")


@app.post("/api/enps/driver-importance")
def enps_driver_importance(body: Body = Body(), wave: str = Query("Oct", pattern="^(Apr|Oct)$")):
    w = _w(body)
    return respond(E.driver_importance(w, wave), *survey_n(w, " AND wave = $n_wave", {"n_wave": wave}),
                   endpoint="enps/driver-importance")


@app.post("/api/enps/heatmap")
def enps_heatmap(body: Body = Body(), row: str = Query("thread"), col: str = Query("function"),
                 wave: str = Query("Oct", pattern="^(Apr|Oct)$")):
    w = _w(body)
    return respond(E.heatmap(row, col, w, wave), *survey_n(w, " AND wave = $n_wave", {"n_wave": wave}),
                   endpoint="enps/heatmap")


@app.post("/api/enps/themes")
def enps_themes(body: Body = Body()):
    w = _w(body)
    return respond(E.themes(w), *survey_n(w), endpoint="enps/themes")


@app.post("/api/enps/respondents-who-exited")
def enps_respondents_who_exited(body: Body = Body()):
    w = _w(body)
    return respond(E.respondents_who_exited(w), *survey_n(w, " AND wave = 'Apr'"), endpoint="enps/respondents-who-exited")


@app.post("/api/enps/non-response-bias")
def enps_non_response_bias(body: Body = Body(), dim: str | None = Query(None)):
    w = _w(body)
    return respond(E.non_response_bias(dim, w), *survey_n(w, " AND wave = 'Apr' AND invited_both_waves"),
                   endpoint="enps/non-response-bias" if dim else None)


# ── Hiring ───────────────────────────────────────────────────────────────────

def _h(body: Body):
    return build_where(body.filters, "requisitions"), build_where(body.filters, "candidates")


def _hiring_route(path: str, fn: Callable, base: str, extra: str = ""):
    def handler(body: Body = Body()):
        wr, wc = _h(body)
        n_sql, n_params = req_n(wr, extra) if base == "req" else cand_n(wc, extra)
        return respond(fn(wr, wc), n_sql, n_params, endpoint=f"hiring/{path}")
    handler.__name__ = "hiring_" + path.strip("/").replace("-", "_")
    handler.__doc__ = fn.__doc__
    app.post(f"/api/hiring/{path}")(handler)


for _path, _fn, _base, _extra in [
    ("kpis", H.kpis, "req", ""), ("monthly", H.monthly, "req", ""), ("funnel", H.funnel, "cand", ""),
    ("stage-time", H.stage_time, "cand", " AND NOT stage_dates_invalid"), ("source", H.source, "cand", ""),
    ("recruiters", H.recruiters, "req", ""), ("recruiter-comparison", H.recruiter_comparison, "req", ""), ("interviewers", H.interviewers, "cand", " AND r1_feedback_days IS NOT NULL"),
    ("ttf-by-grade", H.ttf_by_grade, "req", ""), ("open-aging", H.open_aging, "req", " AND is_open"),
    ("open-aging-buckets", H.open_aging_buckets, "req", " AND is_open"),
    ("offers", H.offers, "cand", " AND (is_offer_accepted OR is_offer_declined)"),
    ("offers-summary", H.offers_summary, "cand", " AND (is_offer_accepted OR is_offer_declined)"),
    ("sla-mismatch", H.sla_mismatch, "req", ""), ("sla-mismatch-list", H.sla_mismatch_list, "req", ""),
    ("backfill", H.backfill, "req", ""),
]:
    _hiring_route(_path, _fn, _base, _extra)


# ── Plain-language summaries ─────────────────────────────────────────────────
TAKEAWAY_DIMS = ["manager_status", "thread", "tenure_band", "function"]


def _enps_page(w) -> tuple[list[dict], str]:
    k, s1 = run(E.kpis(w))
    pn, s2 = run(E.panel(w))
    segs, sqls = {}, [s1, s2]
    for d in TAKEAWAY_DIMS:
        segs[d], sq = run(E.segment(d, w))
        sqls.append(sq)
    dr, s3 = run(E.drivers(w))
    sqls.append(s3)
    return narrative.page_takeaways_enps(k[0] if k else {}, pn[0] if pn else {}, segs, dr), ";\n\n".join(sqls)


def _hiring_page(wr, wc) -> tuple[list[dict], str]:
    k, s1 = run(H.kpis(wr, wc))
    g, s2 = run(H.ttf_by_grade(wr, wc))
    o, s3 = run(H.offers(wr, wc))
    i, s4 = run(H.interviewers(wr, wc))
    return narrative.page_takeaways_hiring(k[0] if k else {}, g, o, i), ";\n\n".join([s1, s2, s3, s4])


@app.post("/api/enps/takeaways")
def enps_takeaways(body: Body = Body()):
    """Three plain-language headline bullets for the Sentiment page (written by code from the metric SQL)."""
    w = _w(body)
    data, sql = _enps_page(w)
    return {"data": data, "sql": sql, "n": db.scalar(*survey_n(w))}


@app.post("/api/hiring/takeaways")
def hiring_takeaways(body: Body = Body()):
    """Three plain-language headline bullets for the Hiring page."""
    wr, wc = _h(body)
    data, sql = _hiring_page(wr, wc)
    return {"data": data, "sql": sql, "n": db.scalar(*req_n(wr))}


@app.get("/api/home")
def home():
    """Headline numbers and plain-language findings for the landing page (unfiltered)."""
    from backend.sql_common import ALL
    k, s1 = run(E.kpis(ALL))
    pn, s2 = run(E.panel(ALL))
    hk, s3 = run(H.kpis(ALL, ALL))
    enps_cards, s4 = _enps_page(ALL)
    hire_cards, s5 = _hiring_page(ALL, ALL)
    dq_sql = ("SELECT count(*) AS rules, count(*) FILTER (WHERE rows_affected > 0 AND treatment <> 'Validated') "
              "AS issues_treated FROM v_dq_log")
    dq = db.query(dq_sql)[0]
    row = {**(k[0] if k else {}), "panel_n": (pn[0] if pn else {}).get("n"),
           "panel_change": (pn[0] if pn else {}).get("enps_change"),
           **{f"h_{key}": v for key, v in (hk[0] if hk else {}).items()}, **dq,
           "findings": [dict(c, area="Sentiment") for c in enps_cards[1:]] + [dict(c, area="Hiring") for c in hire_cards[1:]]}
    return {"data": [row], "sql": ";\n\n".join([s1, s2, s3, s4, s5, dq_sql]), "n": row.get("n")}


# ── Ask the Data ─────────────────────────────────────────────────────────────

class AskBody(BaseModel):
    question: str = Field(..., max_length=2000)
    dataset: str = Field("all", pattern="^(enps|hiring|all)$")
    filters: dict[str, Any] = Field(default_factory=dict)
    apply_filters: bool = False


@app.post("/api/ask")
def ask_the_data(body: AskBody):
    """Plain English -> one validated read-only SELECT on the v_* views. Superset of the {data, sql, n} contract:
    data = result rows, plus columns, chart_spec, explanation, and refused / unavailable / error with a message."""
    return ask.answer(body.question, body.dataset, body.filters, body.apply_filters)


@app.get("/api/ask/status")
def ask_status():
    return {"data": [{"available": ai_service.available(), "model": ai_service.model_name(),
                      "suggestions": ask.SUGGESTIONS}], "sql": "", "n": 1}


class InsightBody(BaseModel):
    title: str = Field(..., max_length=200)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    context: str = Field("", max_length=1200)   # the panel subtitle + plain-language takeaway


@app.post("/api/chart-insight")
def chart_insight(body: InsightBody):
    """Two-sentence blurb written by Groq only from the rows the panel already shows (Hard rule 9)."""
    return {"data": [{"insight": ai_service.chart_blurb(body.title, body.rows, body.context)}], "sql": "",
            "n": len(body.rows)}


# ── filter options, data quality, health ─────────────────────────────────────

OPTIONS_SQL = """
SELECT 'enps' AS dashboard, key, value, min(sort_key) AS sort_key FROM (
    SELECT 'wave' AS key, wave AS value, CASE wave WHEN 'Apr' THEN 1 ELSE 2 END AS sort_key FROM v_invited
    UNION ALL SELECT 'thread', thread, 0 FROM v_invited
    UNION ALL SELECT 'function', function, 0 FROM v_invited
    UNION ALL SELECT 'job_family', job_family, 0 FROM v_invited
    UNION ALL SELECT 'grade', grade, grade_num FROM v_invited
    UNION ALL SELECT 'location', location, 0 FROM v_invited
    UNION ALL SELECT 'location_type', location_type, 0 FROM v_invited
    UNION ALL SELECT 'company', company, 0 FROM v_invited
    UNION ALL SELECT 'tenure_band', tenure_band, CASE tenure_band WHEN '<6m' THEN 1 WHEN '6-12m' THEN 2 WHEN '1-2y' THEN 3 WHEN '2-4y' THEN 4 ELSE 5 END FROM v_invited
    UNION ALL SELECT 'performance_rating', performance_rating, CASE performance_rating WHEN 'Game Changer' THEN 1 WHEN 'High Impact Player' THEN 2 WHEN 'Solid Performer' THEN 3 WHEN 'Needs Improvement' THEN 4 WHEN 'Below Expectations' THEN 5 ELSE 6 END FROM v_invited
    UNION ALL SELECT 'compa_band', compa_band, CASE compa_band WHEN 'Below' THEN 1 WHEN 'At' THEN 2 WHEN 'Above' THEN 3 ELSE 4 END FROM v_invited
    UNION ALL SELECT 'manager_status', manager_status, CASE manager_status WHEN 'Same manager' THEN 1 WHEN 'Changed manager' THEN 2 ELSE 3 END FROM v_invited
) GROUP BY ALL
UNION ALL
SELECT 'hiring', key, value, min(sort_key) FROM (
    SELECT 'thread' AS key, thread AS value, 0 AS sort_key FROM v_requisitions
    UNION ALL SELECT 'function', function, 0 FROM v_requisitions
    UNION ALL SELECT 'grade', grade, grade_num FROM v_requisitions
    UNION ALL SELECT 'location', location, 0 FROM v_requisitions
    UNION ALL SELECT 'recruiter', recruiter, 0 FROM v_requisitions
    UNION ALL SELECT 'source', source, 0 FROM v_candidates
    UNION ALL SELECT 'position_type', position_type, 0 FROM v_requisitions
    UNION ALL SELECT 'criticality', criticality, 0 FROM v_requisitions
    UNION ALL SELECT 'req_status', req_status, CASE req_status WHEN 'Open' THEN 1 WHEN 'Offer Accepted' THEN 2 WHEN 'Closed - Joined' THEN 3 WHEN 'On Hold' THEN 4 ELSE 5 END FROM v_requisitions
    UNION ALL SELECT 'raised_month', raised_month, 0 FROM v_requisitions
) GROUP BY ALL
ORDER BY dashboard, key, sort_key, value"""


@app.get("/api/filters/options")
def filter_options():
    rows = db.query(OPTIONS_SQL)
    grouped: dict[tuple, list] = {}
    for r in rows:
        if r["value"] is not None:
            grouped.setdefault((r["dashboard"], r["key"]), []).append(r["value"])
    data = [{"dashboard": d, "key": k, "values": v} for (d, k), v in grouped.items()]
    return {"data": data, "sql": OPTIONS_SQL.strip(), "n": len(data)}


DQ_DATASET = Query(None, pattern="^(eNPS|Recruitment)$")


def _dq_where(dataset):
    return ("dataset = $dataset", {"dataset": dataset}) if dataset else ("TRUE", {})


@app.get("/api/dq")
def dq_log(dataset: str | None = DQ_DATASET):
    where, params = _dq_where(dataset)
    sql = (f"SELECT *, rows_affected > 0 AND treatment <> 'Validated' AS changed_data FROM v_dq_log WHERE {where} "
           "ORDER BY dataset, sheet, rows_affected DESC")
    full = db.annotate(sql, params)
    return {"data": db.query(full, params), "sql": full, "n": db.scalar(f"SELECT count(*) FROM v_dq_log WHERE {where}", params)}


@app.get("/api/dq/summary")
def dq_summary(dataset: str | None = DQ_DATASET):
    where, params = _dq_where(dataset)
    sql = f"""SELECT (SELECT count(*) FROM v_dq_log WHERE {where}) AS rules,
       (SELECT count(*) FROM v_dq_log WHERE {where} AND rows_affected > 0 AND treatment <> 'Validated') AS issues_treated,
       (SELECT count(*) FROM v_dq_log WHERE {where} AND rows_affected = 0) AS checks_passed,
       (SELECT count(DISTINCT dataset || '/' || sheet) FROM v_reconciliation WHERE {where}) AS sheets_reconciled"""
    full = db.annotate(sql, params)
    data = db.query(full, params)
    return {"data": data, "sql": full, "n": data[0]["rules"]}


@app.get("/api/dq/stories")
def dq_stories(dataset: str | None = DQ_DATASET):
    """The cleaning log grouped into a few plain-language cards (counts summed from v_dq_log)."""
    where, params = _dq_where(dataset)
    sql = f"SELECT dataset, sheet, \"column\", issue, rows_affected, treatment FROM v_dq_log WHERE {where}"
    full = db.annotate(sql, params)
    rows = db.query(full, params)
    return {"data": narrative.dq_stories(rows), "sql": full, "n": len(rows)}


@app.get("/api/dq/reconciliation")
def dq_reconciliation(dataset: str | None = DQ_DATASET):
    where, params = _dq_where(dataset)
    sql = f'SELECT * FROM v_reconciliation WHERE {where} ORDER BY dataset, sheet, "order"'
    full = db.annotate(sql, params)
    return {"data": db.query(full, params), "sql": full, "n": db.scalar(f"SELECT count(*) FROM v_reconciliation WHERE {where}", params)}


@app.get("/api/health")
def health():
    sql = "SELECT (SELECT count(*) FROM v_survey) AS survey_rows, (SELECT count(*) FROM v_requisitions) AS requisitions"
    return {"data": [{"status": "ok", **db.query(sql)[0]}], "sql": sql, "n": 1}


# ── frontend (built Vite app) ────────────────────────────────────────────────

if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.startswith("api/") or full_path == "api":
        return JSONResponse({"detail": "Not found"}, status_code=404)
    file = DIST / full_path
    if full_path and file.is_file() and DIST in file.resolve().parents:
        return FileResponse(str(file))
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"detail": "Frontend not built yet. Run: cd frontend && npm run build"}, status_code=404)
