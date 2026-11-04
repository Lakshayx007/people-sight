/**
 * KPI card, adapted from Onco-Sight's Metric. `value` is already formatted; `tone` colours the value
 * (negative = red for a bad direction). `suppressed` shows "n<5" instead of a value.
 */
export default function Metric({ label, value, note, sub, icon: Icon, tone, suppressed, badge, loading, children }) {
  const color = tone === 'negative' ? 'text-negative' : tone === 'accent' ? 'text-accent' : 'text-primary';
  return (
    <div className="flex min-w-0 flex-col rounded-xl border border-border bg-surface p-4 shadow-sm">
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase leading-tight tracking-wide text-muted">{label}</span>
        {Icon && <Icon className="h-4 w-4 shrink-0 text-accent" />}
      </div>
      {children || (
        <div className={`text-2xl font-bold tabular-nums ${loading ? 'animate-pulse text-muted' : suppressed ? 'text-muted' : color}`}>
          {loading ? '…' : suppressed ? 'n<5' : value}
        </div>
      )}
      {note && <div className="mt-1 text-[11px] text-muted">{note}</div>}
      {sub && <div className="mt-0.5 text-[11px] text-muted">{sub}</div>}
      {badge && <div className="mt-2">{badge}</div>}
    </div>
  );
}
