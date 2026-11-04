// ECharts option builders for the Employee Sentiment page.
// They only place API values on charts; no metric is calculated here.
import { fmtInt, fmtPct, fmtSigned, isNum, truncate } from '../lib/format';

const WARN = '⚠';
const tipRow = (label, value) => `<div style="display:flex;justify-content:space-between;gap:16px"><span style="opacity:.7">${label}</span><b>${value}</b></div>`;
const tipHead = (t) => `<div style="font-weight:600;margin-bottom:4px">${t}</div>`;
const scoreOr = (v, suppressed, f = fmtSigned) => (suppressed ? 'n&lt;5' : f(v));
const lowNote = '<div style="margin-top:4px;color:#B45309">⚠ Low response, read with caution</div>';

/** (1) Dumbbell: eNPS April (grey) → October (accent) per segment. */
export function dumbbellOption(rows, p, { mobile }) {
  const cats = rows.map((r) => r.segment);
  const byName = Object.fromEntries(rows.map((r) => [r.segment, r]));
  const low = (r) => r && (r.low_response_apr || r.low_response_oct);
  const both = rows.map((r, i) => (isNum(r.enps_apr) && isNum(r.enps_oct) ? [r.enps_apr, r.enps_oct, i] : null)).filter(Boolean);
  const dot = (key) => rows.filter((r) => isNum(r[key])).map((r) => ({ value: [r[key], r.segment], seg: r.segment }));
  const hidden = rows.filter((r) => !isNum(r.enps_oct) && !isNum(r.enps_apr)).map((r) => ({ value: [0, r.segment], seg: r.segment }));
  const partial = rows.filter((r) => isNum(r.enps_oct) !== isNum(r.enps_apr));

  return {
    grid: { left: 8, right: 24, top: 30, bottom: 34, containLabel: true },
    legend: { top: 0, right: 0, data: ['April', 'October'] },
    tooltip: {
      trigger: 'item',
      formatter: (prm) => {
        const r = byName[prm.data?.seg];
        if (!r) return '';
        return tipHead(r.segment)
          + tipRow('April eNPS', `${scoreOr(r.enps_apr, r.suppressed_apr)} (n = ${fmtInt(r.n_apr)})`)
          + tipRow('October eNPS', `${scoreOr(r.enps_oct, r.suppressed_oct)} (n = ${fmtInt(r.n_oct)})`)
          + tipRow('Change', isNum(r.enps_change) ? `${fmtSigned(r.enps_change)} pts` : '—')
          + tipRow('Response rate Apr / Oct', `${fmtPct(r.response_rate_apr_pct)} / ${fmtPct(r.response_rate_oct_pct)}`)
          + (low(r) ? lowNote : '') + '<div style="margin-top:4px;opacity:.6;font-size:11px">Click to drill down</div>';
      },
    },
    xAxis: { type: 'value', name: 'eNPS (points, −100 to +100)', nameLocation: 'middle', nameGap: 24, scale: true },
    yAxis: {
      type: 'category', data: cats, inverse: true, triggerEvent: true,
      axisLabel: {
        width: mobile ? 92 : 150, overflow: 'truncate', fontSize: 11,
        formatter: (v) => (low(byName[v]) ? `{w|${WARN}} ${truncate(v, mobile ? 12 : 22)}` : truncate(v, mobile ? 14 : 24)),
        rich: { w: { color: p.warn, fontWeight: 600 } },
      },
    },
    series: [
      {
        type: 'custom', name: 'change', silent: true, z: 1, tooltip: { show: false }, encode: { x: [0, 1], y: 2 },
        renderItem: (params, api) => {
          const a = api.coord([api.value(0), api.value(2)]);
          const b = api.coord([api.value(1), api.value(2)]);
          return { type: 'line', shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, style: { stroke: p.greyLight, lineWidth: 4 } };
        },
        data: both,
      },
      {
        type: 'scatter', name: 'April', data: dot('enps_apr'), symbolSize: 11, itemStyle: { color: p.grey }, z: 2,
        markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: p.muted, type: 'solid', opacity: 0.35 }, data: [{ xAxis: 0 }] },
      },
      { type: 'scatter', name: 'October', data: dot('enps_oct'), symbolSize: 13, itemStyle: { color: p.accent }, z: 3 },
      {
        type: 'scatter', name: 'n<5', data: hidden, symbolSize: 1, itemStyle: { opacity: 0 }, z: 4,
        label: { show: true, formatter: 'n<5', color: p.muted, backgroundColor: p.zero, padding: [2, 5], borderRadius: 3, fontSize: 10 },
      },
      {
        type: 'scatter', name: 'partial', symbolSize: 1, itemStyle: { opacity: 0 }, z: 4,
        data: partial.map((r) => ({ value: [isNum(r.enps_oct) ? r.enps_oct : r.enps_apr, r.segment], seg: r.segment })),
        label: {
          show: true, position: 'right', distance: 10, color: p.muted, fontSize: 10,
          formatter: (prm) => (isNum(byName[prm.data.seg].enps_apr) ? 'Oct n<5' : (byName[prm.data.seg].n_apr === 0 ? 'not in April' : 'Apr n<5')),
        },
      },
    ],
  };
}

