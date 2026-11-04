import { useEffect, useState } from 'react';
import { Pin, X } from 'lucide-react';
import { getPins, onPinsChanged, removePin } from '../lib/askStore';
import AskChart from './AskChart';
import SqlBlock from './SqlBlock';

/** Answers pinned from Ask the Data (snapshot + SQL, stored in this browser only). */
export default function PinnedAnswers({ dataset }) {
  const [pins, setPins] = useState(getPins);
  const [sqlOpen, setSqlOpen] = useState(null);
  useEffect(() => onPinsChanged(() => setPins(getPins())), []);
  const shown = pins.filter((p) => p.dataset === dataset || p.dataset === 'all');
  if (!shown.length) return null;
  return (
    <section className="space-y-2">
      <h2 className="flex items-center gap-1.5 text-sm font-semibold"><Pin className="h-4 w-4 text-accent" /> Pinned from Ask the data</h2>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {shown.map((p) => (
          <div key={p.id} className="rounded-xl border border-border bg-surface p-4 shadow-sm">
            <div className="mb-2 flex items-start justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold">{p.chart_spec?.title || p.question}</h3>
                <p className="text-[11px] text-muted">“{p.question}” · snapshot {new Date(p.pinnedAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })} · n = {p.n}</p>
              </div>
              <div className="flex shrink-0 gap-1">
                <button onClick={() => setSqlOpen(sqlOpen === p.id ? null : p.id)} className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted hover:text-primary">SQL</button>
                <button onClick={() => removePin(p.id)} className="rounded-md p-1 text-muted hover:text-negative" aria-label="Unpin"><X className="h-3.5 w-3.5" /></button>
              </div>
            </div>
            {p.chart_spec?.chart_type === 'table'
              ? <p className="text-xs text-muted">{p.data.length} rows (table answer — open SQL to re-run).</p>
              : <AskChart spec={p.chart_spec} rows={p.data} columns={p.columns} height={240} />}
            {sqlOpen === p.id && <SqlBlock sql={p.sql} />}
          </div>
        ))}
      </div>
    </section>
  );
}
