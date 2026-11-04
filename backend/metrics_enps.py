"""
metrics_enps.py
---------------
One function per Employee Sentiment metric. Each returns (sql, params).

Filters: `w` is a (fragment, params) pair applied to BOTH v_survey and v_invited (they share the
segment column names), so numerators and response-rate denominators always describe the same group.
Small-n suppression: any group with fewer than MIN_N respondents returns NULL scores and suppressed = true.

Definitions (the case brief): eNPS = 100 * (share Q1 9-10 - share Q1 0-6), one decimal.
Response rate = valid respondents / employees active on the wave open date (same segment).
Driver scores Q2-Q6: mean and % favourable (4-5).
"""
from __future__ import annotations

from backend.sql_common import ALL, LOW_RESPONSE_PCT, MIN_N, Where, ident, merge

SEGMENT_DIMS = {
    "thread": "Thread", "function": "Function", "job_family": "Job family", "grade": "Grade", "location": "Location",
    "location_type": "Location type", "company": "Company", "tenure_band": "Tenure band",
    "performance_rating": "Performance rating", "compa_band": "Compa band", "manager_status": "Manager status",
    "joined_this_fy": "Joined this FY", "is_interviewer": "Interviewer", "is_hiring_manager": "Hiring manager",
}
DRIVERS = {"q2": "Manager feedback", "q3": "Fair pay", "q4": "Workload", "q5": "Onboarding & tools", "q6": "Growth path"}
ORDER = {
    "grade": "grade_num",
    "tenure_band": "CASE tenure_band WHEN '<6m' THEN 1 WHEN '6-12m' THEN 2 WHEN '1-2y' THEN 3 WHEN '2-4y' THEN 4 ELSE 5 END",
    "compa_band": "CASE compa_band WHEN 'Below' THEN 1 WHEN 'At' THEN 2 WHEN 'Above' THEN 3 ELSE 4 END",
    "manager_status": "CASE manager_status WHEN 'Same manager' THEN 1 WHEN 'Changed manager' THEN 2 ELSE 3 END",
}
WAVE_ORDER = "CASE wave WHEN 'Apr' THEN 1 ELSE 2 END"


def _sup(n: str, expr: str) -> str:
    """NULL the expression when the base n is below the threshold."""
    return f"CASE WHEN {n} < {MIN_N} THEN NULL ELSE {expr} END"


ENPS = "round(100.0 * (avg(is_promoter) - avg(is_detractor)), 1)"


def by_wave(w: Where = ALL):
    """Per wave: invited, valid respondents (n), response rate, % promoters / passives / detractors, eNPS."""
    f, p = w
    sql = f"""
WITH s AS (SELECT * FROM v_survey WHERE {f}),
     i AS (SELECT * FROM v_invited WHERE {f}),
     inv AS (SELECT wave, count(*) AS invited FROM i GROUP BY wave),
     sv AS (SELECT wave, count(*) AS n, avg(is_promoter) AS p, avg(is_passive) AS pa, avg(is_detractor) AS d
            FROM s GROUP BY wave)
SELECT inv.wave,
       inv.invited,
       coalesce(sv.n, 0) AS n,
       round(100.0 * coalesce(sv.n, 0) / inv.invited, 1) AS response_rate_pct,
       {_sup('coalesce(sv.n, 0)', 'round(100.0 * sv.p, 1)')} AS pct_promoters,
       {_sup('coalesce(sv.n, 0)', 'round(100.0 * sv.pa, 1)')} AS pct_passives,
       {_sup('coalesce(sv.n, 0)', 'round(100.0 * sv.d, 1)')} AS pct_detractors,
       {_sup('coalesce(sv.n, 0)', 'round(100.0 * (sv.p - sv.d), 1)')} AS enps,
       coalesce(sv.n, 0) < {MIN_N} AS suppressed,
       100.0 * coalesce(sv.n, 0) / inv.invited < {LOW_RESPONSE_PCT} AS low_response
FROM inv LEFT JOIN sv USING (wave)
ORDER BY CASE inv.wave WHEN 'Apr' THEN 1 ELSE 2 END"""
    return sql, dict(p)


