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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import db
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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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


def respond(metric: tuple[str, dict], n_sql: str, n_params: dict) -> dict:
    sql, params = metric
    full = db.annotate(sql, params)
    return {"data": db.query(full, params), "sql": full, "n": db.scalar(n_sql, n_params)}


# ── base counts (n) ──────────────────────────────────────────────────────────

def survey_n(w, extra: str = "", extra_params: dict | None = None):
    return f"SELECT count(*) FROM v_survey WHERE {w[0]}{extra}", {**w[1], **(extra_params or {})}


def req_n(wr):
    return f"SELECT count(*) FROM v_requisitions WHERE {wr[0]}", wr[1]


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
    return respond(E.by_wave(w), *survey_n(w))


@app.post("/api/enps/panel")
def enps_panel(body: Body = Body()):
    w = _w(body)
    return respond(E.panel(w), *survey_n(w, " AND responded_both_waves"))


@app.post("/api/enps/segment")
def enps_segment(body: Body = Body(), dim: str = Query("thread")):
    w = _w(body)
    return respond(E.segment(dim, w), *survey_n(w))


@app.post("/api/enps/drivers")
def enps_drivers(body: Body = Body()):
    w = _w(body)
    return respond(E.drivers(w), *survey_n(w))


@app.post("/api/enps/driver-importance")
def enps_driver_importance(body: Body = Body(), wave: str = Query("Oct", pattern="^(Apr|Oct)$")):
    w = _w(body)
    return respond(E.driver_importance(w, wave), *survey_n(w, " AND wave = $n_wave", {"n_wave": wave}))


@app.post("/api/enps/heatmap")
def enps_heatmap(body: Body = Body(), row: str = Query("thread"), col: str = Query("function"),
                 wave: str = Query("Oct", pattern="^(Apr|Oct)$")):
    w = _w(body)
    return respond(E.heatmap(row, col, w, wave), *survey_n(w, " AND wave = $n_wave", {"n_wave": wave}))


@app.post("/api/enps/themes")
def enps_themes(body: Body = Body()):
    w = _w(body)
    return respond(E.themes(w), *survey_n(w))


@app.post("/api/enps/respondents-who-exited")
def enps_respondents_who_exited(body: Body = Body()):
    w = _w(body)
    return respond(E.respondents_who_exited(w), *survey_n(w, " AND wave = 'Apr'"))


@app.post("/api/enps/non-response-bias")
def enps_non_response_bias(body: Body = Body(), dim: str | None = Query(None)):
    w = _w(body)
    return respond(E.non_response_bias(dim, w), *survey_n(w, " AND wave = 'Apr' AND invited_both_waves"))


# ── Hiring ───────────────────────────────────────────────────────────────────

def _h(body: Body):
    return build_where(body.filters, "requisitions"), build_where(body.filters, "candidates")


def _hiring_route(path: str, fn: Callable, base: str, extra: str = ""):
    def handler(body: Body = Body()):
        wr, wc = _h(body)
        n_sql, n_params = req_n(wr) if base == "req" else cand_n(wc, extra)
        return respond(fn(wr, wc), n_sql, n_params)
    handler.__name__ = "hiring_" + path.strip("/").replace("-", "_")
    handler.__doc__ = fn.__doc__
    app.post(f"/api/hiring/{path}")(handler)


for _path, _fn, _base, _extra in [
    ("kpis", H.kpis, "req", ""), ("monthly", H.monthly, "req", ""), ("funnel", H.funnel, "cand", ""),
    ("stage-time", H.stage_time, "cand", " AND NOT stage_dates_invalid"), ("source", H.source, "cand", ""),
    ("recruiters", H.recruiters, "req", ""), ("interviewers", H.interviewers, "cand", " AND r1_feedback_days IS NOT NULL"),
    ("ttf-by-grade", H.ttf_by_grade, "req", ""), ("open-aging", H.open_aging, "req", ""),
    ("open-aging-buckets", H.open_aging_buckets, "req", ""),
    ("offers", H.offers, "cand", " AND (is_offer_accepted OR is_offer_declined)"),
    ("offers-summary", H.offers_summary, "cand", " AND (is_offer_accepted OR is_offer_declined)"),
    ("sla-mismatch", H.sla_mismatch, "req", ""), ("sla-mismatch-list", H.sla_mismatch_list, "req", ""),
    ("backfill", H.backfill, "req", ""),
]:
    _hiring_route(_path, _fn, _base, _extra)


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


@app.get("/api/dq")
def dq_log():
    sql = "SELECT * FROM v_dq_log ORDER BY dataset, sheet, rows_affected DESC"
    return {"data": db.query(sql), "sql": sql, "n": db.scalar("SELECT count(*) FROM v_dq_log")}


@app.get("/api/dq/reconciliation")
def dq_reconciliation():
    sql = 'SELECT * FROM v_reconciliation ORDER BY dataset, sheet, "order"'
    return {"data": db.query(sql), "sql": sql, "n": db.scalar("SELECT count(*) FROM v_reconciliation")}


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
