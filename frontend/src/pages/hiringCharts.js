// ECharts option builders for the Hiring page. They only place API values; no metric is calculated here.
import { fmtInt, fmtPct, isNum, truncate } from '../lib/format';

const tipRow = (label, value) => `<div style="display:flex;justify-content:space-between;gap:16px"><span style="opacity:.7">${label}</span><b>${value}</b></div>`;
const tipHead = (t) => `<div style="font-weight:600;margin-bottom:4px">${t}</div>`;
const MONTHS = { '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr', '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug', '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec' };
export const monthLabel = (m) => (m ? `${MONTHS[m.slice(5, 7)]} ${m.slice(2, 4)}` : '');
const days = (v) => (isNum(v) ? `${Number.isInteger(v) ? v : v.toFixed(1)} d` : '–');

/** (1) Monthly: reqs raised (bars) vs offers accepted and joins (lines). */
export function monthlyOption(rows, p) {
  const cats = rows.map((r) => monthLabel(r.month));
  return {
    grid: { left: 30, right: 16, top: 34, bottom: 30, containLabel: true },
    legend: { top: 0, right: 0 },
    tooltip: {
      trigger: 'axis',
      formatter: (ps) => {
        const r = rows[ps[0].dataIndex];
        return tipHead(monthLabel(r.month)) + tipRow('Reqs raised', fmtInt(r.reqs_raised)) + tipRow('Offers accepted', fmtInt(r.offers_accepted))
          + tipRow('Joins', fmtInt(r.joins)) + '<div style="margin-top:4px;opacity:.6;font-size:11px">Click to filter to reqs raised this month</div>';
      },
    },
    xAxis: { type: 'category', data: cats, triggerEvent: true },
    yAxis: { type: 'value', name: 'Count per month', nameLocation: 'middle', nameGap: 32, minInterval: 1 },
    series: [
      { type: 'bar', name: 'Reqs raised', data: rows.map((r) => r.reqs_raised), barMaxWidth: 26, itemStyle: { color: p.greyLight, borderRadius: [3, 3, 0, 0] },
        label: { show: true, position: 'top', fontSize: 10, color: p.muted } },
      { type: 'line', name: 'Offers accepted', data: rows.map((r) => r.offers_accepted), smooth: false, symbolSize: 7, lineStyle: { width: 2.5, color: p.accent }, itemStyle: { color: p.accent } },
      { type: 'line', name: 'Joins', data: rows.map((r) => r.joins), symbolSize: 7, lineStyle: { width: 2, type: 'dashed', color: p.accentMid }, itemStyle: { color: p.accentMid } },
    ],
  };
}

/** (2) Funnel: candidates reaching each stage, with conversion from the previous stage. */
export function funnelOption(rows, p, { mobile }) {
  return {
    grid: { left: 8, right: mobile ? 92 : 128, top: 8, bottom: 26, containLabel: true },
    tooltip: {
      trigger: 'item',
      formatter: (prm) => {
        const r = rows[prm.dataIndex];
        return tipHead(r.stage) + tipRow('Candidates (n)', fmtInt(r.candidates)) + tipRow('% of previous stage', fmtPct(r.pct_of_previous)) + tipRow('% of applicants', fmtPct(r.pct_of_applied));
      },
    },
    xAxis: { type: 'log', name: 'Candidates (log scale)', nameLocation: 'middle', nameGap: 24, min: 1, axisLabel: { formatter: (v) => fmtInt(v) } },
    yAxis: { type: 'category', data: rows.map((r) => r.stage), inverse: true, axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar', barMaxWidth: 18, data: rows.map((r) => Math.max(r.candidates, 1)),
      itemStyle: { color: p.accent, borderRadius: [0, 3, 3, 0] },
      label: {
        show: true, position: 'right', fontSize: 10, color: p.muted,
        formatter: (prm) => { const r = rows[prm.dataIndex]; return isNum(r.pct_of_previous) ? `${fmtInt(r.candidates)} · ${r.pct_of_previous}%` : fmtInt(r.candidates); },
      },
    }],
  };
}

