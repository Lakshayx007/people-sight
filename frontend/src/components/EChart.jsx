import { useMemo, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import { useTheme } from '../context/ThemeContext';

/** Thin wrapper: applies the registered theme, remounts on theme change, wires click for drill-down. */
export default function EChart({ option, height, onClick, minWidth }) {
  const { chartTheme } = useTheme();
  const ref = useRef(null);
  // Remount when the chart's categories or series sizes change (e.g. after a drill-down), so no stale hover
  // state from the previous data can survive. Same-shape updates still animate in place.
  const shape = useMemo(() => {
    const axisData = (a) => (Array.isArray(a) ? a : [a]).map((x) => (x?.data ? x.data.join('|') : '')).join('/');
    return [axisData(option?.xAxis), axisData(option?.yAxis), (option?.series || []).map((x) => x.data?.length ?? 0).join(',')].join('#');
  }, [option]);
  const onEvents = useMemo(() => (onClick ? {
    click: (e) => {
      // Clear hover / tooltip state first: the drill-down replaces this chart's data, and ECharts errors if a
      // highlighted element disappears under the mouse. Then apply the filter after ECharts finishes the click.
      const inst = ref.current?.getEchartsInstance();
      try { inst?.dispatchAction({ type: 'hideTip' }); inst?.dispatchAction({ type: 'downplay' }); } catch { /* ignore */ }
      setTimeout(() => onClick(e), 0);
    },
  } : undefined), [onClick]);
  const chart = (
    <ReactECharts
      ref={ref}
      key={`${chartTheme}:${shape}`}
      theme={chartTheme}
      option={option}
      notMerge
      onEvents={onEvents}
      style={{ height, width: '100%', minWidth }}
      opts={{ renderer: 'canvas' }}
      // expose the instance on its DOM node so automated UI checks can click exact chart points
      onChartReady={(inst) => { inst.getDom().__chart = inst; }}
    />
  );
  return minWidth ? <div className="overflow-x-auto">{chart}</div> : chart;
}