const DRIVER_LABEL = (r) => `${r.driver} · ${r.label}`;

/** (2) Driver scores: % favourable, April vs October. */
export function driversOption(rows, p, { mobile }) {
  const drivers = [...new Set(rows.map(DRIVER_LABEL))];
  const get = (d, w) => rows.find((r) => DRIVER_LABEL(r) === d && r.wave === w);
  const series = ['Apr', 'Oct'].map((w) => ({
    type: 'bar', name: w === 'Apr' ? 'April' : 'October', barMaxWidth: 14, barGap: '25%',
    itemStyle: { color: w === 'Apr' ? p.grey : p.accent, borderRadius: [0, 3, 3, 0] },
    label: { show: true, position: 'right', fontSize: 10, color: p.muted, formatter: (prm) => (prm.data.r?.suppressed ? 'n<5' : `${prm.value}%`) },
    data: drivers.map((d) => { const r = get(d, w); return { value: r?.pct_favourable ?? null, r }; }),
  }));
  return {
    grid: { left: 8, right: 40, top: 30, bottom: 34, containLabel: true },
    legend: { top: 0, right: 0 },
    tooltip: {
      trigger: 'item',
      formatter: (prm) => {
        const r = prm.data.r;
        if (!r) return '';
        return tipHead(`${DRIVER_LABEL(r)} — ${prm.seriesName}`)
          + tipRow('% favourable (4–5)', scoreOr(r.pct_favourable, r.suppressed, fmtPct))
          + tipRow('Mean score (1–5)', scoreOr(r.mean_score, r.suppressed, (v) => (isNum(v) ? v.toFixed(2) : '—')))
          + tipRow('n answering', fmtInt(r.n));
      },
    },
    xAxis: { type: 'value', max: 100, name: '% favourable (score 4–5)', nameLocation: 'middle', nameGap: 24, axisLabel: { formatter: '{value}%' } },
    yAxis: { type: 'category', data: drivers, inverse: true, axisLabel: { width: mobile ? 100 : 150, overflow: 'truncate' } },
    series,
  };
}