def kpis(w: Where = ALL):
    """One row: eNPS Apr, eNPS Oct, change (Oct - Apr, pts), response rates, Oct promoter/passive/detractor mix, n."""
    inner, p = by_wave(w)
    sql = f"""
WITH bw AS ({inner})
SELECT max(enps) FILTER (WHERE wave = 'Apr') AS enps_apr,
       max(enps) FILTER (WHERE wave = 'Oct') AS enps_oct,
       round(max(enps) FILTER (WHERE wave = 'Oct') - max(enps) FILTER (WHERE wave = 'Apr'), 1) AS enps_change,
       max(n) FILTER (WHERE wave = 'Apr') AS n_apr,
       max(n) FILTER (WHERE wave = 'Oct') AS n_oct,
       max(invited) FILTER (WHERE wave = 'Apr') AS invited_apr,
       max(invited) FILTER (WHERE wave = 'Oct') AS invited_oct,
       max(response_rate_pct) FILTER (WHERE wave = 'Apr') AS response_rate_apr_pct,
       max(response_rate_pct) FILTER (WHERE wave = 'Oct') AS response_rate_oct_pct,
       max(pct_promoters) FILTER (WHERE wave = 'Oct') AS pct_promoters_oct,
       max(pct_passives) FILTER (WHERE wave = 'Oct') AS pct_passives_oct,
       max(pct_detractors) FILTER (WHERE wave = 'Oct') AS pct_detractors_oct,
       coalesce(sum(n), 0) AS n
FROM bw"""
    return sql, p


def panel(w: Where = ALL):
    """Respondents valid in BOTH waves: eNPS each wave on the same people, and per-person Q1 movement."""
    f, p = w
    sql = f"""
WITH s AS (SELECT * FROM v_survey WHERE {f} AND responded_both_waves),
     per AS (SELECT respondent_key,
                    max(q1) FILTER (WHERE wave = 'Apr') AS q1_apr, max(q1) FILTER (WHERE wave = 'Oct') AS q1_oct,
                    max(is_promoter) FILTER (WHERE wave = 'Apr') - max(is_detractor) FILTER (WHERE wave = 'Apr') AS s_apr,
                    max(is_promoter) FILTER (WHERE wave = 'Oct') - max(is_detractor) FILTER (WHERE wave = 'Oct') AS s_oct
             FROM s GROUP BY respondent_key
             HAVING count(DISTINCT wave) = 2)
SELECT count(*) AS n,
       {_sup('count(*)', 'round(100.0 * avg(s_apr), 1)')} AS enps_apr,
       {_sup('count(*)', 'round(100.0 * avg(s_oct), 1)')} AS enps_oct,
       {_sup('count(*)', 'round(100.0 * (avg(s_oct) - avg(s_apr)), 1)')} AS enps_change,
       {_sup('count(*)', 'round(avg(q1_oct - q1_apr), 2)')} AS mean_q1_change,
       {_sup('count(*)', 'round(100.0 * avg((q1_oct < q1_apr)::INT), 1)')} AS pct_q1_down,
       {_sup('count(*)', 'round(100.0 * avg((q1_oct = q1_apr)::INT), 1)')} AS pct_q1_same,
       {_sup('count(*)', 'round(100.0 * avg((q1_oct > q1_apr)::INT), 1)')} AS pct_q1_up,
       count(*) < {MIN_N} AS suppressed
FROM per"""
    return sql, dict(p)


