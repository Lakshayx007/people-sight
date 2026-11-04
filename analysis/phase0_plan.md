# Phase 0 — Orientation, reuse plan and build plan

Date: 04-Nov-2026. No feature code in this phase.

## 1. Environment check

| Item | Status |
|---|---|
| `data/raw/eNPS_Data.xlsx` | Present (byte-identical copy of `eNPS Data.xlsx`) |
| `data/raw/Recruitment_Data.xlsx` | Present (byte-identical copy of `Case_Recruitment_Data.xlsx`) |
| `.env` with `GROQ_API_KEY` | **Missing.** `.env.example` created. Needed from Phase 8 (Ask the Data). Dashboards do not need it. |
| `reference/Onco-Sight` | Cloned (depth 1), read-only, git-ignored |
| Python 3.10.12, git 2.34, Node 22, npm 10 | Present |
| pandas, openpyxl, python-pptx, matplotlib | Installed |
| duckdb, fastapi, uvicorn, sqlglot, pytest, scipy, groq, pyarrow | Not installed yet — install at the start of Phase 1 |

## 2. Every sheet and column

### `data/raw/eNPS_Data.xlsx`

| Sheet | Rows | Columns |
|---|---:|---|
| README | — | free-text notes (not tabular) |
| Employee_Master | 1,322 | `Employee ID`, `Employee Name`, `Company`, `Thread`, `Function`, `Designation`, `Grade`, `Location`, `Location Type`, `Date of Joining`, `Reporting Manager ID`, `Manager Effective From`, `Performance Rating FY25-26`, `Annual CTC (INR)`, `Employment Status`, `Date of Exit`, `Exit Type`, `Exit Classification`, `Record Updated On` |
| eNPS_Responses | 1,726 | `Response ID`, `Employee ID`, `Survey Wave`, `Submitted On`, `Q1. How likely are you to recommend Porter as a place to work? (0-10)`, `Q2. My manager gives me regular, useful feedback (1-5)`, `Q3. I am paid fairly for the work I do (1-5)`, `Q4. My workload is manageable (1-5)`, `Q5. I had the onboarding, tools and training I needed (1-5)`, `Q6. I can see a clear growth path for myself at Porter (1-5)`, `Comments (optional)` |
| Pay_Bands | 44 | `Effective From`, `Job Family`, `Grade`, `Band Min (INR)`, `Band Mid (INR)`, `Band Max (INR)` |
| Data_Dictionary | — | free-text notes (not tabular) |

### `data/raw/Recruitment_Data.xlsx`

| Sheet | Rows | Columns |
|---|---:|---|
| Readme | — | free-text notes (not tabular) |
| Requisitions | 300 | `Req ID`, `Req Raised On`, `Thread`, `Function`, `Designation`, `Grade`, `Location`, `Position Type`, `Replaced Employee ID`, `Criticality`, `Hiring Manager ID`, `Recruiter`, `SLA (Days)`, `Req Status`, `Budgeted Max CTC (INR)`, `SLA Status (System)` |
| Candidates | 5,815 | `Candidate ID`, `Req ID`, `Source`, `Agency Name`, `Applied On`, `Shortlisted On`, `Screening Done On`, `R1 Interview Date`, `R1 Interviewer ID`, `R1 Feedback Submitted On`, `R1 Result`, `R2 Interview Date`, `R2 Result`, `Offer Released On`, `Offered CTC (INR)`, `Current CTC (INR)`, `Expected CTC (INR)`, `Notice Period (Days)`, `Offer Status`, `Offer Response On`, `Expected DOJ`, `Actual DOJ`, `Candidate Status` |
| Recruiters | 8 | `Recruiter ID`, `Recruiter Name`, `Monthly Offer Target`, `Status` |
| People_Directory | 172 | `Employee ID`, `Employee Name`, `Thread`, `Function`, `Designation`, `Grade`, `Location`, `Hiring Role` |
| Data_Dictionary | — | free-text notes (not tabular) |

## 3. Onco-Sight: reuse / adapt / drop

