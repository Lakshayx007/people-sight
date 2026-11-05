import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  Ban, ChevronDown, Copy, FileSpreadsheet, Flag, Lightbulb, ListChecks, ShieldCheck, SpellCheck, Wrench,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';
import Panel from '../components/Panel';
import Metric from '../components/Metric';
import DataTable from '../components/DataTable';
import { useApi } from '../lib/api';
import { fmtInt } from '../lib/format';
import { FadeIn, Stagger, item } from '../lib/motion';

const TABS = [['', 'Both workbooks'], ['eNPS', 'Employee survey'], ['Recruitment', 'Recruitment']];
const ICONS = { duplicates: Copy, spelling: SpellCheck, formats: Wrench, excluded: Ban, corrected: ShieldCheck, findings: Flag };

export default function DataQuality() {
  const [dataset, setDataset] = useState('');
  const [showLog, setShowLog] = useState(false);
  const params = dataset ? { dataset } : {};
  const sum = useApi('/dq/summary', { method: 'get', params });
  const stories = useApi('/dq/stories', { method: 'get', params });
  const rec = useApi('/dq/reconciliation', { method: 'get', params });
  const dq = useApi('/dq', { method: 'get', params, enabled: showLog });
  const sm = sum.data?.[0] || {};

  const sheets = [];
  for (const r of rec.data || []) {
    let s = sheets.find((x) => x.dataset === r.dataset && x.sheet === r.sheet);
    if (!s) { s = { dataset: r.dataset, sheet: r.sheet, steps: [] }; sheets.push(s); }
    s.steps.push(r);
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-3 sm:p-5 lg:p-8">
      <PageHeader eyebrow="Data quality" title="Can you trust these numbers?">
        Before any number on this site was calculated, the raw spreadsheets were checked and cleaned. This page explains
        what we found and fixed. Every step is recorded, so anyone can audit it.
      </PageHeader>

      <div className="flex flex-wrap gap-2">
        {TABS.map(([v, l]) => (
          <button key={l} onClick={() => setDataset(v)}
            className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors ${dataset === v ? 'border-accent bg-accent text-white' : 'border-border bg-surface text-muted hover:text-primary'}`}>
            {l}
          </button>
        ))}
      </div>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Metric label="Checks run" icon={ListChecks} loading={sum.loading && !sum.data} value={fmtInt(sm.rules)}
          note="Each check looked for one kind of problem in one column" />
        <Metric label="Problems fixed" icon={Wrench} loading={sum.loading && !sum.data} value={fmtInt(sm.issues_treated)}
          note="Checks that found something and changed, flagged or set aside data" />
        <Metric label="Checks passed clean" icon={ShieldCheck} loading={sum.loading && !sum.data} value={fmtInt(sm.checks_passed)}
          note="Checks that found nothing wrong" />
      </section>

      <section>
        <FadeIn><h2 className="mb-3 font-display text-xl font-semibold">What we fixed, and why it matters</h2></FadeIn>
        {stories.loading && !stories.data ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="skeleton h-44" />)}</div>
        ) : (
          <Stagger className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" key={dataset}>
            {(stories.data || []).map((s) => {
              const Icon = ICONS[s.key] || Lightbulb;
              const finding = s.key === 'findings';
              return (
                <motion.article key={s.key} variants={item} className={`card flex flex-col p-5 ${finding ? 'border-warn/40' : ''}`}>
                  <div className="mb-3 flex items-center gap-3">
                    <span className={`grid h-10 w-10 place-items-center rounded-xl ${finding ? 'bg-warn-soft' : 'bg-accent-soft'}`}>
                      <Icon className={`h-5 w-5 ${finding ? 'text-warn' : 'text-accent'}`} />
                    </span>
                    <div>
                      <h3 className="text-[15px] font-semibold leading-tight">{s.title}</h3>
                      <div className="text-xs text-muted tabular-nums">{fmtInt(s.rows)} values · {fmtInt(s.rules)} checks</div>
                    </div>
                  </div>
                  <p className="text-[13.5px] leading-6">{s.why}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {s.examples.map((e) => <span key={e} className="rounded-full bg-subtle px-2.5 py-1 text-[11px] text-muted">{e}</span>)}
                  </div>
                </motion.article>
              );
            })}
          </Stagger>
        )}
      </section>

      <Panel title="From raw spreadsheet to clean data" height={0}
        subtitle="Each bar is one sheet: the full bar is what arrived, the blue part is what was kept. Open a sheet to see each step."
        n={rec.n} nLabel="steps" sql={rec.sql} loading={rec.loading} error={rec.error} empty={!rec.loading && !sheets.length}>
        {() => (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {sheets.map((s) => {
              const first = s.steps[0]?.rows || 0;
              const last = s.steps[s.steps.length - 1]?.rows || 0;
              const kept = first ? (100 * last) / first : 100;
              return (
                <details key={`${s.dataset}-${s.sheet}`} className="group rounded-xl border border-border p-3 open:bg-subtle">
                  <summary className="flex cursor-pointer list-none items-center gap-3">
                    <FileSpreadsheet className="h-4 w-4 shrink-0 text-muted" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2 text-xs">
                        <span className="font-semibold">{s.sheet} <span className="font-normal text-muted">· {s.dataset}</span></span>
                        <span className="tabular-nums text-muted">{fmtInt(first)} → <b className="text-primary">{fmtInt(last)}</b></span>
                      </div>
                      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-border">
                        <motion.div className="h-full rounded-full bg-accent" initial={{ width: 0 }} whileInView={{ width: `${kept}%` }}
                          viewport={{ once: true }} transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }} />
                      </div>
                    </div>
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted transition-transform group-open:rotate-180" />
                  </summary>
                  <ol className="mt-3 space-y-1 border-t border-border pt-2">
                    {s.steps.map((st) => (
                      <li key={st.order} className="flex items-center justify-between gap-2 text-[12px]">
                        <span className="min-w-0 truncate text-muted" title={st.note || st.step}>{st.step}</span>
                        <span className="shrink-0 tabular-nums">
                          <b>{fmtInt(st.rows)}</b>
                          {typeof st.change === 'number' && st.change !== 0 && <span className="ml-1.5 text-negative">{st.change > 0 ? '+' : ''}{fmtInt(st.change)}</span>}
                        </span>
                      </li>
                    ))}
                  </ol>
                </details>
              );
            })}
          </div>
        )}
      </Panel>

      <FadeIn className="card p-4 sm:p-5">
        <button onClick={() => setShowLog((x) => !x)} className="flex w-full items-center justify-between gap-3 text-left" aria-expanded={showLog}>
          <div>
            <h3 className="text-[15px] font-semibold">Full cleaning log, for auditors</h3>
            <p className="text-xs text-muted">Every check with the column, what was found, how many rows, what we did and why. {fmtInt(sm.rules)} rows.</p>
          </div>
          <span className="flex shrink-0 items-center gap-1 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-accent">
            {showLog ? 'Hide' : 'Show'} log <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showLog ? 'rotate-180' : ''}`} />
          </span>
        </button>
        <AnimatePresence initial={false}>
          {showLog && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
              <div className="mt-4">
                {dq.loading && !dq.data ? <div className="skeleton h-64" /> : (
                  <DataTable rows={dq.data || []} maxHeight={560} rowKey={(r) => `${r.dataset}-${r.sheet}-${r.column}-${r.issue}`}
                    highlight={(r) => r.changed_data}
                    columns={[
                      { key: 'sheet', label: 'Sheet', wrap: 120, format: (v, r) => <span>{v}<br /><span className="text-[10px] text-muted">{r.dataset}</span></span> },
                      { key: 'column', label: 'Column', wrap: 110 },
                      { key: 'issue', label: 'What we found', wrap: 250 },
                      { key: 'rows_affected', label: 'Rows', align: 'right', format: fmtInt },
                      { key: 'treatment', label: 'What we did', wrap: 210 },
                      { key: 'assumption', label: 'Why / assumption', wrap: 230, format: (v) => v || '–' },
                    ]} />
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </FadeIn>
    </div>
  );
}
