import { CountUp } from '../lib/motion';

/**
 * KPI card. `value` is already formatted by the API-backed formatters; it counts up on first view (display only).
 * `tone` colours the value (negative = red for a bad direction). `suppressed` shows "n<5" instead of a value.
 */
export default function Metric({ label, value, note, sub, icon: Icon, tone, suppressed, badge, loading, children }) {
  const color = tone === 'negative' ? 'text-negative' : tone === 'accent' ? 'text-accent' : 'text-primary';
  return (
    <div className="card flex min-w-0 flex-col p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase leading-tight tracking-wide text-muted">{label}</span>
        {Icon && <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-accent-soft"><Icon className="h-3.5 w-3.5 text-accent" /></span>}
      </div>
      {children || (loading
        ? <div className="skeleton h-8 w-24" />
        : <div className={`text-[26px] font-bold leading-tight tabular-nums ${suppressed ? 'text-muted' : color}`}>
            {suppressed ? 'n<5' : <CountUp text={value} />}
          </div>)}
      {note && <div className="mt-1 text-[11px] leading-4 text-muted">{note}</div>}
      {sub && <div className="mt-0.5 text-[11px] leading-4 text-muted">{sub}</div>}
      {badge && <div className="mt-2">{badge}</div>}
    </div>
  );
}
