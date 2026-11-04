import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';

/**
 * Sortable table for API rows (sorting is presentation only). Columns:
 *   { key, label, align: 'left'|'right', format: (v, row) => node, title, bar: { max, color, tone(row) } }
 * `onRowClick(row)` makes rows clickable (drill-down). Scrolls horizontally on small screens.
 */
export default function DataTable({ columns, rows = [], onRowClick, defaultSort, rowKey, maxHeight, dense = false, highlight }) {
  const [sort, setSort] = useState(defaultSort || null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const { key, dir } = sort;
    return [...rows].sort((a, b) => {
      const x = a[key]; const y = b[key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y));
      return dir === 'asc' ? c : -c;
    });
  }, [rows, sort]);

  const toggle = (key) => setSort((s) => (s?.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }));
  const pad = dense ? 'px-2 py-1.5' : 'px-3 py-2';

  return (
    <>
    {columns.length > 4 && <div className="mb-1 text-[11px] text-muted sm:hidden">Swipe sideways to see all columns →</div>}
    <div className="overflow-auto rounded-lg border border-border" style={{ maxHeight }}>
      <table className="w-full min-w-max border-collapse text-xs">
        <thead className="sticky top-0 z-10 bg-subtle">
          <tr>
            {columns.map((c) => (
              <th key={c.key} title={c.title}
                style={c.headWidth ? { minWidth: c.headWidth, maxWidth: c.headWidth } : undefined}
                className={`${pad} border-b border-border align-bottom font-semibold leading-tight text-muted ${c.headWidth ? 'whitespace-normal' : 'whitespace-nowrap'} ${c.align === 'right' ? 'text-right' : 'text-left'} ${c.sortable === false ? '' : 'cursor-pointer select-none hover:text-primary'}`}
                onClick={c.sortable === false ? undefined : () => toggle(c.key)}>
                <span className={`inline-flex items-center gap-1 ${c.align === 'right' ? 'flex-row-reverse' : ''}`}>
                  {c.label}
                  {c.sortable !== false && (sort?.key === c.key
                    ? (sort.dir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)
                    : <ArrowUpDown className="h-3 w-3 opacity-30" />)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={rowKey ? rowKey(r) : i}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={`border-b border-border last:border-0 ${onRowClick ? 'cursor-pointer hover:bg-accent-soft/50' : ''} ${highlight?.(r) ? 'bg-warn-soft/40' : ''}`}>
              {columns.map((c) => {
                const v = r[c.key];
                const content = c.format ? c.format(v, r) : (v ?? '—');
                return (
                  <td key={c.key} className={`${pad} align-middle tabular-nums ${c.align === 'right' ? 'text-right' : 'text-left'} ${c.wrap ? 'whitespace-normal' : 'whitespace-nowrap'}`}
                    style={c.wrap ? { maxWidth: c.wrap, minWidth: Math.min(c.wrap, 90) } : undefined}>
                    {c.bar && typeof v === 'number' ? (
                      <div className="flex items-center justify-end gap-2">
                        <span>{content}</span>
                        <span className="h-1.5 w-12 overflow-hidden rounded-full bg-subtle">
                          <span className="block h-full rounded-full" style={{ width: `${Math.min(100, (100 * v) / c.bar.max)}%`, background: c.bar.tone ? c.bar.tone(r) : c.bar.color }} />
                        </span>
                      </div>
                    ) : content}
                  </td>
                );
              })}
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr><td colSpan={columns.length} className="px-3 py-6 text-center text-muted">No rows for the current filters</td></tr>
          )}
        </tbody>
      </table>
    </div>
    </>
  );
}