def segment(dim: str, w: Where = ALL):
    """eNPS, n, invited and response rate per segment value, April and October side by side (dumbbell)."""
    d = ident(dim, SEGMENT_DIMS)
    f, p = w
    order = ORDER.get(d, d)
    sql = f"""
WITH s AS (SELECT * FROM v_survey WHERE {f}),
     i AS (SELECT * FROM v_invited WHERE {f}),
     inv AS (SELECT {d} AS segment, min({order}) AS sort_key,
                    count(*) FILTER (WHERE wave = 'Apr') AS invited_apr, count(*) FILTER (WHERE wave = 'Oct') AS invited_oct
             FROM i GROUP BY {d}),
     sv AS (SELECT {d} AS segment,
                   count(*) FILTER (WHERE wave = 'Apr') AS n_apr, count(*) FILTER (WHERE wave = 'Oct') AS n_oct,
                   100.0 * (avg(is_promoter) FILTER (WHERE wave = 'Apr') - avg(is_detractor) FILTER (WHERE wave = 'Apr')) AS e_apr,
                   100.0 * (avg(is_promoter) FILTER (WHERE wave = 'Oct') - avg(is_detractor) FILTER (WHERE wave = 'Oct')) AS e_oct
            FROM s GROUP BY {d})
SELECT inv.segment,
       inv.invited_apr, coalesce(sv.n_apr, 0) AS n_apr,
       round(100.0 * coalesce(sv.n_apr, 0) / nullif(inv.invited_apr, 0), 1) AS response_rate_apr_pct,
       {_sup('coalesce(sv.n_apr, 0)', 'round(sv.e_apr, 1)')} AS enps_apr,
       inv.invited_oct, coalesce(sv.n_oct, 0) AS n_oct,
       round(100.0 * coalesce(sv.n_oct, 0) / nullif(inv.invited_oct, 0), 1) AS response_rate_oct_pct,
       {_sup('coalesce(sv.n_oct, 0)', 'round(sv.e_oct, 1)')} AS enps_oct,
       CASE WHEN coalesce(sv.n_apr, 0) < {MIN_N} OR coalesce(sv.n_oct, 0) < {MIN_N} THEN NULL
            ELSE round(sv.e_oct - sv.e_apr, 1) END AS enps_change,
       coalesce(sv.n_apr, 0) < {MIN_N} AS suppressed_apr,
       coalesce(sv.n_oct, 0) < {MIN_N} AS suppressed_oct,
       coalesce(100.0 * coalesce(sv.n_apr, 0) / nullif(inv.invited_apr, 0) < {LOW_RESPONSE_PCT}, false) AS low_response_apr,
       coalesce(100.0 * coalesce(sv.n_oct, 0) / nullif(inv.invited_oct, 0) < {LOW_RESPONSE_PCT}, false) AS low_response_oct
FROM inv LEFT JOIN sv USING (segment)
ORDER BY inv.sort_key, inv.segment"""
    return sql, dict(p)


def _drivers_long(f: str) -> str:
    parts = [f"SELECT wave, '{q.upper()}' AS driver, '{label}' AS label, {q} AS score, q1 FROM s"
             for q, label in DRIVERS.items()]
    return f"WITH s AS (SELECT * FROM v_survey WHERE {f}), u AS ({' UNION ALL '.join(parts)})"


def drivers(w: Where = ALL):
    """Q2-Q6 per wave: n answering, mean (1-5), % favourable (4-5). Blank answers excluded per question."""
    f, p = w
    sql = f"""
{_drivers_long(f)}
SELECT driver, label, wave, count(score) AS n,
       {_sup('count(score)', 'round(avg(score), 2)')} AS mean_score,
       {_sup('count(score)', 'round(100.0 * avg((score >= 4)::INT), 1)')} AS pct_favourable,
       count(score) < {MIN_N} AS suppressed
FROM u GROUP BY driver, label, wave
ORDER BY driver, {WAVE_ORDER}"""
    return sql, dict(p)


def driver_importance(w: Where = ALL, wave: str = "Oct"):
    """Per driver in one wave: correlation with Q1 (importance, x) vs mean score (y), for the 2x2 chart."""
    f, p = w
    sql = f"""
{_drivers_long(f)}
SELECT driver, label, count(score) AS n,
       {_sup('count(score)', 'round(corr(score, q1), 3)')} AS corr_with_q1,
       {_sup('count(score)', 'round(avg(score), 2)')} AS mean_score,
       {_sup('count(score)', 'round(100.0 * avg((score >= 4)::INT), 1)')} AS pct_favourable,
       count(score) < {MIN_N} AS suppressed
FROM u WHERE wave = $imp_wave
GROUP BY driver, label ORDER BY driver"""
    return sql, merge(p, {"imp_wave": wave})


def heatmap(row: str, col: str, w: Where = ALL, wave: str = "Oct"):
    """eNPS per (row x col) cell in one wave, e.g. thread x function."""
    r, c = ident(row, SEGMENT_DIMS), ident(col, SEGMENT_DIMS)
    if r == c:
        raise ValueError("row and col must differ")
    f, p = w
    sql = f"""
WITH s AS (SELECT * FROM v_survey WHERE {f} AND wave = $hm_wave)
SELECT {r} AS row_value, {c} AS col_value, count(*) AS n,
       {_sup('count(*)', ENPS)} AS enps,
       count(*) < {MIN_N} AS suppressed
FROM s GROUP BY {r}, {c}
ORDER BY min({ORDER.get(r, r)}), {r}, min({ORDER.get(c, c)}), {c}"""
    return sql, merge(p, {"hm_wave": wave})


