import { AlertTriangle } from 'lucide-react';

export function LowResponseBadge({ detail, compact = false }) {
  return (
    <span
      title="Response rate below 50%: the people who answered may not represent the group"
      className="inline-block rounded-md bg-warn-soft px-2 py-0.5 text-[11px] font-medium leading-5 text-warn"
    >
      <AlertTriangle className="mr-1 inline h-3 w-3 align-[-2px]" />
      {compact ? 'Low response' : 'Low response, read with caution'}
      {detail ? <span className="font-normal"> · {detail}</span> : null}
    </span>
  );
}

export function NBadge({ n, label = 'n' }) {
  if (n == null) return null;
  return (
    <span className="rounded-md bg-subtle px-2 py-0.5 text-[11px] font-medium text-muted tabular-nums">
      {label} = {Number(n).toLocaleString('en-IN')}
    </span>
  );
}

export function SuppressedTag() {
  return <span className="rounded bg-subtle px-1.5 py-0.5 text-[11px] font-medium text-muted">n&lt;5</span>;
}
