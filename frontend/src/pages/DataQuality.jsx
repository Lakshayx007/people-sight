import { useState } from 'react';
import { ArrowRight, ClipboardCheck, FileSpreadsheet, ListChecks } from 'lucide-react';
import Panel from '../components/Panel';
import Metric from '../components/Metric';
import DataTable from '../components/DataTable';
import { useApi } from '../lib/api';
import { fmtInt } from '../lib/format';

const TABS = [['', 'All'], ['eNPS', 'eNPS workbook'], ['Recruitment', 'Recruitment workbook']];

export default function DataQuality() {
  const [dataset, setDataset] = useState('');
  const dq = useApi('/dq', { method: 'get', params: dataset ? { dataset } : {} });
  const params = dataset ? { dataset } : {};
  const rec = useApi('/dq/reconciliation', { method: 'get', params });
  const sum = useApi('/dq/summary', { method: 'get', params });
  const sm = sum.data?.[0] || {};

  const rows = dq.data || [];
  const sheets = [];
  for (const r of rec.data || []) {
    let s = sheets.find((x) => x.dataset === r.dataset && x.sheet === r.sheet);
    if (!s) { s = { dataset: r.dataset, sheet: r.sheet, steps: [] }; sheets.push(s); }
    s.steps.push(r);
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-4 p-3 sm:p-4 lg:p-6">
      <div>
        <h1 className="text-lg font-bold sm:text-xl">Data quality</h1>
        <p className="text-xs text-muted">Every cleaning rule the pipeline applied (data/clean/dq_log.csv) and the row counts from raw input to cleaned output. Rows affected = 0 means the check ran and passed.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map(([v, l]) => (
          <button key={l} onClick={() => setDataset(v)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${dataset === v ? 'border-accent bg-accent-soft text-accent' : 'border-border bg-surface text-muted hover:text-primary'}`}>
            {l}
          </button>
        ))}
      </div>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Rules logged" icon={ListChecks} loading={sum.loading && !sum.data} value={fmtInt(sm.rules)} note="Rows in the cleaning log" />
        <Metric label="Issues treated" icon={ClipboardCheck} loading={sum.loading && !sum.data} value={fmtInt(sm.issues_treated)} note="Rules that changed, flagged or excluded rows" />
        <Metric label="Checks passed" icon={ClipboardCheck} loading={sum.loading && !sum.data} value={fmtInt(sm.checks_passed)} note="Validations with 0 rows affected" />
        <Metric label="Sheets reconciled" icon={FileSpreadsheet} loading={sum.loading && !sum.data} value={fmtInt(sm.sheets_reconciled)} note="Rows in → each step → rows out" />
      </section>

      <Panel title="Row counts: raw input → each step → cleaned output" height={0}
        n={rec.n} nLabel="n steps" sql={rec.sql} loading={rec.loading} error={rec.error} empty={!rec.loading && !sheets.length}>
        {() => (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {sheets.map((s) => (
              <div key={`${s.dataset}-${s.sheet}`} className="rounded-lg border border-border p-3">
                <div className="mb-2 flex items-baseline justify-between gap-2">
                  <span className="text-xs font-semibold">{s.sheet}</span>
                  <span className="text-[11px] text-muted">{s.dataset}</span>
                </div>
                <ol className="space-y-1">
                  {s.steps.map((st, i) => (
                    <li key={st.order} className="flex items-center justify-between gap-2 text-[11px]">
                      <span className="flex min-w-0 items-center gap-1.5 text-muted">
                        {i > 0 && <ArrowRight className="h-3 w-3 shrink-0" />}
                        <span className="truncate" title={st.note || st.step}>{st.step}</span>
                      </span>
                      <span className="shrink-0 tabular-nums">
                        <b>{fmtInt(st.rows)}</b>
                        {typeof st.change === 'number' && st.change !== 0 && <span className="ml-1.5 text-negative">{st.change > 0 ? '+' : ''}{fmtInt(st.change)}</span>}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Cleaning log: issue, rows affected, treatment and assumption" height={0}
        subtitle="Click a column header to sort. Highlighted rows changed, flagged or excluded data."
        n={dq.n} nLabel="n rules" sql={dq.sql} loading={dq.loading} error={dq.error} empty={!dq.loading && !rows.length}>
        {() => (
          <DataTable rows={rows} maxHeight={640} rowKey={(r) => `${r.dataset}-${r.sheet}-${r.column}-${r.issue}`}
            highlight={(r) => r.changed_data}
            columns={[
              { key: 'sheet', label: 'Sheet', wrap: 120, format: (v, r) => <span>{v}<br /><span className="text-[10px] text-muted">{r.dataset}</span></span> },
              { key: 'column', label: 'Column', wrap: 110 },
              { key: 'issue', label: 'Issue', wrap: 250 },
              { key: 'rows_affected', label: 'Rows', align: 'right', format: fmtInt },
              { key: 'treatment', label: 'Treatment', wrap: 210 },
              { key: 'assumption', label: 'Assumption', wrap: 230, format: (v) => v || '—' },
            ]} />
        )}
      </Panel>
    </div>
  );
}
