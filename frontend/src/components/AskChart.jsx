import { useMemo } from 'react';
import EChart from './EChart';
import { useTheme } from '../context/ThemeContext';
import { fmtInt, isNum, truncate } from '../lib/format';

const N_COLS = (cols) => cols.filter((c) => c === 'n' || c.startsWith('n_') || c.endsWith('_n'));
const fmtV = (v) => (isNum(v) ? (Number.isInteger(v) ? fmtInt(v) : v.toLocaleString('en-IN', { maximumFractionDigits: 2 })) : 'n<5');

/**
 * Draws the chart Groq specified ({chart_type, x, y, series, title}) from the rows the query returned.
 * Only reshapes rows for display (long -> one series per value); never computes a metric.
 */
export default function AskChart({ spec, rows, columns, height = 260 }) {
  const { palette: p } = useTheme();
  const option = useMemo(() => build(spec, rows, columns, p), [spec, rows, columns, p]);
  if (!spec || spec.chart_type === 'table' || !rows?.length) return null;
  if (spec.chart_type === 'kpi') {
    const r = rows[0];
    return (
      <div className="flex flex-wrap gap-3">
        {spec.y.map((c) => (
          <div key={c} className="min-w-[120px] rounded-lg border border-border p-3">
            <div className="text-[11px] text-muted">{c}</div>
            <div className="text-2xl font-bold tabular-nums">{r.suppressed && !N_COLS(columns).includes(c) ? 'n<5' : fmtV(r[c])}</div>
          </div>
        ))}
      </div>
    );
  }
  return option ? <EChart option={option} height={height} /> : null;
}

function build(spec, rows, columns, p) {
  if (!spec || !rows?.length || ['table', 'kpi'].includes(spec.chart_type)) return null;
  const { chart_type: type, x, y, series } = spec;
  const nCol = N_COLS(columns)[0];
  const palette = [p.accent, p.grey, p.accentMid, p.negative, p.accentSoft, p.text];
  const tip = (r) => (r ? `${nCol && isNum(r[nCol]) ? `<br/><span style="opacity:.7">${nCol} = ${fmtInt(r[nCol])}</span>` : ''}${r.suppressed ? '<br/><span style="opacity:.7">n&lt;5: hidden for privacy</span>' : ''}` : '');

  if (type === 'pie') {
    return {
      tooltip: { trigger: 'item', formatter: (prm) => `<b>${prm.name}</b><br/>${fmtV(prm.value)} (${prm.percent}%)${tip(prm.data.r)}` },
      legend: { bottom: 0, type: 'scroll' },
      series: [{ type: 'pie', radius: ['40%', '68%'], center: ['50%', '45%'], data: rows.map((r) => ({ name: String(r[x]), value: r[y[0]], r })),
        label: { fontSize: 11, formatter: (prm) => truncate(prm.name, 14) }, color: palette }],
    };
  }
  if (type === 'scatter') {
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 30, containLabel: true },
      tooltip: { trigger: 'item', formatter: (prm) => `${x}: ${fmtV(prm.value[0])}<br/>${y[0]}: ${fmtV(prm.value[1])}${tip(prm.data.r)}` },
      xAxis: { type: 'value', name: x, nameLocation: 'middle', nameGap: 24, scale: true },
      yAxis: { type: 'value', name: y[0], scale: true },
      series: [{ type: 'scatter', symbolSize: 10, itemStyle: { color: p.accent }, data: rows.map((r) => ({ value: [r[x], r[y[0]]], r })) }],
    };
  }

  // bar / stacked_bar / line
  const cats = [...new Set(rows.map((r) => String(r[x])))];
  let sers;
  if (series) {
    const groups = [...new Set(rows.map((r) => String(r[series])))];
    sers = groups.map((g, i) => ({
      name: g,
      color: palette[i % palette.length],
      data: cats.map((c) => { const r = rows.find((row) => String(row[x]) === c && String(row[series]) === g); return { value: r ? r[y[0]] : null, r }; }),
    }));
  } else {
    sers = y.map((col, i) => ({ name: col, color: palette[i % palette.length], data: rows.map((r) => ({ value: r[col], r })) }));
  }
  const horizontal = type !== 'line' && cats.length > 6;
  const rotate = !horizontal && cats.length > 4;
  // Few vertical categories: wrap long labels onto two lines instead of cutting them off.
  const catLabel = horizontal || rotate
    ? { fontSize: 10, interval: 0, rotate: rotate ? 30 : 0, formatter: (v) => truncate(v, horizontal ? 22 : 14) }
    : { fontSize: 10, interval: 0, width: 96, overflow: 'break', lineHeight: 13 };
  const catAxis = { type: 'category', data: cats, inverse: horizontal, axisLabel: catLabel };
  const valAxis = { type: 'value', name: series ? y[0] : (y.length === 1 ? y[0] : ''), nameLocation: 'middle', nameGap: horizontal ? 24 : 40, scale: type === 'line' };
  return {
    grid: { left: horizontal ? 8 : 30, right: 24, top: sers.length > 1 ? 34 : 24, bottom: horizontal ? 30 : 8, containLabel: true },
    legend: sers.length > 1 ? { top: 0, right: 0, type: 'scroll' } : undefined,
    tooltip: { trigger: 'item', formatter: (prm) => `<b>${prm.name}</b><br/>${prm.seriesName}: ${fmtV(prm.value)}${tip(prm.data?.r)}` },
    xAxis: horizontal ? valAxis : catAxis,
    yAxis: horizontal ? catAxis : valAxis,
    series: sers.map((s) => ({
      type: type === 'line' ? 'line' : 'bar', name: s.name, data: s.data, stack: type === 'stacked_bar' ? 'all' : undefined,
      itemStyle: { color: s.color, borderRadius: type === 'line' ? 0 : 2 }, lineStyle: { color: s.color, width: 2.5 }, barMaxWidth: 22,
      label: { show: type !== 'line' && sers.length <= 2 && cats.length <= 12, position: horizontal ? 'right' : 'top', fontSize: 10, color: p.muted,
        formatter: (prm) => (prm.data?.r?.suppressed ? 'n<5' : fmtV(prm.value)) },
    })),
  };
}
