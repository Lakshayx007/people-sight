"""
metrics_hiring.py
-----------------
One function per Hiring metric. Each returns (sql, params).

Filters: `wr` applies to v_requisitions, `wc` to v_candidates (v_candidates carries the requisition's
attributes under the same column names, plus `source`). filters.build_where() builds both.

Fill measures (filled, TTF, SLA met) are computed from the HIRED CANDIDATE's row (v_candidates.is_hire), and
volume measures (reqs raised, open, past SLA) from v_requisitions. Unfiltered they are identical to counting
requisitions. Under a Source filter they mean: reqs raised / open = reqs with >= 1 applicant from the source;
filled / TTF / SLA = reqs filled by a candidate from the source — so the funnel always reconciles with the KPIs.

Definitions (docs/metric_definitions.md): TTF = hired candidate's Offer Response On - Req Raised On (days).
SLA met = TTF <= SLA days (recomputed status is authoritative). Open reqs breached if age at 31-Oct > SLA.
Offer acceptance = Accepted / (Accepted + Declined). Joining rate = Joined / Accepted with Expected DOJ <= 31-Oct.
Agency fee = 8.33% x Offered CTC for agency-sourced candidates who joined.
Recruiter attainment = accepted offers per month / Monthly Offer Target.
"""
from __future__ import annotations

from backend.sql_common import ALL, FY_MONTHS, Where, merge

STAGES = [("Applied", "reached_applied"), ("Shortlisted", "reached_shortlisted"), ("Screening Done", "reached_screening_done"),
          ("R1 Interview", "reached_r1_interview"), ("R1 Select", "reached_r1_select"), ("R2 Interview", "reached_r2_interview"),
          ("Offer Released", "reached_offer_released"), ("Offer Accepted", "reached_offer_accepted"), ("Joined", "reached_joined")]
TRANSITIONS = [("Applied → Shortlisted", "days_applied_to_shortlisted"), ("Shortlisted → Screening", "days_shortlisted_to_screening"),
               ("Screening → R1", "days_screening_to_r1"), ("R1 → R2", "days_r1_to_r2"), ("R2 → Offer", "days_r2_to_offer"),
               ("Offer → Response", "days_offer_to_response"), ("Response → Join", "days_response_to_join")]


def _ctes(wr: Where, wc: Where) -> tuple[str, dict]:
    return (f"r AS (SELECT * FROM v_requisitions WHERE {wr[0]}), c AS (SELECT * FROM v_candidates WHERE {wc[0]})",
            merge(wr[1], wc[1]))


def kpis(wr: Where = ALL, wc: Where = ALL):
    """Headline hiring KPIs in one row."""
    ctes, p = _ctes(wr, wc)
    sql = f"""
WITH {ctes}
SELECT (SELECT count(*) FROM r) AS reqs_raised,
       (SELECT count(*) FILTER (WHERE is_open) FROM r) AS open_reqs,
       (SELECT count(*) FILTER (WHERE is_hire) FROM c) AS filled_reqs,
       (SELECT count(*) FILTER (WHERE is_hire AND is_joined) FROM c) AS filled_joined,
       (SELECT count(*) FILTER (WHERE is_hire AND NOT is_joined) FROM c) AS filled_yet_to_join,
       (SELECT count(*) FILTER (WHERE req_status IN ('On Hold', 'Archived')) FROM r) AS on_hold_or_archived,
       (SELECT median(req_ttf_days) FROM c WHERE is_hire) AS median_ttf_days,
       (SELECT round(100.0 * avg(req_sla_met::INT), 1) FROM c WHERE is_hire) AS pct_within_sla,
       (SELECT count(*) FILTER (WHERE open_breached) FROM r) AS open_past_sla,
       (SELECT count(*) FILTER (WHERE is_offer_accepted) FROM c) AS offers_accepted,
       (SELECT count(*) FILTER (WHERE is_offer_declined) FROM c) AS offers_declined,
       (SELECT round(100.0 * count(*) FILTER (WHERE is_offer_accepted)
               / nullif(count(*) FILTER (WHERE is_offer_accepted OR is_offer_declined), 0), 1) FROM c) AS offer_acceptance_pct,
       (SELECT count(*) FILTER (WHERE joining_due AND is_joined) FROM c) AS joined_of_due,
       (SELECT count(*) FILTER (WHERE joining_due) FROM c) AS joining_due,
       (SELECT round(100.0 * count(*) FILTER (WHERE joining_due AND is_joined) / nullif(count(*) FILTER (WHERE joining_due), 0), 1) FROM c) AS joining_rate_pct,
       (SELECT coalesce(sum(agency_fee_inr), 0) FROM c) AS agency_fees_inr,
       (SELECT round(coalesce(sum(agency_fee_inr), 0) / 100000, 2) FROM c) AS agency_fees_lakh,
       (SELECT count(*) FILTER (WHERE agency_fee_inr > 0) FROM c) AS agency_joiners,
       (SELECT count(*) FROM c) AS applicants,
       (SELECT count(*) FROM r) AS n"""
    return sql, p


