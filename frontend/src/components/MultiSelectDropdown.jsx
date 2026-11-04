import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Search } from 'lucide-react';

/**
 * Adapted from Onco-Sight's MultiSelectDropdown. Changes: nothing selected = "All" (no filter),
 * no forced minimum selection, a search box for long lists, the label shows the filter name.
 */
export default function MultiSelectDropdown({ label, options = [], selected = [], onChange, align = 'left' }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const ref = useRef(null);

  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const shown = useMemo(
    () => (q ? options.filter((o) => o.toLowerCase().includes(q.toLowerCase())) : options), [options, q]);
  const toggle = (o) => onChange(selected.includes(o) ? selected.filter((x) => x !== o) : [...selected, o]);
  const summary = selected.length === 0 ? 'All' : selected.length === 1 ? selected[0] : `${selected.length} selected`;
  const active = selected.length > 0;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex h-9 w-full items-center justify-between gap-2 rounded-lg border px-3 text-xs font-medium transition-colors sm:w-auto sm:max-w-[220px] ${
          active ? 'border-accent bg-accent-soft text-accent' : 'border-border bg-surface text-primary hover:border-muted'}`}
      >
        <span className="truncate"><span className="text-muted">{label}:</span> {summary}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted" />
      </button>

      {open && (
        <div className={`absolute z-50 mt-1 w-64 max-w-[85vw] overflow-hidden rounded-lg border border-border bg-surface shadow-xl ${align === 'right' ? 'right-0' : 'left-0'}`}>
          {options.length > 8 && (
            <div className="flex items-center gap-2 border-b border-border px-3 py-2">
              <Search className="h-3.5 w-3.5 text-muted" />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={`Search ${label.toLowerCase()}`}
                className="w-full bg-transparent text-xs outline-none placeholder:text-muted"
              />
            </div>
          )}
          <div className="flex items-center justify-between border-b border-border px-2 py-1.5">
            <button type="button" className="rounded px-2 py-1 text-xs font-medium text-accent" onClick={() => onChange([...options])}>Select all</button>
            <button type="button" className="rounded px-2 py-1 text-xs font-medium text-muted hover:text-primary" onClick={() => onChange([])}>Clear</button>
          </div>
          <div className="max-h-64 overflow-y-auto p-1">
            {shown.length === 0 && <div className="px-3 py-2 text-xs text-muted">No matches</div>}
            {shown.map((o) => {
              const on = selected.includes(o);
              return (
                <button
                  type="button"
                  key={o}
                  onClick={() => toggle(o)}
                  className={`flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-xs ${on ? 'bg-accent-soft' : 'hover:bg-subtle'}`}
                >
                  <span className={`grid h-4 w-4 shrink-0 place-items-center rounded border ${on ? 'border-accent bg-accent text-white' : 'border-muted'}`}>
                    {on && <Check className="h-3 w-3" />}
                  </span>
                  <span className={on ? 'font-medium' : 'text-muted'}>{o}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