def themes(w: Where = ALL):
    """Comment themes by wave: comments per theme, % of respondents in the wave, % of comments."""
    f, p = w
    sql = f"""
WITH s AS (SELECT * FROM v_survey WHERE {f}),
     base AS (SELECT wave, count(*) AS respondents, count(comment_theme) AS commenters FROM s GROUP BY wave),
     t AS (SELECT wave, comment_theme AS theme, count(*) AS comments FROM s WHERE comment_theme IS NOT NULL GROUP BY wave, comment_theme)
SELECT t.wave, t.theme, base.respondents AS n, base.commenters,
       {_sup('base.respondents', 't.comments')} AS comments,
       {_sup('base.respondents', 'round(100.0 * t.comments / base.respondents, 1)')} AS pct_of_respondents,
       {_sup('base.respondents', 'round(100.0 * t.comments / base.commenters, 1)')} AS pct_of_comments,
       base.respondents < {MIN_N} AS suppressed
FROM t JOIN base USING (wave)
ORDER BY CASE t.wave WHEN 'Apr' THEN 1 ELSE 2 END, t.comments DESC, t.theme"""
    return sql, dict(p)


def respondents_who_exited(w: Where = ALL):
    """April respondents by NPS group: % who exited after the wave (and voluntary / regrettable shares)."""
    f, p = w
    sql = f"""
WITH s AS (SELECT * FROM v_survey WHERE {f} AND wave = 'Apr')
SELECT nps_group, count(*) AS n,
       {_sup('count(*)', 'sum(exited_after_wave::INT)')} AS exited,
       {_sup('count(*)', 'round(100.0 * avg(exited_after_wave::INT), 1)')} AS pct_exited,
       {_sup('count(*)', "round(100.0 * avg((exit_type_after_wave = 'Voluntary')::INT), 1)")} AS pct_voluntary_exit,
       {_sup('count(*)', 'round(100.0 * avg(regrettable_after_wave::INT), 1)')} AS pct_regrettable_exit,
       count(*) < {MIN_N} AS suppressed
FROM s GROUP BY nps_group
ORDER BY CASE nps_group WHEN 'Detractor' THEN 1 WHEN 'Passive' THEN 2 ELSE 3 END"""
    return sql, dict(p)


def non_response_bias(dim: str | None = "thread", w: Where = ALL):
    """Non-response bias check. Panel-eligible people only (invited to both waves AND answered in April):
    their APRIL eNPS, split by whether they also answered in October. If October non-respondents were less
    positive in April than October respondents, the October eNPS is likely flattered by who chose to answer."""
    seg = "'All'" if dim is None else ident(dim, SEGMENT_DIMS)
    order = None if dim is None else ORDER.get(dim, dim)
    f, p = w
    e_resp = "100.0 * (avg(is_promoter) FILTER (WHERE responded_both_waves) - avg(is_detractor) FILTER (WHERE responded_both_waves))"
    e_non = "100.0 * (avg(is_promoter) FILTER (WHERE NOT responded_both_waves) - avg(is_detractor) FILTER (WHERE NOT responded_both_waves))"
    n_resp = "count(*) FILTER (WHERE responded_both_waves)"
    n_non = "count(*) FILTER (WHERE NOT responded_both_waves)"
    sql = f"""
WITH s AS (SELECT * FROM v_survey WHERE {f} AND wave = 'Apr' AND invited_both_waves)
SELECT {seg} AS segment,
       count(*) AS n_eligible,
       {n_resp} AS n_oct_respondents,
       {n_non} AS n_oct_nonrespondents,
       round(100.0 * {n_resp} / count(*), 1) AS oct_response_rate_pct,
       {_sup(n_resp, f'round({e_resp}, 1)')} AS apr_enps_oct_respondents,
       {_sup(n_non, f'round({e_non}, 1)')} AS apr_enps_oct_nonrespondents,
       CASE WHEN {n_resp} < {MIN_N} OR {n_non} < {MIN_N} THEN NULL
            ELSE round(({e_non}) - ({e_resp}), 1) END AS gap_nonresp_minus_resp,
       {n_resp} < {MIN_N} OR {n_non} < {MIN_N} AS suppressed,
       100.0 * {n_resp} / count(*) < {LOW_RESPONSE_PCT} AS low_response
FROM s GROUP BY {seg}
{"" if dim is None else f"ORDER BY min({order}), {seg}"}"""
    return sql, dict(p)


ALL_METRICS = {"kpis": kpis, "by_wave": by_wave, "panel": panel, "drivers": drivers,
               "driver_importance": driver_importance, "themes": themes, "respondents_who_exited": respondents_who_exited,
               "non_response_bias": non_response_bias}