/** (3) 2x2: importance (correlation with Q1) vs October mean score. */
export function quadrantOption(rows, p) {
  const pts = rows.filter((r) => isNum(r.corr_with_q1)).map((r) => ({ value: [r.corr_with_q1, r.mean_score], r, name: r.label }));
  // Stagger labels of points that sit almost on top of each other (layout only, no metric maths).
  const xr = Math.max(...pts.map((d) => d.value[0])) - Math.min(...pts.map((d) => d.value[0])) || 1;
  const yr = Math.max(...pts.map((d) => d.value[1])) - Math.min(...pts.map((d) => d.value[1])) || 1;
  const order = pts.map((d, i) => i).sort((a, b) => pts[b].value[1] - pts[a].value[1] || pts[a].value[0] - pts[b].value[0]);
  const dy = {};
  order.forEach((i, k) => {
    const near = order.slice(0, k).filter((j) => Math.abs(pts[j].value[0] - pts[i].value[0]) / xr < 0.35
      && Math.abs(pts[j].value[1] - pts[i].value[1]) / yr < 0.12);
    dy[i] = near.length ? Math.max(...near.map((j) => dy[j])) + 15 : 0;
  });
  return {
    grid: { left: 8, right: 120, top: 24, bottom: 40, containLabel: true },
    tooltip: {
      trigger: 'item',
      formatter: (prm) => {
        const r = prm.data.r;
        return tipHead(`${r.driver} · ${r.label}`) + tipRow('Correlation with Q1', r.corr_with_q1.toFixed(3))
          + tipRow('Mean score (1–5)', r.mean_score.toFixed(2)) + tipRow('% favourable', fmtPct(r.pct_favourable)) + tipRow('n', fmtInt(r.n));
      },
    },
    xAxis: { type: 'value', scale: true, name: 'Importance: correlation with Q1 (eNPS question)', nameLocation: 'middle', nameGap: 26, axisLabel: { formatter: (v) => v.toFixed(2) } },
    yAxis: { type: 'value', scale: true, name: 'Mean score (1–5)', nameLocation: 'middle', nameGap: 36, axisLabel: { formatter: (v) => v.toFixed(2) } },
    series: [{
      type: 'scatter', symbolSize: 14, itemStyle: { color: p.accent }, data: pts,
      label: { show: true, formatter: (prm) => prm.data.name, position: 'right', fontSize: 11, color: p.text },
      labelLine: { show: true, lineStyle: { color: p.muted, opacity: 0.5 } },
      labelLayout: (prm) => ({ dy: dy[prm.dataIndex] || 0 }),
      markLine: {
        silent: true, symbol: 'none', lineStyle: { type: 'dashed', color: p.muted, opacity: 0.6 },
        label: { show: false }, data: [{ type: 'average', valueDim: 'x' }, { type: 'average', valueDim: 'y' }],
      },
    }],
    graphic: [{ type: 'text', right: 126, bottom: 62, style: { text: 'Fix first ↘', fill: p.negative, fontSize: 11, fontWeight: 600 } }],
  };
}

/** (4) Heatmap: eNPS for row x col (e.g. thread x function). Suppressed cells grey "n<5". */
export function heatmapOption(rows, p, { mobile }) {
  const xs = [...new Set(rows.map((r) => r.col_value))];
  const ys = [...new Set(rows.map((r) => r.row_value))];
  const ok = rows.filter((r) => !r.suppressed).map((r) => ({ value: [xs.indexOf(r.col_value), ys.indexOf(r.row_value), r.enps], r }));
  const sup = rows.filter((r) => r.suppressed).map((r) => ({ value: [xs.indexOf(r.col_value), ys.indexOf(r.row_value), 0], r }));
  const tip = (prm) => {
    const r = prm.data.r;
    return tipHead(`${r.row_value} × ${r.col_value}`) + tipRow('eNPS', scoreOr(r.enps, r.suppressed)) + tipRow('n', fmtInt(r.n))
      + '<div style="margin-top:4px;opacity:.6;font-size:11px">Click to drill down</div>';
  };
  return {
    grid: { left: 8, right: 12, top: 6, bottom: 74, containLabel: true },
    tooltip: { trigger: 'item', formatter: tip },
    xAxis: { type: 'category', data: xs, splitArea: { show: false }, axisLabel: { rotate: 35, interval: 0, fontSize: 10, formatter: (v) => truncate(v, 16) } },
    yAxis: { type: 'category', data: ys, inverse: true, axisLabel: { fontSize: 11, formatter: (v) => truncate(v, mobile ? 12 : 18) } },
    visualMap: {
      seriesIndex: 0, min: -50, max: 50, orient: 'horizontal', left: 'center', bottom: 0, itemWidth: 10, itemHeight: 140,
      calculable: false, text: ['+50', '−50'], textStyle: { color: p.muted, fontSize: 10 },
      inRange: { color: [p.negative, p.zero, p.accent] },
    },
    series: [
      { type: 'heatmap', data: ok, itemStyle: { borderColor: p.surface, borderWidth: 2, borderRadius: 3 },
        label: { show: true, fontSize: 10, color: p.text, formatter: (prm) => fmtSigned(prm.data.value[2], 0) },
        emphasis: { itemStyle: { borderColor: p.text, borderWidth: 1 } } },
      { type: 'heatmap', data: sup, itemStyle: { color: p.zero, borderColor: p.surface, borderWidth: 2, borderRadius: 3 },
        label: { show: true, fontSize: 9, color: p.muted, formatter: 'n<5' } },
    ],
  };
}