/** (3) Median days between consecutive stages. */
export function stageTimeOption(rows, p) {
  return {
    grid: { left: 8, right: 54, top: 8, bottom: 26, containLabel: true },
    tooltip: {
      trigger: 'item',
      formatter: (prm) => {
        const r = rows[prm.dataIndex];
        return tipHead(r.transition) + tipRow('Median', days(r.median_days)) + tipRow('75th percentile', days(r.p75_days)) + tipRow('n (candidates with both dates)', fmtInt(r.n));
      },
    },
    xAxis: { type: 'value', name: 'Median days', nameLocation: 'middle', nameGap: 24, minInterval: 1 },
    yAxis: { type: 'category', data: rows.map((r) => r.transition), inverse: true, axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar', barMaxWidth: 16, data: rows.map((r) => r.median_days),
      itemStyle: { color: p.accent, borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: 'right', fontSize: 10, color: p.muted, formatter: (prm) => days(prm.value) },
    }],
  };
}

/** (4) Median TTF by grade vs the grade's SLA. Bars over SLA are red. */
export function ttfGradeOption(rows, p) {
  const shown = rows.filter((r) => r.filled > 0);
  const over = (r) => isNum(r.median_ttf_days) && r.median_ttf_days > r.sla_days;
  return {
    grid: { left: 30, right: 12, top: 34, bottom: 26, containLabel: true },
    legend: { top: 0, right: 0, data: ['Median TTF', 'SLA'] },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (ps) => {
        const r = shown[ps[0].dataIndex];
        return tipHead(`Grade ${r.grade}`) + tipRow('Median TTF', days(r.median_ttf_days)) + tipRow('75th percentile', days(r.p75_ttf_days))
          + tipRow('SLA', days(r.sla_days)) + tipRow('Filled within SLA', `${fmtPct(r.pct_within_sla)} (${fmtInt(r.filled - r.breached)} of ${fmtInt(r.filled)})`)
          + tipRow('Reqs raised', fmtInt(r.reqs)) + '<div style="margin-top:4px;opacity:.6;font-size:11px">Click to filter to this grade</div>';
      },
    },
    xAxis: { type: 'category', data: shown.map((r) => r.grade), triggerEvent: true },
    yAxis: { type: 'value', name: 'Days (raised → offer accepted)', nameLocation: 'middle', nameGap: 32 },
    series: [
      {
        type: 'bar', name: 'Median TTF', barMaxWidth: 28,
        data: shown.map((r) => ({ value: r.median_ttf_days, itemStyle: { color: over(r) ? p.negative : p.accent, borderRadius: [3, 3, 0, 0] } })),
        label: { show: true, position: 'top', fontSize: 10, color: p.muted, formatter: (prm) => `${fmtPct(shown[prm.dataIndex].pct_within_sla, 0)}` },
      },
      {
        type: 'line', name: 'SLA', step: 'middle', data: shown.map((r) => r.sla_days), symbol: 'none',
        lineStyle: { color: p.text, type: 'dashed', width: 1.5 }, itemStyle: { color: p.text }, z: 5,
      },
    ],
  };
}

