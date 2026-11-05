import { useEffect, useState } from 'react';
import { Code2, Lightbulb, Maximize2, Sparkles } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import ChartModal from './ChartModal';
import SqlBlock from './SqlBlock';
import { NBadge } from './Badges';
import { api, loadAskStatus } from '../lib/api';
import { FadeIn } from '../lib/motion';

export const CHART_H = 300;

/**
 * Chart card. Shows: title + subtitle, a "What this shows" sentence written by the backend from the
 * same rows (always available, no AI), an optional "What does this chart say?" AI explanation (only when Groq is
 * configured; written only from the rows shown), n badge, Show SQL, enlarge, and loading / error / empty states.
 * `children` may be a function (height) => node so the same chart can render inside the zoom modal.
 */
export default function Panel({
  title, subtitle, n, nLabel, sql, loading, error, empty, badges, actions, children,
  className = '', height = CHART_H, footer, insightRows, takeaway,
}) {
  const [showSql, setShowSql] = useState(false);
  const [zoom, setZoom] = useState(false);
  const [aiOn, setAiOn] = useState(false);
  const [ai, setAi] = useState({ text: null, loading: false, key: null });
  const render = (h) => (typeof children === 'function' ? children(h) : children);
  useEffect(() => { if (insightRows) loadAskStatus().then((st) => setAiOn(!!st.available)); }, [insightRows]);
  const rowsKey = insightRows ? `${JSON.stringify(insightRows).length}:${(sql || '').length}` : null;
  const aiText = ai.key === rowsKey ? ai.text : null;
  const aiLoading = ai.loading && ai.key === rowsKey;

  const explain = async () => {
    setAi({ text: null, loading: true, key: rowsKey });
    try {
      const r = await api.post('/chart-insight', {
        title, rows: (insightRows || []).slice(0, 40), context: [subtitle, takeaway].filter(Boolean).join(' '),
      }, { timeout: 45000 });
      setAi({ text: r.data.data[0].insight, loading: false, key: rowsKey });
    } catch (e) {
      setAi({ text: e.response?.data?.detail || 'Could not get an explanation right now. Try again in a minute.', loading: false, key: rowsKey });
    }
  };

  let body;
  if (error) body = <State text={`Could not load: ${error}`} tone="error" />;
  else if (empty && !loading) body = <State text="No data for the current filters" />;
  else if (loading && !insightRows && height) body = <div className="skeleton h-full w-full" style={{ minHeight: height }} />;
  else body = render(height);

  const canExplain = aiOn && insightRows?.length > 0 && !loading && !error;

  return (
    <FadeIn as="section" className={`card flex min-w-0 flex-col p-4 sm:p-5 ${className}`}>
      <header className="mb-3">
        <div className="flex items-start justify-between gap-3">
          <h3 className="min-w-0 flex-1 text-[15px] font-semibold leading-snug">{title}</h3>
          <div className="flex shrink-0 items-center gap-0.5">
            <button onClick={() => setShowSql((x) => !x)} aria-pressed={showSql}
              className={`flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-medium ${showSql ? 'bg-accent-soft text-accent' : 'text-muted hover:bg-subtle hover:text-primary'}`}
              title="Show the exact SQL behind this chart">
              <Code2 className="h-3.5 w-3.5" /> SQL
            </button>
            <button onClick={() => setZoom(true)} className="rounded-md p-1.5 text-muted hover:bg-subtle hover:text-accent" title="Enlarge" aria-label="Enlarge chart">
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
        {subtitle && <p className="mt-0.5 text-xs leading-5 text-muted">{subtitle}</p>}
        {(actions || n != null || canExplain) && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {actions}
            <NBadge n={n} label={nLabel} />
            {canExplain && (
              <button onClick={explain} disabled={aiLoading}
                className="flex items-center gap-1 rounded-full border border-accent/40 bg-accent-soft px-2.5 py-0.5 text-[11px] font-medium text-accent hover:border-accent disabled:opacity-60"
                title="Get a short summary of this chart">
                <Sparkles className="h-3 w-3" /> What does this chart say?
              </button>
            )}
          </div>
        )}
      </header>

      {takeaway && !error && (
        <div className="mb-3 flex gap-2 rounded-xl bg-subtle px-3 py-2 text-[13px] leading-5 text-primary">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
          <p><span className="sr-only">What this shows: </span>{takeaway}</p>
        </div>
      )}

      <AnimatePresence>
        {(aiText || aiLoading) && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            className="mb-3 overflow-hidden rounded-xl border border-accent/30 bg-accent-soft/50 px-3 py-2 text-[13px] leading-5">
            <div className="mb-0.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-accent">
              <Sparkles className="h-3.5 w-3.5" /> AI explanation
            </div>
            {aiLoading ? <span className="animate-pulse text-muted">Reading the chart…</span> : <p>{aiText}</p>}
          </motion.div>
        )}
      </AnimatePresence>

      {badges && <div className="mb-2 flex flex-wrap gap-1.5">{badges}</div>}
      <div className="relative min-w-0" style={{ minHeight: height }}>
        {body}
        {loading && insightRows && (
          <div className="absolute inset-0 grid place-items-center bg-surface/60 backdrop-blur-[1px]">
            <div className="h-7 w-7 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          </div>
        )}
      </div>
      {footer}
      {showSql && <SqlBlock sql={sql} />}
      <ChartModal isOpen={zoom} onClose={() => setZoom(false)} title={title} subtitle={subtitle}>
        {!error && !empty && render(Math.min(560, window.innerHeight * 0.65))}
      </ChartModal>
    </FadeIn>
  );
}

function State({ text, tone }) {
  return (
    <div className={`grid h-full min-h-[inherit] place-items-center rounded-xl border border-dashed border-border text-xs ${tone === 'error' ? 'text-negative' : 'text-muted'}`} style={{ minHeight: 'inherit' }}>
      {text}
    </div>
  );
}