const THEMES = ['Manager', 'Pay', 'Growth', 'Workload', 'Onboarding', 'Positive'];

/** (5) Comment themes: % of respondents mentioning each theme, by wave. */
export function themesOption(rows, p) {
  const get = (t, w) => rows.find((r) => r.theme === t && r.wave === w);
  return {
    grid: { left: 8, right: 36, top: 30, bottom: 34, containLabel: true },
    legend: { top: 0, right: 0 },
    tooltip: {
      trigger: 'item',
      formatter: (prm) => {
        const r = prm.data.r;
        if (!r) return '';
        return tipHead(`${r.theme} — ${prm.seriesName}`) + tipRow('% of respondents', scoreOr(r.pct_of_respondents, r.suppressed, fmtPct))
          + tipRow('Comments', r.suppressed ? 'n&lt;5' : fmtInt(r.comments)) + tipRow('Respondents (n)', fmtInt(r.n));
      },
    },
    xAxis: { type: 'value', name: '% of respondents', nameLocation: 'middle', nameGap: 24, axisLabel: { formatter: '{value}%' } },
    yAxis: { type: 'category', data: THEMES, inverse: true },
    series: ['Apr', 'Oct'].map((w) => ({
      type: 'bar', name: w === 'Apr' ? 'April' : 'October', barMaxWidth: 12,
      itemStyle: { color: w === 'Apr' ? p.grey : p.accent, borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: 'right', fontSize: 10, color: p.muted, formatter: (prm) => (prm.data.r?.suppressed ? 'n<5' : isNum(prm.value) ? `${prm.value}%` : '') },
      data: THEMES.map((t) => { const r = get(t, w); return { value: r?.pct_of_respondents ?? null, r }; }),
    })),
  };
}

/** (6) Promoters / passives / detractors, 100% stacked by wave. */
export function mixOption(rows, p) {
  const cats = rows.map((r) => (r.wave === 'Apr' ? 'April' : 'October'));
  const mk = (name, key, color) => ({
    type: 'bar', name, stack: 'mix', barMaxWidth: 40, itemStyle: { color },
    label: { show: true, color: key === 'pct_passives' ? p.text : '#fff', fontSize: 11, fontWeight: 600, formatter: (prm) => (isNum(prm.value) && prm.value >= 8 ? `${Math.round(prm.value)}%` : '') },
    data: rows.map((r) => ({ value: r[key], r })),
  });
  return {
    grid: { left: 8, right: 16, top: 30, bottom: 34, containLabel: true },
    legend: { top: 0, right: 0 },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (ps) => {
        const r = ps[0].data.r;
        if (r.suppressed) return tipHead(ps[0].axisValue) + `n&lt;5 (n = ${r.n})`;
        return tipHead(`${ps[0].axisValue} — eNPS ${fmtSigned(r.enps)}`) + tipRow('Promoters (9–10)', fmtPct(r.pct_promoters))
          + tipRow('Passives (7–8)', fmtPct(r.pct_passives)) + tipRow('Detractors (0–6)', fmtPct(r.pct_detractors))
          + tipRow('Respondents (n)', fmtInt(r.n)) + tipRow('Response rate', fmtPct(r.response_rate_pct)) + (r.low_response ? lowNote : '');
      },
    },
    xAxis: { type: 'value', max: 100, name: '% of respondents', nameLocation: 'middle', nameGap: 24, axisLabel: { formatter: '{value}%' } },
    yAxis: { type: 'category', data: cats, inverse: true, triggerEvent: true },
    series: [mk('Detractors', 'pct_detractors', p.negative), mk('Passives', 'pct_passives', p.greyLight), mk('Promoters', 'pct_promoters', p.accent)],
  };
}