def monthly(wr: Where = ALL, wc: Where = ALL):
    """Per month Apr-Oct 2026: reqs raised, offers accepted (by acceptance date), joins (by actual DOJ)."""
    ctes, p = _ctes(wr, wc)
    months = ", ".join(f"('{m}')" for m in FY_MONTHS)
    sql = f"""
WITH {ctes},
     m(month) AS (VALUES {months}),
     raised AS (SELECT raised_month AS month, count(*) AS n FROM r GROUP BY 1),
     acc AS (SELECT strftime(offer_response_on, '%Y-%m') AS month, count(*) AS n FROM c WHERE is_offer_accepted GROUP BY 1),
     joins AS (SELECT strftime(actual_doj, '%Y-%m') AS month, count(*) AS n FROM c WHERE is_joined GROUP BY 1)
SELECT m.month, coalesce(raised.n, 0) AS reqs_raised, coalesce(acc.n, 0) AS offers_accepted, coalesce(joins.n, 0) AS joins
FROM m LEFT JOIN raised USING (month) LEFT JOIN acc USING (month) LEFT JOIN joins USING (month)
ORDER BY m.month"""
    return sql, p


def funnel(wr: Where = ALL, wc: Where = ALL):
    """Candidates reaching each stage, conversion from the previous stage and from Applied."""
    _, p = _ctes(wr, wc)
    parts = [f"SELECT {i} AS step, '{name}' AS stage, count(*) FILTER (WHERE {col}) AS candidates FROM c"
             for i, (name, col) in enumerate(STAGES, 1)]
    sql = f"""
WITH c AS (SELECT * FROM v_candidates WHERE {wc[0]}),
     f AS ({' UNION ALL '.join(parts)})
SELECT step, stage, candidates,
       round(100.0 * candidates / nullif(lag(candidates) OVER (ORDER BY step), 0), 1) AS pct_of_previous,
       round(100.0 * candidates / nullif(first_value(candidates) OVER (ORDER BY step), 0), 1) AS pct_of_applied
FROM f ORDER BY step"""
    return sql, dict(wc[1])


def stage_time(wr: Where = ALL, wc: Where = ALL):
    """Median (and p75) days between consecutive stage dates; rows with both dates in valid order only."""
    parts = [f"SELECT {i} AS step, '{name}' AS transition, count({col}) AS n, median({col}) AS median_days, "
             f"quantile_cont({col}, 0.75) AS p75_days FROM c" for i, (name, col) in enumerate(TRANSITIONS, 1)]
    sql = f"""
WITH c AS (SELECT * FROM v_candidates WHERE {wc[0]} AND NOT stage_dates_invalid)
{' UNION ALL '.join(parts)}
ORDER BY step"""
    return sql, dict(wc[1])


def source(wr: Where = ALL, wc: Where = ALL):
    """Source effectiveness: applicants, hires, applicant-to-hire %, median TTF of reqs filled from the source,
    offer acceptance, agency cost per joiner."""
    sql = f"""
WITH c AS (SELECT * FROM v_candidates WHERE {wc[0]})
SELECT source,
       count(*) AS applicants,
       count(*) FILTER (WHERE reached_offer_released) AS offers,
       count(*) FILTER (WHERE is_hire) AS hires,
       count(*) FILTER (WHERE is_joined) AS joined,
       round(100.0 * count(*) FILTER (WHERE is_hire) / count(*), 2) AS applicant_to_hire_pct,
       median(req_ttf_days) FILTER (WHERE is_hire) AS median_ttf_days,
       round(100.0 * count(*) FILTER (WHERE is_offer_accepted)
             / nullif(count(*) FILTER (WHERE is_offer_accepted OR is_offer_declined), 0), 1) AS offer_acceptance_pct,
       sum(agency_fee_inr) AS agency_fees_inr,
       round(sum(agency_fee_inr) / nullif(count(*) FILTER (WHERE is_joined), 0), 0) AS cost_per_joiner_inr
FROM c GROUP BY source
ORDER BY applicants DESC"""
    return sql, dict(wc[1])