/** (7) Slowest R1 interviewers by median feedback turnaround. */
export function interviewersOption(rows, p, { mobile }) {
  return {
    grid: { left: 8, right: 70, top: 8, bottom: 26, containLabel: true },
    tooltip: {
      trigger: 'item',
      formatter: (prm) => {
        const r = rows[prm.dataIndex];
        return tipHead(r.interviewer) + `<div style="opacity:.7;margin-bottom:4px">${r.designation} · ${r.thread}</div>`
          + tipRow('Median feedback time', days(r.median_feedback_days)) + tipRow('Mean', days(r.mean_feedback_days))
          + tipRow('Over 2 days', fmtPct(r.pct_over_2_days)) + tipRow('Interviews with feedback (n)', fmtInt(r.n)) + tipRow('Reqs', fmtInt(r.reqs));
      },
    },
    xAxis: { type: 'value', name: 'Median days from R1 interview to feedback', nameLocation: 'middle', nameGap: 24, minInterval: 1 },
    yAxis: { type: 'category', data: rows.map((r) => r.interviewer), inverse: true, axisLabel: { fontSize: 11, formatter: (v) => truncate(v, mobile ? 14 : 22) } },
    series: [{
      type: 'bar', barMaxWidth: 12,
      data: rows.map((r) => ({ value: r.median_feedback_days, itemStyle: { color: r.median_feedback_days > 2 ? p.negative : p.accent, borderRadius: [0, 3, 3, 0] } })),
      label: { show: true, position: 'right', fontSize: 10, color: p.muted, formatter: (prm) => `${days(prm.value)} · n=${rows[prm.dataIndex].n}` },
    }],
  };
}

/** (8) Offer decline rate by offered / expected CTC band. */
export function offersOption(rows, p) {
  return {
    grid: { left: 30, right: 12, top: 24, bottom: 30, containLabel: true },
    tooltip: {
      trigger: 'item',
      formatter: (prm) => {
        const r = rows[prm.dataIndex];
        return tipHead(`Offered ÷ expected CTC ${r.ratio_band}`) + tipRow('Declined', `${fmtPct(r.decline_rate_pct)} (${fmtInt(r.declined)} of ${fmtInt(r.offers)})`)
          + tipRow('Accepted', fmtInt(r.accepted)) + tipRow('Median offer ÷ budget max', isNum(r.median_offer_to_budget) ? r.median_offer_to_budget.toFixed(2) : '–');
      },
    },
    xAxis: { type: 'category', data: rows.map((r) => r.ratio_band), name: 'Offered CTC ÷ candidate’s expected CTC', nameLocation: 'middle', nameGap: 26 },
    yAxis: { type: 'value', name: '% of offers declined', nameLocation: 'middle', nameGap: 34, axisLabel: { formatter: '{value}%' } },
    series: [{
      type: 'bar', barMaxWidth: 44,
      data: rows.map((r) => ({ value: r.decline_rate_pct, itemStyle: { color: p.accent, borderRadius: [3, 3, 0, 0] } })),
      label: { show: true, position: 'top', fontSize: 10, color: p.muted, formatter: (prm) => { const r = rows[prm.dataIndex]; return `${r.decline_rate_pct}% (${r.declined}/${r.offers})`; } },
    }],
  };
}

const BUCKET_ORDER = ['Within SLA', '1-15 days over', '16-30 days over', '31-60 days over', '60+ days over'];

/** (9) Open reqs by how far past SLA they are on 31-Oct. */
export function agingOption(rows, p) {
  const byB = Object.fromEntries(rows.map((r) => [r.aging_bucket, r.open_reqs]));
  const cats = BUCKET_ORDER.filter((b) => b in byB);
  return {
    grid: { left: 28, right: 12, top: 24, bottom: 38, containLabel: true },
    tooltip: { trigger: 'item', formatter: (prm) => tipHead(prm.name) + tipRow('Open reqs (n)', fmtInt(prm.value)) },
    xAxis: { type: 'category', data: cats, axisLabel: { fontSize: 10, interval: 0, lineHeight: 12, formatter: (v) => v.replace(' days over', '\ndays over') }, name: 'Age on 31-Oct vs SLA', nameLocation: 'middle', nameGap: 34 },
    yAxis: { type: 'value', name: 'Open reqs', nameLocation: 'middle', nameGap: 30, minInterval: 1 },
    series: [{
      type: 'bar', barMaxWidth: 40,
      data: cats.map((b) => ({ value: byB[b], itemStyle: { color: b === 'Within SLA' ? p.accent : p.negative, opacity: b === 'Within SLA' ? 1 : 0.55 + 0.1 * BUCKET_ORDER.indexOf(b), borderRadius: [3, 3, 0, 0] } })),
      label: { show: true, position: 'top', fontSize: 10, color: p.muted },
    }],
  };
}
