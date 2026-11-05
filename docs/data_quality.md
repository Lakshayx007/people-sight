# Data quality note

Porter People Analytics case data, as of 31-Oct-2026. Every cleaning rule is logged in `data/clean/dq_log.csv` (116 rules; 71 changed data). The raw workbooks are never modified. Main items below; counts come from the log.

**eNPS workbook**

| Issue | Rows / values | Treatment | Assumption |
|---|---|---|---|
| Duplicate employee rows (exact) | 8 | Dropped | — |
| Same ID, different Location | 4 | Kept the latest record | Latest record is current |
| Thread / grade / location / status spellings | 338 | Mapped to one canonical list | Only spelling variants merged |
| Mixed date formats (joining, exit) | 136 | Parsed day-first | DD/MM, not MM/DD |
| 'Active' with an exit date | 4 | Set to Exited | Exit date is reliable |
| Exited without an exit date | 3 | Not invited to October; April only if joined by 06-Apr | Left before the October wave; date unknown |
| CTC as text (4,48,000 / 2.96 LPA) | 102 | Converted to rupees | — |
| Monthly CTC entered as annual | 7 | Multiplied by 12, flagged | x12 lands within 0.5-2x band mid |
| manager_status = Changed manager | 62 | Effective 18-Apr..04-Oct and after joining | Only the current manager is recorded |
| manager_status = New joiner (first manager) | 186 | Effective date = joining date | First manager, not a change |
| Test responses | 3 | Excluded | — |
| Respondent not in master | 6 | Excluded | — |
| Two answers in one wave | 28 | Kept the latest | — |
| Not active on wave open date | 6 | Excluded | — |
| Q1 blank or outside 0-10 | 18 | Response invalid for all metrics | One base n per wave |

Rows in → out: Employee_Master 1,322 → 1,310; eNPS_Responses 1,726 → 1,665.

**Recruitment workbook**

| Issue | Rows / values | Treatment | Assumption |
|---|---|---|---|
| Duplicate candidate rows | 22 | Dropped | — |
| Req ID without 'REQ_' prefix | 805 | Prefix added | — |
| Orphan candidates (no requisition) | 36 | Excluded; kept in candidates_excluded | Belong to older reqs not in the extract |
| Source spellings; Vendor/Consultant | 843 | Mapped to 6 sources; Vendor/Consultant = Agency | All carry an agency name |
| Notice period as text ('2 months') | 345 | Converted to days | 1 month = 30 days |
| Accepted, then backed out | 14 | Not a hire | Req counted filled only if refilled |
| Backfill raised before the exit | 22 | Kept | Backfill ahead of a known exit |
| ATS SLA status vs dates (all 'Within SLA' → breached, 2-86 days over) | 14 | Recomputed status used; listed as a finding | ATS rule unknown |

Rows in → out: Candidates 5,815 → 5,757.

**Definition used throughout — manager_status.** 'Changed manager' = Manager Effective From between 18-Apr and 04-Oct-2026 and after the joining date; 'New joiner (first manager)' = in that window and equal to the joining date; 'Same manager' = everyone else.

> **Limitations.** (1) HRMS keeps only current attributes and the current manager, so thread, grade, rating and manager history are not visible. (2) Survey data are anonymised (salted key, groups of 5 or more), so individual follow-up is impossible by design. (3) The data are synthetic and cover one financial half-year; ATS SLA logic and the 36 orphan candidates' requisitions are outside the extract.