def recruiters(wr: Where = ALL, wc: Where = ALL, months: int = len(FY_MONTHS)):
    """Recruiter load vs target: reqs owned (share), open, filled, median TTF, SLA met %, and attainment in two
    versions over the FY-to-date months (Apr-Oct = 7):
      *_all        = all accepted offers (incl. candidates who later backed out)
      *_excl_bo    = accepted offers excluding backed-out candidates."""
    ctes, p = _ctes(wr, wc)
    sql = f"""
WITH {ctes},
     rq AS (SELECT recruiter, count(*) AS reqs, count(*) FILTER (WHERE is_open) AS open_reqs,
                   count(*) FILTER (WHERE open_breached) AS open_past_sla
            FROM r GROUP BY recruiter),
     ac AS (SELECT recruiter, count(*) FILTER (WHERE is_offer_accepted) AS acc_all,
                   count(*) FILTER (WHERE is_offer_accepted AND NOT is_backed_out) AS acc_excl_bo,
                   count(*) FILTER (WHERE is_hire) AS filled, median(req_ttf_days) FILTER (WHERE is_hire) AS median_ttf_days,
                   round(100.0 * avg(req_sla_met::INT) FILTER (WHERE is_hire), 1) AS pct_within_sla
            FROM c GROUP BY recruiter)
SELECT t.recruiter, t.recruiter_id, coalesce(rq.reqs, 0) AS reqs,
       round(100.0 * coalesce(rq.reqs, 0) / nullif(sum(rq.reqs) OVER (), 0), 1) AS pct_of_reqs,
       coalesce(rq.open_reqs, 0) AS open_reqs, coalesce(rq.open_past_sla, 0) AS open_past_sla,
       coalesce(ac.filled, 0) AS filled, ac.median_ttf_days, ac.pct_within_sla,
       t.monthly_offer_target,
       coalesce(ac.acc_all, 0) AS offers_accepted_all,
       round(coalesce(ac.acc_all, 0) / $months, 2) AS accepted_per_month_all,
       round(100.0 * coalesce(ac.acc_all, 0) / $months / t.monthly_offer_target, 1) AS attainment_all_pct,
       coalesce(ac.acc_excl_bo, 0) AS offers_accepted_excl_bo,
       round(coalesce(ac.acc_excl_bo, 0) / $months, 2) AS accepted_per_month_excl_bo,
       round(100.0 * coalesce(ac.acc_excl_bo, 0) / $months / t.monthly_offer_target, 1) AS attainment_excl_bo_pct
FROM v_recruiters t LEFT JOIN rq USING (recruiter) LEFT JOIN ac USING (recruiter)
WHERE coalesce(rq.reqs, 0) > 0
ORDER BY reqs DESC"""
    return sql, merge(p, {"months": months})


def recruiter_comparison(wr: Where = ALL, wc: Where = ALL):
    """Fair comparison per recruiter, independent of how many reqs each was given: reqs assigned, filled %,
    median TTF, % filled within SLA, open reqs past SLA, accepted offers per assigned req."""
    ctes, p = _ctes(wr, wc)
    sql = f"""
WITH {ctes},
     rq AS (SELECT recruiter, count(*) AS reqs_assigned, count(*) FILTER (WHERE is_open) AS open_reqs,
                   count(*) FILTER (WHERE open_breached) AS open_past_sla
            FROM r GROUP BY recruiter),
     hc AS (SELECT recruiter, count(*) FILTER (WHERE is_hire) AS filled,
                   median(req_ttf_days) FILTER (WHERE is_hire) AS median_ttf_days,
                   round(100.0 * avg(req_sla_met::INT) FILTER (WHERE is_hire), 1) AS pct_filled_within_sla,
                   count(*) FILTER (WHERE is_offer_accepted) AS offers_accepted
            FROM c GROUP BY recruiter)
SELECT t.recruiter, coalesce(rq.reqs_assigned, 0) AS reqs_assigned, coalesce(hc.filled, 0) AS filled,
       round(100.0 * coalesce(hc.filled, 0) / nullif(rq.reqs_assigned, 0), 1) AS filled_pct,
       hc.median_ttf_days, hc.pct_filled_within_sla,
       coalesce(rq.open_reqs, 0) AS open_reqs, coalesce(rq.open_past_sla, 0) AS open_past_sla,
       coalesce(hc.offers_accepted, 0) AS offers_accepted,
       round(coalesce(hc.offers_accepted, 0) / nullif(rq.reqs_assigned, 0), 2) AS accepted_per_assigned_req
FROM v_recruiters t LEFT JOIN rq USING (recruiter) LEFT JOIN hc USING (recruiter)
WHERE coalesce(rq.reqs_assigned, 0) > 0
ORDER BY reqs_assigned DESC"""
    return sql, p


