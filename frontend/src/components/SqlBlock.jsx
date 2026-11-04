import { useState } from 'react';
import { Check, Copy } from 'lucide-react';

/** The exact SQL the API ran (first line holds the parameter values). */
export default function SqlBlock({ sql }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard not available */ }
  };
  return (
    <div className="relative mt-3 rounded-lg border border-border bg-subtle">
      <button onClick={copy} className="absolute right-2 top-2 flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-[11px] text-muted hover:text-primary">
        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />} {copied ? 'Copied' : 'Copy'}
      </button>
      <pre className="sql max-h-64 overflow-auto whitespace-pre p-3 pr-20 text-primary">{sql || '—'}</pre>
    </div>
  );
}