/** (7) April respondents who later exited, by April NPS group. */
export function exitsOption(rows, p) {
  const cats = rows.map((r) => `${r.nps_group}s`);
  const mk = (name, key, color) => ({
    type: 'bar', name, barMaxWidth: 18, itemStyle: { color, borderRadius: [3, 3, 0, 0] },
    label: { show: key === 'pct_exited', position: 'top', fontSize: 10, color: p.muted, formatter: (prm) => (prm.data.r.suppressed ? 'n<5' : `${prm.value}%`) },
    data: rows.map((r) => ({ value: r[key], r })),
  });
  return {
    grid: { left: 22, right: 8, top: 30, bottom: 30, containLabel: true },
    legend: { top: 0, right: 0 },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (ps) => {
        const r = ps[0].data.r;
        return tipHead(`April ${r.nps_group.toLowerCase()}s`) + tipRow('Exited later', r.suppressed ? 'n&lt;5' : `${fmtPct(r.pct_exited)} (${fmtInt(r.exited)})`)
          + tipRow('Voluntary exit', fmtPct(r.pct_voluntary_exit)) + tipRow('Regrettable exit', fmtPct(r.pct_regrettable_exit)) + tipRow('n (April respondents)', fmtInt(r.n));
      },
    },
    xAxis: { type: 'category', data: cats },
    yAxis: { type: 'value', name: '% of group who exited', nameLocation: 'middle', nameGap: 38, axisLabel: { formatter: '{value}%' } },
    series: [mk('Any exit', 'pct_exited', p.accent), mk('Voluntary', 'pct_voluntary_exit', p.accentMid), mk('Regrettable', 'pct_regrettable_exit', p.accentSoft)],
  };
}

/** (8) Non-response bias: April eNPS of people who did vs did not answer in October, by thread. */
export function nonResponseOption(rows, p, { mobile }) {
  const cats = rows.map((r) => r.segment);
  const byName = Object.fromEntries(rows.map((r) => [r.segment, r]));
  const mk = (name, key, nkey, color) => ({
    type: 'bar', name, barMaxWidth: 16, barGap: '40%', itemStyle: { color, borderRadius: [3, 3, 0, 0] },
    label: { show: !mobile, position: 'top', fontSize: 9, color: p.muted, formatter: (prm) => (isNum(prm.value) ? fmtSigned(prm.value) : 'n<5') },
    data: rows.map((r) => ({ value: r[key], r, n: r[nkey] })),
  });
  return {
    grid: { left: 8, right: 8, top: 30, bottom: 30, containLabel: true },
    legend: { top: 0, right: 0 },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (ps) => {
        const r = byName[ps[0].axisValue];
        return tipHead(`${r.segment} — April eNPS`) + tipRow('Answered October', `${scoreOr(r.apr_enps_oct_respondents, r.n_oct_respondents < 5)} (n = ${fmtInt(r.n_oct_respondents)})`)
          + tipRow('Skipped October', `${scoreOr(r.apr_enps_oct_nonrespondents, r.n_oct_nonrespondents < 5)} (n = ${fmtInt(r.n_oct_nonrespondents)})`)
          + tipRow('Gap (skipped − answered)', isNum(r.gap_nonresp_minus_resp) ? `${fmtSigned(r.gap_nonresp_minus_resp)} pts` : '—')
          + tipRow('October response rate', fmtPct(r.oct_response_rate_pct)) + (r.low_response ? lowNote : '');
      },
    },
    xAxis: {
      type: 'category', data: cats, triggerEvent: true,
      axisLabel: { interval: 0, fontSize: 10, rotate: mobile ? 30 : 0, formatter: (v) => (byName[v]?.low_response ? `{w|${WARN}} ${truncate(v, 16)}` : truncate(v, 16)), rich: { w: { color: p.warn, fontWeight: 600 } } },
    },
    yAxis: { type: 'value', name: 'April eNPS (points)', nameLocation: 'middle', nameGap: 34 },
    series: [mk('Answered October', 'apr_enps_oct_respondents', 'n_oct_respondents', p.accent), mk('Skipped October', 'apr_enps_oct_nonrespondents', 'n_oct_nonrespondents', p.grey)],
  };
}