### Backend
| File | Decision | Why |
|---|---|---|
| `backend/main.py` | **Adapt** | Keep the pattern: `lifespan`, CORS, global exception handler, `/assets` mount, SPA fallback that serves `index.html` for any non-`/api` path (this is what makes `/sentiment` and `/hiring` work as direct links). Change: dist path is hard-coded to `frontend-v2/dist` → use `frontend/dist`; exception handler returns a full traceback to the browser → log it, return only a message; drop all oncology routes, `DataLoader`, PubMed. |
| `backend/ai_service.py` | **Adapt** | Keep `_get_client()` (returns None without a key), the in-process TTL cache (`_cache_get/_cache_set/_make_key`), `GROQ_MODEL`/`GROQ_CACHE_TTL` env vars and the graceful-fallback style. Replace the oncology prompts with (a) a JSON-mode SQL writer for Ask the Data and (b) a short chart-blurb prompt. Its chatbot prompt tells the model to answer from its own knowledge — the opposite of Hard rule 9, so it is not carried over. |
| `backend/query_engine.py` | **Drop** (keep the idea) | Filters and aggregates in pandas, per endpoint, with filter logic repeated in `apply_filters`. Replaced by `filters.py` (one parameterised WHERE builder) + `metrics_enps.py` / `metrics_hiring.py` (one function per metric returning `(sql, params)`). Keeps the "one function per chart returning JSON-ready rows" shape. |
| `backend/data_loader.py` | **Drop** | Supabase/SQLAlchemy loader. Replaced by `db.py`: DuckDB `read_only=True`, one cursor per request. |
| `pubmed_service.py`, `upload_to_supabase.py`, `temp_qe.py`, `fix_qe.py`, `debug_api.py`, `test_api.py`, `test_engine.py` | **Drop** | Oncology-specific or scratch files. |
| `backend/requirements.txt` | **Adapt** | Keep fastapi, uvicorn, pandas, numpy, python-dotenv, groq. Drop sqlalchemy, psycopg2, feedparser, requests, gunicorn, cachetools. Add duckdb, sqlglot, openpyxl, pyarrow, pytest, httpx. |

### Frontend
| File | Decision | Why |
|---|---|---|
| `src/index.css` | **Reuse** | Tailwind v4 `@theme` tokens (`--bg --surf --prim --acc --mut --bord`) + `.dark` overrides, Inter font, scrollbar, tabular-nums. Drop the print/report block. |
| `src/themes/themeConfig.js` | **Reuse** | Registers the `vintage` (light) and `dark` ECharts themes in an ESM-safe way. |
| `src/themes/dark.js`, `vintage.js` | **Drop** | UMD originals, already inlined into `themeConfig.js`. |
| `src/main.jsx` | **Reuse** | Registers themes before render. |
| `src/App.jsx` | **Adapt** | Routes become `/sentiment`, `/hiring`, `/data-quality`; `/` and unknown paths redirect to `/sentiment`. |
| `components/Sidebar.jsx` | **Adapt** | Same collapsible layout; new nav items and Porter People Analytics branding; drop Export. |
| `components/FilterBar.jsx` | **Adapt (heavily)** | Today: single-value `<select>`s with hard-coded option lists. New: one `MultiSelectDropdown` per filter, options from `/api/filters/options`, state from a global filter context synced to the URL, removable chips + Clear all. |
| `components/MultiSelectDropdown.jsx` | **Adapt** | Forces at least one item selected and labels "All Subtypes". New: empty = no filter ("All"), searchable for long lists. |
| `Panel`, `Metric` (inside `pages/Dashboard.jsx`) | **Adapt → own files** | Move to `components/Panel.jsx` / `Metric.jsx`. Add a Show SQL toggle, n badge, "n<5" suppressed state; Metric shows `—` for null. |
| `components/ChartModal.jsx` | **Reuse** | Zoom-to-fullscreen modal, as is. |
| `components/ChartInsight.jsx` | **Reuse** | AI blurb button; the blurb is written only from the panel's returned rows (Hard rule 9). |
| `components/Chatbot.jsx` | **Adapt (Phase 8)** | Becomes the slide-in Ask the Data panel: question → SQL → chart + SQL + table. |
| `pages/Dashboard.jsx` | **Adapt pattern** | Reuse the page layout (sidebar + filter bar + KPI row + 12-col panel grid), theme toggle and zoom modal for `Sentiment.jsx` and `Hiring.jsx`. Drop oncology state; wrap every `localStorage` call in try/catch (it is unguarded today); calls go to relative `/api` instead of `127.0.0.1:8001`. |
| `components/charts/*` | **Mostly drop** | Reuse the tooltip styling and the `onEvents` click pattern (`BarChart.jsx`) for drill-down; `FunnelChart.jsx` → hiring funnel; `SponsorHeatmap.jsx` → thread × function heatmap. GeoMap, AssetLandscape, Combination charts dropped. |
| `ReportView`, `Landing`, `PubMed`, `BackgroundAnimation`, `usa.json`, `world.json`, `assets/`, `public/*` | **Drop** | Oncology-specific. |
| `vite.config.js` | **Adapt** | Add dev proxy `/api → http://localhost:8000`. |
| `postcss.config.js` | **Reuse** | Tailwind v4 PostCSS plugin. |
| `tailwind.config.js` | **Drop** | Tailwind v4 reads tokens from `@theme` in CSS; this v3-style file is unused. |
| `vercel.json` | **Drop** | One Render service serves both API and frontend. |
| `package.json` | **Adapt** | Same versions (React 19, Vite 8, Tailwind 4, ECharts 6, echarts-for-react, lucide-react, axios). Keeps `react-router-dom` — needed for the three routes but not named in the Stack list (see §5). |

