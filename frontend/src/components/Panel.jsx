import { useEffect, useState } from 'react';
import { Code2, Maximize2 } from 'lucide-react';
import ChartModal from './ChartModal';
import SqlBlock from './SqlBlock';
import { NBadge } from './Badges';
import ChartInsight from './ChartInsight';
import { api, loadAskStatus } from '../lib/api';

export const CHART_H = 300;

/**
 * Adapted from Onco-Sight's Panel (moved into its own file). Adds: n badge, Show SQL toggle, loading / error /
 * empty states, a fixed chart height so panels in a row line up, and a slot for badges (e.g. Low response).
 * `children` may be a function (height) => node so the same chart can render inside the zoom modal.
 */
export default function Panel({
  title, subtitle, n, nLabel, sql, loading, error, empty, badges, actions, children,
  className = '', height = CHART_H, footer, insightRows,
}) {
  const [showSql, setShowSql] = useState(false);
  const [zoom, setZoom] = useState(false);
  const render = (h) => (typeof children === 'function' ? children(h) : children);
  const [aiOn, setAiOn] = useState(false);
  const [insight, setInsight] = useState({ text: null, loading: false, key: null });
  useEffect(() => { if (insightRows) loadAskStatus().then((st) => setAiOn(!!st.available)); }, [insightRows]);
  const rowsKey = insightRows ? JSON.stringify(insightRows).length + ':' + (sql || '').length : null;
  const explain = async () => {
    setInsight({ text: null, loading: true, key: rowsKey });
    try {
      const r = await api.post('/chart-insight', { title, rows: (insightRows || []).slice(0, 40) }, { timeout: 45000 });
      setInsight({ text: r.data.data[0].insight, loading: false, key: rowsKey });
    } catch {
      setInsight({ text: 'Could not get a summary right now.', loading: false, key: rowsKey });
    }
  };

  let body;
  if (error) body = <State text={`Could not load: ${error}`} tone="error" />;
  else if (empty && !loading) body = <State text="No data for the current filters" />;
  else body = render(height);

  return (
    <section className={`flex min-w-0 flex-col rounded-xl border border-border bg-surface p-4 shadow-sm ${className}`}>
      <header className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold leading-snug">{title}</h3>
          {subtitle && <p className="mt-0.5 text-[11px] leading-4 text-muted">{subtitle}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          {actions}
          <NBadge n={n} label={nLabel} />
          <button
            onClick={() => setShowSql((s) => !s)}
            className={`flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${showSql ? 'border-accent text-accent' : 'border-border text-muted hover:text-primary'}`}
            title="Show the exact SQL behind this chart"
          >
            <Code2 className="h-3 w-3" /> SQL
          </button>
          <button onClick={() => setZoom(true)} className="rounded-md p-1 text-muted hover:text-accent" title="Enlarge" aria-label="Enlarge chart">
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>
      {badges && <div className="mb-2 flex flex-wrap gap-1.5">{badges}</div>}
      <div className="relative min-w-0" style={{ minHeight: height }}>
        {body}
        {loading && (
          <div className="absolute inset-0 grid place-items-center bg-surface/60">
            <div className="h-7 w-7 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          </div>
        )}
      </div>
      {footer}
      {aiOn && insightRows?.length > 0 && !loading && !error && (
        <ChartInsight insight={insight.key === rowsKey ? insight.text : null} loading={insight.loading && insight.key === rowsKey} onGenerate={explain} />
      )}
      {showSql && <SqlBlock sql={sql} />}
      <ChartModal isOpen={zoom} onClose={() => setZoom(false)} title={title} subtitle={subtitle}>
        {!error && !empty && render(Math.min(560, window.innerHeight * 0.65))}
      </ChartModal>
    </section>
  );
}

function State({ text, tone }) {
  return (
    <div className={`grid h-full min-h-[inherit] place-items-center rounded-lg border border-dashed border-border text-xs ${tone === 'error' ? 'text-negative' : 'text-muted'}`} style={{ minHeight: 'inherit' }}>
      {text}
    </div>
  );
}
