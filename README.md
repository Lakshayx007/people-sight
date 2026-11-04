# Porter People Analytics

Two dashboards in one web app — **Employee Sentiment (eNPS)** and **Hiring** — plus a **Data Quality** page and an
**Ask the Data** panel that turns a plain-English question into one read-only SQL query, a chart and the SQL itself.
Built for the Porter People Analytics intern case study. Every number on screen comes from SQL over one DuckDB file
built by a reproducible pipeline, and every chart can show the exact SQL behind it.

- Live: **Sentiment** `https://<your-service>.onrender.com/sentiment` · **Hiring** `https://<your-service>.onrender.com/hiring`
  · Data quality `/data-quality` (each route works as a direct link)
- Repository: `https://github.com/<you>/<repo>` (add after pushing)

## Run locally (4 commands)

```bash
git clone <repo-url> && cd <repo>
./build.sh                                   # installs Python packages, rebuilds data/people.duckdb, builds the frontend
cp .env.example .env                         # optional: add GROQ_API_KEY for Ask the Data
uvicorn backend.main:app --port 8000         # open http://localhost:8000
```

Needs Python 3.11+ and Node 20.19+ (22 recommended). On Windows run `build.sh` from Git Bash, or run its six lines one by
one. Without a Groq key everything works except Ask the Data, which says it needs a key.

Development: `uvicorn backend.main:app --reload --port 8000` and `cd frontend && npm run dev` (Vite proxies `/api`).

Tests: `pytest tests` (cleaning, metrics vs independent pandas, every API endpoint with random filters,
Ask the Data guard / validator, hardening, insights). The insights tests need `pip install -r requirements-analysis.txt`
and are skipped otherwise.

## What is where

| Path | What |
|---|---|
| `data/raw/` | The two workbooks as received — never modified |
| `pipeline/` | `01_profile.py` → `analysis/profile.md`; `02_clean_enps.py`, `03_clean_recruitment.py` → `data/clean/*.parquet` + `dq_log.csv`; `04_build_db.py` → `data/people.duckdb`; `check_metrics.py` → `analysis/metric_reference.md`; `05_insights.py` → `analysis/insights.md`, charts, DQ note |
| `backend/` | FastAPI: `filters.py` (the only filter → SQL code), `metrics_enps.py` / `metrics_hiring.py` (one function per metric, returns SQL), `db.py` (read-only DuckDB), `ask.py` + `ai_service.py` (Ask the Data) |
| `frontend/` | React 19 + Vite + Tailwind v4 + ECharts: pages Sentiment, Hiring, Data Quality; Ask panel |
| `tests/` | pytest suites (see above) |
| `analysis/` | profile, metric reference, hypotheses, insights, deck charts, DQ note, Ask-the-Data test log, screenshots |
| `scripts/` | screenshots, UI checks, Ask-the-Data evaluation, submission pack builder |
| `render.yaml`, `build.sh` | One Render web service: build = `build.sh`, start = uvicorn |

## Architecture

```
data/raw/*.xlsx ──► pipeline (pandas) ──► data/clean/*.parquet + dq_log.csv ──► 04_build_db ──► people.duckdb
                                                                                     │  t_* tables, v_* views
                                                                                     ▼  (COMMENT on every column)
React (URL = filter state) ──POST /api/...──► FastAPI ──► filters.build_where ──► metrics_*.py SQL ──► DuckDB (read-only)
        ▲                                         │
        └──────── {data, sql, n} ◄────────────────┘     Ask the Data: question guard → Groq (SQL + chart spec only)
                                                          → sqlglot validator → filter CTEs → read-only run → n<5 suppression
```

- **One source of truth for filters.** The URL holds the filter state; `backend/filters.py` turns it into one
  parameterised WHERE clause used by every endpoint. React does no filtering and no metric maths.
- **Every response is `{data, sql, n}`.** The SQL starts with a `-- params:` comment and is exactly what ran.
- **Anonymity.** Survey views hold no names or employee IDs (a salted respondent key links the two waves); every slicing
  attribute is precomputed on the survey rows. Groups under 5 respondents show "n<5". Names exist only in
  `v_interviewers`, used on the Hiring page; any query mixing names with survey data is refused.
- **Ask the Data.** Groq (`GROQ_MODEL`, default `openai/gpt-oss-120b`) only writes SQL and a chart spec; it never sees
  results and never produces numbers. Guard → validate (one SELECT, `v_*` views only, no file / system functions) →
  5-second read-only run → suppression. Evidence: `analysis/ask_the_data_tests.md`.