## 4. Build plan

All numbers come from SQL on one DuckDB file. One `filters.py` builds every WHERE clause.

```
data/raw/*.xlsx ──01_profile──► analysis/profile.md
        │
        ├─02_clean_enps────────► data/clean/employees, survey_responses, pay_bands .parquet ─┐
        ├─03_clean_recruitment─► data/clean/requisitions, candidates, recruiters, people_directory ─┤
        │        (every rule → data/clean/dq_log.csv)                                            │
        └─04_build_db──────────► data/people.duckdb  (v_employees, v_survey [no name], v_requisitions,
                                                     v_candidates, v_recruiters, v_interviewers, v_dq_log)
                                        │
backend/ FastAPI ── db.py (read_only) ── filters.py build_where(filters, dataset) ──► metrics_*.py (sql, params)
        └─ every endpoint returns {data, sql, n}; n<5 suppression in SQL; ask.py (Groq → sqlglot-validated SELECT)
frontend/ React ── FilterContext (URL-synced) ── /sentiment  /hiring  /data-quality  + Ask the Data panel
analysis/ ── check_metrics → metric_reference.md ── 05_insights → insights.md + charts ── dq_note.md ── deck
```

| Phase | Output | Checkpoint |
|---|---|---|
| 1 Profile | `pipeline/01_profile.py`, `analysis/profile.md` | every known issue appears in profile.md |
| 2 Clean eNPS | `02_clean_enps.py`, 3 parquet, dq_log, `tests/test_enps.py` | eNPS Apr and Oct with n |
| 3 Clean recruitment | `03_clean_recruitment.py`, 4 parquet, `tests/test_recruitment.py` | SLA system vs recomputed mismatch count |
| 4 DB + metrics | `04_build_db.py`, `metrics_*.py`, `check_metrics.py`, `metric_reference.md` | reference numbers reviewed |
| 5 API | FastAPI, `filters.py`, all endpoints, `tests/test_api.py` | unfiltered KPIs = metric_reference.md |
| 6 Sentiment page | shell + `/sentiment` | Intercity → function drill-down moves everything together |
| 7 Hiring + DQ pages | `/hiring`, `/data-quality` | recruiter + Agency filters reconcile |
| 8 Ask the Data | `ask.py`, slide-in panel | matches panels; unsafe and named-person questions refused |
| 9 Insights + DQ note | hypotheses, insights, charts, dq_note | keep only strong findings |
| 10 Deploy | render.yaml, README, `submission/` | live link on a phone |
| 11 Deck (optional) | pptx + number trace | ask first |

## 5. Where the case brief and the data disagree (or are silent)

Checked against the raw files. Items marked **Decision needed** await a decision.