def interviewers(wr: Where = ALL, wc: Where = ALL, top: int = 15, min_n: int = 5):
    """Slowest R1 interviewers by median feedback turnaround (min_n interviews with feedback), names from People_Directory."""
    sql = f"""
WITH c AS (SELECT * FROM v_candidates WHERE {wc[0]})
SELECT c.r1_interviewer_id AS interviewer_id, i.employee_name AS interviewer, i.designation, i.thread,
       count(c.r1_feedback_days) AS n, median(c.r1_feedback_days) AS median_feedback_days,
       round(avg(c.r1_feedback_days), 1) AS mean_feedback_days,
       round(100.0 * avg((c.r1_feedback_days > 2)::INT), 1) AS pct_over_2_days,
       max(c.r1_feedback_days) AS max_feedback_days,
       count(DISTINCT c.req_id) AS reqs
FROM c JOIN v_interviewers i ON i.employee_id = c.r1_interviewer_id
WHERE c.r1_feedback_days IS NOT NULL
GROUP BY ALL
HAVING count(c.r1_feedback_days) >= $min_n
ORDER BY median_feedback_days DESC, mean_feedback_days DESC, interviewer_id
LIMIT $top"""
    return sql, merge(wc[1], {"top": top, "min_n": min_n})


def ttf_by_grade(wr: Where = ALL, wc: Where = ALL):
    """Per grade: reqs raised, filled, median / p75 TTF, SLA days, breached, % within SLA (fill measures from hires)."""
    ctes, p = _ctes(wr, wc)
    sql = f"""
WITH {ctes},
     rg AS (SELECT grade, min(grade_num) AS grade_num, count(*) AS reqs, max(sla_days) AS sla_days FROM r GROUP BY grade),
     hg AS (SELECT grade, count(*) AS filled, median(req_ttf_days) AS median_ttf_days,
                   quantile_cont(req_ttf_days, 0.75) AS p75_ttf_days,
                   count(*) FILTER (WHERE NOT req_sla_met) AS breached,
                   round(100.0 * avg(req_sla_met::INT), 1) AS pct_within_sla
            FROM c WHERE is_hire GROUP BY grade)
SELECT rg.grade, rg.grade_num, rg.reqs, coalesce(hg.filled, 0) AS filled, hg.median_ttf_days, hg.p75_ttf_days,
       rg.sla_days, coalesce(hg.breached, 0) AS breached, hg.pct_within_sla
FROM rg LEFT JOIN hg USING (grade) ORDER BY rg.grade_num"""
    return sql, p


def open_aging(wr: Where = ALL, wc: Where = ALL):
    """Each open req: age at 31-Oct vs SLA, days over SLA."""
    sql = f"""
WITH r AS (SELECT * FROM v_requisitions WHERE {wr[0]} AND is_open)
SELECT req_id, designation, grade, thread, recruiter, req_raised_on, age_days_as_of_31oct AS age_days, sla_days,
       age_days_as_of_31oct - sla_days AS days_over_sla, open_breached,
       CASE WHEN NOT open_breached THEN 'Within SLA'
            WHEN age_days_as_of_31oct - sla_days <= 15 THEN '1-15 days over'
            WHEN age_days_as_of_31oct - sla_days <= 30 THEN '16-30 days over'
            WHEN age_days_as_of_31oct - sla_days <= 60 THEN '31-60 days over'
            ELSE '60+ days over' END AS aging_bucket
FROM r ORDER BY days_over_sla DESC, req_id"""
    return sql, dict(wr[1])


def open_aging_buckets(wr: Where = ALL, wc: Where = ALL):
    """Open reqs counted by aging bucket."""
    inner, p = open_aging(wr, wc)
    sql = f"""
WITH o AS ({inner})
SELECT aging_bucket, count(*) AS open_reqs
FROM o GROUP BY aging_bucket
ORDER BY CASE aging_bucket WHEN 'Within SLA' THEN 1 WHEN '1-15 days over' THEN 2 WHEN '16-30 days over' THEN 3
                           WHEN '31-60 days over' THEN 4 ELSE 5 END"""
    return sql, p