- **Hardening.** gzip; immutable caching for hashed assets, no-cache for `index.html`; `nosniff` / frame / referrer
  headers; 256 KB request cap; per-IP limit on the two Groq endpoints (`AI_RATE_PER_MIN`, default 10/min); no CORS
  unless `CORS_ORIGINS` is set (the app is same-origin).

## Metric definitions

- **eNPS** (Q1, 0-10) = % promoters (9-10) − % detractors (0-6), one decimal. Passives = 7-8.
- **Response rate** = valid respondents ÷ employees active on the wave open date (same segment). Waves: April
  (06–17 Apr 2026, invited = active on 06-Apr) and October (05–16 Oct 2026, active on 05-Oct).
- **Drivers Q2–Q6** (1-5): mean and % favourable (4-5): manager feedback, fair pay, workload, onboarding/tools, growth path.
- **Panel view**: people who answered both waves. **Wave change** = October − April.
- **Compa-ratio** = annual CTC ÷ band mid for (job family, grade), 2026-04-01 band set; below < 0.90 ≤ at ≤ 1.10 < above.
- **manager_status**: *Changed manager* = Manager Effective From between 18-Apr and 04-Oct-2026 and after joining;
  *New joiner (first manager)* = in that window and equal to the joining date; *Same manager* = everyone else.
- **Time to fill** = hired candidate's offer response date − req raised date. Hired = offer accepted and not backed out.
- **SLA**: 30 days (up to G2), 45 (G3–G5), 60 (G6+). Met = TTF ≤ SLA. Open reqs breached if age on 31-Oct-2026 > SLA.
  Recomputed status is used; the ATS status is compared and its mismatches reported.
- **Offer acceptance** = accepted ÷ (accepted + declined). **Joining rate** = joined ÷ accepted with expected DOJ ≤ 31-Oct.
- **R1 feedback turnaround** = feedback submitted − R1 interview date. **Agency fee** = 8.33% × offered CTC, joiners only.
- **Recruiter attainment** = accepted offers per month ÷ monthly target, in two versions (all accepted / excluding
  backed-out), shown next to a per-req fair comparison because attainment depends on how many reqs a recruiter holds.

Reference values for all of these (with n) are in `analysis/metric_reference.md`, regenerated by `pipeline/check_metrics.py`.

## Cleaning steps

Every rule writes a row to `data/clean/dq_log.csv` (dataset, sheet, column, issue, rows affected, treatment,
assumption); row counts in → out per sheet are in `data/clean/reconciliation.csv`. Both are on the Data Quality page and
summarised in `analysis/dq_note.md`.

1. **IDs**: trim, upper-case, add missing `REQ_` prefixes; drop exact duplicate rows; for the same employee ID with
   different values keep the latest record.
2. **Categoricals**: map spelling / case variants of thread, grade, location, status, source, wave and candidate status
   to one canonical list (only spelling variants are merged).
3. **Dates**: parse mixed formats day-first, including Excel serials; flag impossible orders.
4. **Money and text numbers**: Indian-comma and "LPA / lakh" strings to rupees; notice periods to days; monthly CTC
   values entered as annual are multiplied by 12 and flagged.
5. **Status fixes**: "Active" with an exit date → Exited; Exited without a date → treated as left before October.
6. **Survey**: drop test IDs, IDs not in the master, superseded duplicates, people not active on the wave open date;
   Q1 blank or outside 0-10 makes the response invalid for all metrics.
7. **Recruitment**: candidates whose requisition is not in the extract are excluded (kept in a separate file);
   backed-out candidates are not hires; SLA status is recomputed from dates.

## Assumptions (main ones)

- HRMS keeps only current attributes and the current manager, so survey segments use current thread / function /
  grade / location; tenure band is computed at each wave's open date.
- Manager Effective From equal to the joining date = first manager, not a change.
- Q1 blank or out of range → response invalid for every survey metric (one base n per wave).
- Source filter on the Hiring page: openings = openings with at least one applicant from the source; filled and TTF =
  openings filled by a hire from that source.
- Agency fees apply to joiners only. Recruiter attainment is shown in two versions over the seven months Apr–Oct 2026.
- All joins use Employee ID — HRMS contains duplicate names.
- The data are synthetic; the as-of date is 31-Oct-2026.

## Deploy (Render)

`render.yaml` defines one free web service: build `./build.sh`, start
`uvicorn backend.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips "*"`, health check
`/api/health`. Set `GROQ_API_KEY` in the Render dashboard (it is never committed); `GROQ_MODEL`, `GROQ_CACHE_TTL` and
`AI_RATE_PER_MIN` have defaults in the blueprint.
