# Hypotheses (Phase 9)

Written from the case brief before testing; `pipeline/05_insights.py` tests each one and writes `analysis/insights.md`. Tests: eNPS z-test on the +1/0/−1 score, two-proportion z / Fisher exact, Mann-Whitney U, Wilcoxon signed-rank (panel), within-strata permutation, Spearman.

| ID | Hypothesis | Data | Test |
|---|---|---|---|
| 1 | Overall eNPS fell April → October, also on the panel | v_survey | z-test; Wilcoxon on panel |
| 2 | Changed manager < Same manager in October, within thread and grade, on the panel, via Q2 | v_survey | z-test; permutation within thread × grade; Mann-Whitney on panel change and Q2 |
| 2b | New joiner (first manager) < Same manager on Q1 and Q5 in October | v_survey | z-test; Mann-Whitney |
| 3 | Intercity is the weakest thread; how much is manager change | v_survey | z-test; counterfactual |
| 3a | Intercity by manager_status, Apr and Oct; Intercity without changed managers vs rest | v_survey | z-test |
| 3b | Timing of Intercity manager changes and number of distinct new managers | v_employees (no survey) | descriptive |
| 4 | Driver importance vs score: which to fix first | v_survey | Spearman with Q1 |
| 5 | Compa-ratio < 0.90 → lower Q3 and Q1 | v_survey | Mann-Whitney; z-test |
| 6 | Tenure < 6m → lower Q5 | v_survey | Mann-Whitney |
| 7 | April detractors exited (voluntary, regrettable) more than promoters | v_survey | z / Fisher |
| 8 | Response-rate shifts by thread vs real sentiment change | v_invited, v_survey | z-test on rates; non-response bias |
| 9 | Small-n segments are suppressed | v_survey | descriptive |
| 10 | TTF vs SLA by grade: which grades breach most | v_requisitions | z / Fisher |
| 11 | Recruiter concentration vs TTF, breach and target | v_requisitions, v_recruiters | Mann-Whitney; z-test |
| 12 | Slow R1 interviewers and the TTF cost on their reqs | v_candidates, v_requisitions | Fisher; counterfactual |
| 13 | Declines vs offered/expected CTC and budget headroom | v_candidates, v_requisitions | z-test |
| 14 | Source conversion, TTF and cost per hire | v_candidates | z-test |
| 15 | System SLA status vs recomputed | v_requisitions | exact McNemar |
| 16 | Backfill lag from exit to replacement req; share regrettable | v_requisitions | Mann-Whitney |
| 17 | Low / falling eNPS teams raise more replacement reqs | v_survey, v_employees, v_requisitions (team level) | Spearman |
| 18 | Interviewers and hiring managers report worse Q4 workload (n ≥ 5) | v_survey (role flags) | Mann-Whitney |
| 19 | This year's joiners rate Q5 onboarding lower in October | v_survey | Mann-Whitney |
| 20 | Where the days go: median days per funnel stage for filled reqs, overall vs G6+ (added at the Phase 9 review) | v_requisitions, v_candidates | Mann-Whitney per stage |
