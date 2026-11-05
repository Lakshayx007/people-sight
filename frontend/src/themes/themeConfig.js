import * as echarts from 'echarts';

/**
 * ECharts themes, registered before React renders.
 * One accent colour; April / passive = neutral grey; negative = red, used only for bad outcomes.
 */
export const PALETTE = {
  light: {
    accent: '#2563EB', accentMid: '#60A5FA', accentSoft: '#BFDBFE', grey: '#9CA3AF', greyLight: '#E5E7EB',
    negative: '#DC2626', negativeSoft: '#FCA5A5', text: '#111827', muted: '#6B7280', border: '#E5E7EB',
    suppressed: '#D1D5DB', surface: '#FFFFFF', warn: '#B45309', zero: '#F3F4F6',
  },
  dark: {
    accent: '#60A5FA', accentMid: '#3B82F6', accentSoft: '#1E3A8A', grey: '#6B7280', greyLight: '#374151',
    negative: '#F87171', negativeSoft: '#7F1D1D', text: '#E5E7EB', muted: '#9CA3AF', border: '#2A303B',
    suppressed: '#4B5563', surface: '#161A22', warn: '#FBBF24', zero: '#1F2937',
  },
};

function build(p, dark) {
  const axis = {
    axisLine: { lineStyle: { color: p.border } },
    axisTick: { show: false },
    axisLabel: { color: p.muted, fontSize: 11 },
    splitLine: { lineStyle: { color: p.border, type: 'dashed' } },
    nameTextStyle: { color: p.muted, fontSize: 11 },
  };
  return {
    darkMode: dark,
    color: [p.accent, p.grey, p.negative, p.accentMid, p.accentSoft],
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'Inter, system-ui, sans-serif', color: p.text },
    title: { textStyle: { color: p.text }, subtextStyle: { color: p.muted } },
    legend: { textStyle: { color: p.muted, fontSize: 11 }, icon: 'circle', itemWidth: 9, itemHeight: 9 },
    tooltip: {
      backgroundColor: p.surface, borderColor: p.border, borderWidth: 1,
      textStyle: { color: p.text, fontSize: 12 }, extraCssText: 'box-shadow: 0 6px 24px rgba(0,0,0,.12); border-radius: 8px;',
    },
    categoryAxis: { ...axis, splitLine: { show: false } },
    valueAxis: axis,
  };
}

export function registerAllThemes() {
  echarts.registerTheme('pa-light', build(PALETTE.light, false));
  echarts.registerTheme('pa-dark', build(PALETTE.dark, true));
}
