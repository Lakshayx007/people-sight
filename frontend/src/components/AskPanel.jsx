import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { AlertTriangle, Ban, Bot, ChevronDown, Clock, Loader2, Pin, Send, Sparkles, X } from 'lucide-react';
import { api } from '../lib/api';
import { addHistory, addPin, getHistory } from '../lib/askStore';
import { useFilters } from '../context/FilterContext';
import AskChart from './AskChart';
import DataTable from './DataTable';
import SqlBlock from './SqlBlock';
import { fmtInt, isNum } from '../lib/format';

/**
 * Ask the Data — upgraded from Onco-Sight's Chatbot.jsx into a slide-in panel.
 * The question goes to POST /api/ask; the backend writes and validates ONE read-only SQL query and runs it.
 * The panel shows the chart Groq specified, the explanation, the exact SQL and the rows.
 */
export default function AskPanel({ open, onClose }) {
  const { pathname } = useLocation();
  const { filters } = useFilters();
  const dataset = pathname.startsWith('/hiring') ? 'hiring' : pathname.startsWith('/sentiment') ? 'enps' : 'all';
  const [status, setStatus] = useState(null);
  const [q, setQ] = useState('');
  const [applyFilters, setApplyFilters] = useState(false);
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState(null);
  const [asked, setAsked] = useState('');
  const [history, setHistory] = useState(getHistory);
  const [showSql, setShowSql] = useState(true);
  const [pinned, setPinned] = useState(false);
  const inputRef = useRef(null);
  const nFilters = Object.keys(filters).length;

  useEffect(() => {
    if (open && !status) api.get('/ask/status').then((r) => setStatus(r.data.data[0])).catch(() => setStatus({ available: false }));
    if (open) setTimeout(() => inputRef.current?.focus(), 150);
  }, [open, status]);

  useEffect(() => {
    if (!open) return undefined;
    const esc = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [open, onClose]);

  const ask = async (question) => {
    const text = (question ?? q).trim();
    if (!text || loading) return;
    setQ(text);
    setAsked(text);
    setLoading(true);
    setPinned(false);
    setHistory(addHistory(text));
    try {
      const r = await api.post('/ask', { question: text, dataset, filters, apply_filters: applyFilters && nFilters > 0 }, { timeout: 60000 });
      setRes(r.data);
    } catch (e) {
      setRes({ error: true, message: e.response?.data?.detail || 'The server did not respond. Try again.' });
    } finally {
      setLoading(false);
    }
  };

  const pin = () => {
    if (!res?.data?.length) return;
    const ok = addPin({ question: asked, dataset, sql: res.sql, chart_spec: res.chart_spec, data: res.data, columns: res.columns, n: res.n });
    setPinned(ok ? 'yes' : 'blocked');
  };

  const suggestions = status?.suggestions || [];
  const ok = res && !res.refused && !res.error && !res.unavailable;

  return (
    <>
      {open && <div className="fixed inset-0 z-50 bg-black/30" onClick={onClose} />}
      <aside
        aria-hidden={!open}
        className={`fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-border bg-surface shadow-2xl transition-transform duration-200 sm:w-[500px] lg:w-[560px] ${open ? 'translate-x-0' : 'translate-x-full'}`}
      >
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent-soft text-accent"><Sparkles className="h-4 w-4" /></div>
            <div>
              <h2 className="text-sm font-semibold">Ask the data</h2>
              <p className="text-[11px] text-muted">
                {status == null ? 'Checking…' : status.available ? `Plain English → SQL → chart · ${status.model}` : 'Needs a Groq API key'}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-md p-1.5 text-muted hover:bg-subtle hover:text-primary" aria-label="Close Ask the data"><X className="h-5 w-5" /></button>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {status && !status.available && (
            <Note tone="warn" icon={AlertTriangle}>
              Ask the Data is switched off because no Groq API key is set (GROQ_API_KEY). Every dashboard, filter and “Show SQL” still works.
            </Note>
          )}

          {/* question */}
          <form onSubmit={(e) => { e.preventDefault(); ask(); }} className="space-y-2">
            <div className="relative">
              <textarea
                ref={inputRef}
                rows={2}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); } }}
                placeholder={dataset === 'hiring' ? 'e.g. Median time to fill by grade vs SLA' : 'e.g. eNPS by manager status for April vs October'}
                className="w-full resize-none rounded-xl border border-border bg-background py-2.5 pl-3 pr-12 text-sm outline-none placeholder:text-muted focus:border-accent"
                maxLength={500}
              />
              <button type="submit" disabled={!q.trim() || loading} aria-label="Ask"
                className="absolute bottom-2.5 right-2 rounded-lg bg-accent p-2 text-white disabled:opacity-40">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </button>
            </div>
            <label className={`flex items-center gap-2 text-xs ${nFilters ? 'text-primary' : 'text-muted'}`}>
              <input type="checkbox" checked={applyFilters && nFilters > 0} disabled={!nFilters} onChange={(e) => setApplyFilters(e.target.checked)} className="accent-[var(--acc)]" />
              Apply current dashboard filters {nFilters ? `(${nFilters} active)` : '(none active)'}
            </label>
          </form>

          {/* suggestions */}
          {suggestions.length > 0 && (
            <div>
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">Try a demo question</div>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((s) => (
                  <button key={s} onClick={() => ask(s)} disabled={loading}
                    className="rounded-full border border-border px-2.5 py-1 text-[11px] text-primary hover:border-accent hover:bg-accent-soft disabled:opacity-50">{s}</button>
                ))}
              </div>
            </div>
          )}

          {/* answer */}
          {loading && (
            <div className="flex items-center gap-2 rounded-lg border border-border p-3 text-xs text-muted">
              <Loader2 className="h-4 w-4 animate-spin text-accent" /> Writing and checking the SQL…
            </div>
          )}
          {!loading && res && (
            <section className="space-y-3 rounded-xl border border-border p-3">
              <div className="text-xs text-muted">You asked: <span className="font-medium text-primary">{asked}</span></div>
              {res.refused && <Note tone="neg" icon={Ban}>{res.message}</Note>}
              {(res.error || res.unavailable) && <Note tone="warn" icon={AlertTriangle}>{res.message}</Note>}
              {ok && (
                <>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold">{res.chart_spec?.title || 'Result'}</h3>
                    <div className="flex items-center gap-1.5">
                      <span className="rounded-md bg-subtle px-2 py-0.5 text-[11px] text-muted">{res.data.length} rows · n = {fmtInt(res.n)}</span>
                      <button onClick={pin} disabled={!res.data.length || pinned === 'yes'} title="Pin a snapshot of this answer to the dashboard (this browser only)"
                        className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[11px] text-muted hover:text-accent disabled:text-accent">
                        <Pin className="h-3 w-3" /> {pinned === 'yes' ? 'Pinned' : 'Pin'}
                      </button>
                    </div>
                  </div>
                  {pinned === 'blocked' && <p className="text-[11px] text-warn">This browser blocks local storage, so pins cannot be saved.</p>}
                  {res.filters_applied && <p className="text-[11px] text-accent">Current dashboard filters applied.</p>}
                  {res.suppressed_rows > 0 && <p className="text-[11px] text-muted">{res.suppressed_rows} group(s) with fewer than 5 respondents are hidden (n&lt;5).</p>}
                  {res.data.length === 0 && <p className="text-xs text-muted">The query returned no rows.</p>}
                  <AskChart spec={res.chart_spec} rows={res.data} columns={res.columns} />
                  {res.explanation && <p className="text-[11px] leading-4 text-muted"><b className="text-primary">How:</b> {res.explanation}</p>}
                  <div>
                    <button onClick={() => setShowSql((s) => !s)} className="flex items-center gap-1 text-[11px] font-medium text-accent">
                      <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showSql ? '' : '-rotate-90'}`} /> SQL that ran
                    </button>
                    {showSql && <SqlBlock sql={res.sql} />}
                  </div>
                  {res.data.length > 0 && (
                    <DataTable dense maxHeight={240} rows={res.data}
                      columns={res.columns.map((c) => ({ key: c, label: c, align: res.data.some((r) => isNum(r[c])) ? 'right' : 'left',
                        format: (v, r) => (v == null ? (r.suppressed ? <span className="text-muted">n&lt;5</span> : '—') : typeof v === 'boolean' ? String(v) : isNum(v) ? v.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : String(v)) }))} />
                  )}
                </>
              )}
            </section>
          )}
          {!loading && !res && (
            <div className="flex flex-col items-center gap-2 py-6 text-center text-xs text-muted">
              <Bot className="h-9 w-9 text-border" />
              Ask a question about survey results or hiring. Answers come from one read-only SQL query on the same data as the dashboards; the SQL is always shown.
            </div>
          )}

          {/* history */}
          {history.length > 0 && (
            <div>
              <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-muted"><Clock className="h-3 w-3" /> Recent questions</div>
              <ul className="space-y-1">
                {history.map((h) => (
                  <li key={h}><button onClick={() => ask(h)} className="w-full truncate rounded-md px-2 py-1 text-left text-xs text-muted hover:bg-subtle hover:text-primary">{h}</button></li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <footer className="border-t border-border px-4 py-2 text-[10px] leading-4 text-muted">
          Read-only queries on the dashboard views. Survey answers are anonymous: no names, no individual responses, groups under 5 hidden.
        </footer>
      </aside>
    </>
  );
}

function Note({ tone, icon: Icon, children }) {
  const cls = tone === 'neg' ? 'border-negative/30 text-negative' : 'border-warn/30 bg-warn-soft text-warn';
  return <div className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${cls}`}><Icon className="mt-0.5 h-4 w-4 shrink-0" /><span>{children}</span></div>;
}
