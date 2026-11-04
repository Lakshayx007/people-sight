# Metric definitions

Single source of truth for every metric in the dashboards, the insights and Ask the Data (`backend/ask.py` puts this list in its prompt).

<!-- definitions -->
- eNPS (Q1, 0-10) = % promoters (9-10) − % detractors (0-6), × 100, one decimal. Passives = 7-8.
- Response rate = valid respondents ÷ employees active on the wave open date (same segment).
- Driver scores Q2-Q6 (1-5): mean and % favourable (4-5). Q2 manager feedback, Q3 fair pay,
  Q4 workload, Q5 onboarding/tools, Q6 growth path.
- Wave change = Oct − Apr. Also report a PANEL view (employees who answered both waves).
- Segment attributes for survey analysis = the employee's attributes snapshotted at the wave open date.
- Tech job family = Engineering, Product, Data & Analytics, Design & Research. Else Non-Tech.
- Compa-ratio = Annual CTC ÷ Band Mid for (job family, grade) from the band set effective on
  the as-of date (2026-04-01 set). Bands: <0.90 below, 0.90-1.10 at, >1.10 above.
- Tenure band at wave open date: <6m, 6-12m, 1-2y, 2-4y, 4y+.
- manager_status (3 levels; the dashboard filter and segment dimension):
  'Changed manager' = Manager Effective From between 18-Apr-2026 and 04-Oct-2026 AND > Date of Joining;
  'New joiner (first manager)' = Manager Effective From in that window AND = Date of Joining (joined after the
  April wave); 'Same manager' = everyone else. Assumption: Manager Effective From equal to joining date = first
  manager, not a change. Only the current manager is recorded, so earlier or multiple changes are not visible.
  The literal rule (effective date in the window, any joining date) is kept as manager_changed_literal —
  backup only, never used in charts.
- Time to Fill (TTF) = Offer Response On (hired candidate's accepted offer) − Req Raised On, days.
  Hired candidate = Offer Status Accepted and not Backed Out. If a req has several, take the one
  who joined, else yet-to-join, else earliest acceptance.
- SLA days: 30 for TBA-G2, 45 for G3-G5, 60 for G6+. SLA met = TTF <= SLA. Open reqs:
  breached if (31-Oct-2026 − Req Raised On) > SLA. Compare to "SLA Status (System)" and report mismatches.
- Critical = Tech G6+ or Non-Tech G8+.
- Funnel stages: Applied -> Shortlisted -> Screening Done -> R1 Interview -> R1 Select ->
  R2 Interview -> Offer Released -> Offer Accepted -> Joined. Stage reached = date present.
- Stage time = median days between consecutive stage dates (only rows with both dates, valid order).
- Offer acceptance rate = Accepted ÷ (Accepted + Declined). Joining rate = Joined ÷ Accepted
  (offers whose Expected DOJ <= 31-Oct-2026).
- R1 feedback turnaround = R1 Feedback Submitted On − R1 Interview Date (days).
- Agency fee = 8.33% × Offered CTC for agency-sourced candidates who Joined.
- Recruiter attainment = accepted offers per month ÷ Monthly Offer Target.
