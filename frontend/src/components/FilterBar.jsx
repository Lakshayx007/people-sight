import { useEffect, useState } from 'react';
import { ChevronRight, Filter, SlidersHorizontal, X } from 'lucide-react';
import MultiSelectDropdown from './MultiSelectDropdown';
import { useFilters } from '../context/FilterContext';
import { loadFilterOptions } from '../lib/api';

/**
 * Global filter bar: every filter is a multi-select fed by /api/filters/options,
 * state lives in the URL (FilterContext). Active filters show as removable chips with Clear all,
 * and a breadcrumb trail shows the drill-down path.
 */
export default function FilterBar() {
  const { dashboard, defs, filters, order, setFilter, removeValue, clearAll, goToCrumb } = useFilters();
  const [options, setOptions] = useState(null);
  const [error, setError] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    loadFilterOptions().then(setOptions).catch((e) => setError(e.message));
  }, []);

  const opts = options?.[dashboard] || {};
  const labelOf = (k) => defs.find((d) => d.key === k)?.label || k;
  const activeCount = Object.keys(filters).length;
  const months = opts.raised_month || [];

  const controls = defs.map((d) => (d.range ? (
    <label key={d.key} className="flex h-9 items-center gap-2 rounded-lg border border-border bg-surface px-3 text-xs">
      <span className="text-muted">{d.label}:</span>
      <select
        value={filters[d.key] || ''}
        onChange={(e) => setFilter(d.key, e.target.value)}
        className="bg-transparent font-medium outline-none"
      >
        <option value="">Any</option>
        {months.map((m) => <option key={m} value={m}>{m}</option>)}
      </select>
    </label>
  ) : (
    <MultiSelectDropdown
      key={d.key}
      label={d.label}
      options={opts[d.key] || []}
      selected={filters[d.key] || []}
      onChange={(v) => setFilter(d.key, v)}
    />
  )));

  return (
    <section className="rounded-xl border border-border bg-surface px-4 py-3 shadow-sm">
      {/* breadcrumb trail */}
      <nav className="mb-2 flex flex-wrap items-center gap-1 text-xs text-muted" aria-label="Breadcrumb">
        <button onClick={() => goToCrumb(-1)} className={`rounded px-1 py-0.5 hover:text-primary ${order.length === 0 ? 'font-semibold text-primary' : ''}`}>
          {dashboard === 'hiring' ? 'All requisitions' : 'All employees'}
        </button>
        {order.map((k, i) => (
          <span key={k} className="flex items-center gap-1">
            <ChevronRight className="h-3 w-3" />
            <button
              onClick={() => goToCrumb(i)}
              className={`rounded px-1 py-0.5 hover:text-primary ${i === order.length - 1 ? 'font-semibold text-primary' : ''}`}
            >
              {labelOf(k)}: {Array.isArray(filters[k]) ? filters[k].join(', ') : filters[k]}
            </button>
          </span>
        ))}
      </nav>

      {/* mobile toggle */}
      <button
        onClick={() => setMobileOpen((o) => !o)}
        className="flex h-9 w-full items-center justify-between rounded-lg border border-border px-3 text-xs font-medium sm:hidden"
      >
        <span className="flex items-center gap-2"><SlidersHorizontal className="h-4 w-4 text-accent" /> Filters{activeCount ? ` (${activeCount})` : ''}</span>
        <ChevronRight className={`h-4 w-4 text-muted transition-transform ${mobileOpen ? 'rotate-90' : ''}`} />
      </button>

      <div className={`${mobileOpen ? 'mt-2 grid' : 'hidden'} grid-cols-1 gap-2 sm:flex sm:flex-wrap sm:items-center`}>
        <Filter className="hidden h-4 w-4 text-accent sm:block" />
        {error ? <span className="text-xs text-negative">Filter options unavailable: {error}</span> : controls}
      </div>

      {activeCount > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {Object.entries(filters).flatMap(([k, v]) => (Array.isArray(v) ? v : [v]).map((val) => (
            <span key={`${k}-${val}`} className="inline-flex items-center gap-1.5 rounded-md bg-accent-soft px-2 py-1 text-[11px] font-medium text-accent">
              {labelOf(k)}: {val}
              <button onClick={() => (Array.isArray(v) ? removeValue(k, val) : setFilter(k, ''))} aria-label={`Remove ${val}`} className="hover:text-negative">
                <X className="h-3 w-3" />
              </button>
            </span>
          )))}
          <button onClick={clearAll} className="ml-1 text-[11px] font-semibold text-negative hover:underline">Clear all</button>
        </div>
      )}
    </section>
  );
}