| # | Topic | What the data shows | Proposed resolution |
|---|---|---|---|
| 1 | Workbook names/location | Files were in the project root as `eNPS Data.xlsx` and `Case_Recruitment_Data.xlsx`. | Copied unchanged to `data/raw/` under the names in the case brief. Originals left in place, git-ignored. **Resolved.** |
| 2 | Employee ID fixes ("lowercase `emp` (26 rows)") | 26 IDs need fixing, but only 5 are lowercase; 21 just have stray spaces. | Same treatment (strip + upper); correct the wording in the case brief in Phase 1. **Resolved.** |
| 3 | Status vs Date of Exit (spec says "cross-check", no treatment) | 4 rows `Active` but with an exit date (May–Sep 2026) and Exit Type + Classification filled (EMP15158, EMP28501, EMP25584, EMP16376; EMP25584 is also backfilled by a replacement req). 3 rows `Exited` with no exit date but Exit Type filled (EMP34460, EMP15885, EMP15975). | **Decision needed.** Proposed: (a) the 4 → Exited, keep their exit date (three fields agree vs one stale status); (b) the 3 → stay Exited, exit date unknown, so they count as active on both wave open dates and get no exit month. Log both. |
| 4 | Candidate Status canonical list (not defined) | 22 raw values incl. `Applied - Under Review`, `Shortlisted`, `Screening Cleared`, `R1 Cleared`, `R1 Feedback Pending`, `Offer In Approval`, `On Hold - Position Filled`, `Withdrawn`, `Not Joined - Backed Out`. | **Decision needed.** Proposed 16: Applied - Under Review, Shortlisted, Screening Cleared, R1 Cleared, R1 Feedback Pending, Offer In Approval, Offer Accepted - Yet to Join, Joined, Offer Declined, Not Joined - Backed Out, Rejected - Profile, Rejected - Screening, Rejected - R1, Rejected - R2, On Hold - Position Filled, Withdrawn. Merge only the spelling variants (`Rejected-Profile`, `Profile Reject` → Rejected - Profile; `R1 Reject` → Rejected - R1; `joined`/`Joined ` → Joined; `Declined` → Offer Declined). |
| 5 | Joiner counts looked inconsistent | 180 "Joined" vs 167 actual joining dates. All 13 extra, plus 1 accepted offer marked "Rejected - Profile", sit in the 36 candidate rows whose Req ID matches no requisition (all `C690xxx`, `REQ_4xxx`). After excluding them: 167 joined = 167 joining dates = 167 reqs Closed - Joined; 64 yet-to-join = 64 reqs Offer Accepted; no req has two live hires. | No conflict — the 36 are already excluded by the spec. Log it as a DQ finding. **Resolved.** |
| 6 | Offer Status "Pending" (data dictionary) | None in data: 249 Accepted, 51 Declined (246 / 51 after dropping duplicates). | Nothing to do. **Resolved.** |
| 7 | `BLR` location → "decide by Location Type" | All 5 `BLR` rows are Location Type = City. | Map to `Bengaluru` (city), not HO. **Resolved.** |
| 8 | Performance rating null "otherwise → Missing" | All 173 nulls are joiners on/after 01-Jan-2026. | All become Not Rated; Missing will have 0 rows. **Resolved.** |
| 9 | Replaced Employee ID → Employee_Master | 28 of 128 IDs not in the master. | Expected per data dictionary (left before 01-Apr-2026). Exit date / type / regrettable and `days_exit_to_req` stay null for them; log the count. **Resolved.** |
| 10 | Requisition thread variant `central` (lowercase) | Not in the listed variants. | Covered by the same normalisation. **Resolved.** |
| 11 | Dependencies used by the plan but not named in the Stack list | `react-router-dom` (routes), `pyarrow` (pandas parquet), `httpx` (FastAPI test client), `python-dotenv` (reads `.env`), plus `uvicorn` and `groq`, which the Stack implies. | **Decision needed:** approve these 6. |

Checks that matched the case brief exactly: 12 duplicate employee IDs (8 exact), 8 wave spellings with no wave/date disagreement, all submissions inside their window, 28 double-answered employee-wave pairs, 3 test IDs + 6 `EMP99xxx` IDs, 6 responses from employees not active on the wave open date, 12 string req dates, criticality and SLA days 100% consistent with the rules, 22 exact duplicate candidates, 808 rows missing `REQ_`, 36 orphans after fixing, 16 shortlisted-before-applied, Excel serials only in Offer Released On (9), all Vendor/Consultant rows carry an Agency Name (safe to map to Agency), all interviewer / hiring-manager / directory IDs resolve.