def offers(wr: Where = ALL, wc: Where = ALL):
    """Offers by offered / expected CTC ratio band: offers, accepted, declined, decline rate."""
    sql = f"""
WITH c AS (SELECT * FROM v_candidates WHERE {wc[0]} AND (is_offer_accepted OR is_offer_declined)),
     b AS (SELECT *, CASE WHEN offer_to_expected_ratio < 0.90 THEN '<0.90'
                          WHEN offer_to_expected_ratio < 1.00 THEN '0.90-0.99'
                          WHEN offer_to_expected_ratio < 1.10 THEN '1.00-1.09'
                          ELSE '>=1.10' END AS ratio_band FROM c)
SELECT ratio_band, count(*) AS offers, count(*) FILTER (WHERE is_offer_accepted) AS accepted,
       count(*) FILTER (WHERE is_offer_declined) AS declined,
       round(100.0 * avg(is_offer_declined::INT), 1) AS decline_rate_pct,
       round(median(offer_to_budget_ratio), 3) AS median_offer_to_budget
FROM b GROUP BY ratio_band
ORDER BY CASE ratio_band WHEN '<0.90' THEN 1 WHEN '0.90-0.99' THEN 2 WHEN '1.00-1.09' THEN 3 ELSE 4 END"""
    return sql, dict(wc[1])


def offers_summary(wr: Where = ALL, wc: Where = ALL):
    """Accepted vs declined offers: median offered/expected ratio and offered/budget ratio (budget headroom)."""
    sql = f"""
WITH c AS (SELECT * FROM v_candidates WHERE {wc[0]} AND (is_offer_accepted OR is_offer_declined))
SELECT CASE WHEN is_offer_accepted THEN 'Accepted' ELSE 'Declined' END AS outcome, count(*) AS n,
       round(median(offer_to_expected_ratio), 3) AS median_offer_to_expected,
       round(median(offer_to_budget_ratio), 3) AS median_offer_to_budget,
       round(100.0 * avg((offer_to_expected_ratio < 1)::INT), 1) AS pct_below_expected
FROM c GROUP BY 1 ORDER BY 1"""
    return sql, dict(wc[1])


def sla_mismatch(wr: Where = ALL, wc: Where = ALL):
    """System SLA status vs recomputed status: counts per pair (blank = no status)."""
    sql = f"""
WITH r AS (SELECT * FROM v_requisitions WHERE {wr[0]})
SELECT coalesce(sla_status_system, '(blank)') AS system_status, coalesce(sla_status_recomputed, '(blank)') AS recomputed_status,
       count(*) AS reqs, bool_or(sla_status_mismatch) AS mismatch
FROM r GROUP BY ALL ORDER BY mismatch DESC, reqs DESC"""
    return sql, dict(wr[1])


def sla_mismatch_list(wr: Where = ALL, wc: Where = ALL):
    """The individual reqs where system and recomputed SLA status disagree."""
    sql = f"""
WITH r AS (SELECT * FROM v_requisitions WHERE {wr[0]} AND sla_status_mismatch)
SELECT req_id, grade, recruiter, req_raised_on, offer_accepted_on, ttf_days, sla_days, ttf_days - sla_days AS days_over_sla,
       sla_status_system, sla_status_recomputed, had_backout
FROM r ORDER BY days_over_sla DESC, req_id"""
    return sql, dict(wr[1])


def backfill(wr: Where = ALL, wc: Where = ALL):
    """Replacement reqs: exit-to-req lag and share backfilling regrettable exits."""
    sql = f"""
WITH r AS (SELECT * FROM v_requisitions WHERE {wr[0]} AND position_type = 'Replacement')
SELECT count(*) AS replacement_reqs,
       count(days_exit_to_req) AS with_known_exit_date,
       median(days_exit_to_req) AS median_days_exit_to_req,
       count(*) FILTER (WHERE days_exit_to_req < 0) AS raised_before_exit,
       count(*) FILTER (WHERE replaced_is_regrettable) AS backfilling_regrettable,
       round(100.0 * count(*) FILTER (WHERE replaced_is_regrettable) / nullif(count(*) FILTER (WHERE replaced_in_master), 0), 1) AS pct_regrettable_of_known,
       median(ttf_days) FILTER (WHERE is_filled) AS median_ttf_days
FROM r"""
    return sql, dict(wr[1])


ALL_METRICS = {"kpis": kpis, "monthly": monthly, "funnel": funnel, "stage_time": stage_time, "source": source,
               "recruiters": recruiters, "recruiter_comparison": recruiter_comparison, "interviewers": interviewers, "ttf_by_grade": ttf_by_grade,
               "open_aging_buckets": open_aging_buckets, "offers": offers, "offers_summary": offers_summary,
               "sla_mismatch": sla_mismatch, "sla_mismatch_list": sla_mismatch_list, "backfill": backfill,
               "open_aging": open_aging}
