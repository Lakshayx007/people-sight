import { createContext, useCallback, useContext, useMemo } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';

/**
 * One global filter state per dashboard, stored in the URL query string (?thread=Intercity&function=Sales).
 * The URL is the single source of truth, so every view is a shareable link and the back button works.
 * Order of keys in the URL = order filters were added = the breadcrumb trail.
 */
export const FILTER_DEFS = {
  enps: [
    { key: 'wave', label: 'Wave' },
    { key: 'thread', label: 'Thread' },
    { key: 'function', label: 'Function' },
    { key: 'job_family', label: 'Job family' },
    { key: 'grade', label: 'Grade' },
    { key: 'location', label: 'Location' },
    { key: 'location_type', label: 'Location type' },
    { key: 'company', label: 'Company' },
    { key: 'tenure_band', label: 'Tenure' },
    { key: 'performance_rating', label: 'Rating' },
    { key: 'compa_band', label: 'Compa band' },
    { key: 'manager_status', label: 'Manager status' },
  ],
  hiring: [
    { key: 'thread', label: 'Thread' },
    { key: 'function', label: 'Function' },
    { key: 'grade', label: 'Grade' },
    { key: 'location', label: 'Location' },
    { key: 'recruiter', label: 'Recruiter' },
    { key: 'source', label: 'Source' },
    { key: 'position_type', label: 'Position type' },
    { key: 'criticality', label: 'Criticality' },
    { key: 'req_status', label: 'Req status' },
    { key: 'raised_month_from', label: 'Raised from', range: true },
    { key: 'raised_month_to', label: 'Raised to', range: true },
  ],
};

export const dashboardFor = (pathname) =>
  pathname.startsWith('/hiring') ? 'hiring' : pathname.startsWith('/sentiment') ? 'enps' : null;

const Ctx = createContext(null);

export function FilterProvider({ children }) {
  const [sp, setSp] = useSearchParams();
  const { pathname } = useLocation();
  const dashboard = dashboardFor(pathname);
  const defs = useMemo(() => FILTER_DEFS[dashboard] || [], [dashboard]);

  const filters = useMemo(() => {
    const f = {};
    for (const d of defs) {
      if (d.range) {
        const v = sp.get(d.key);
        if (v) f[d.key] = v;
      } else {
        const v = sp.getAll(d.key).filter(Boolean);
        if (v.length) f[d.key] = v;
      }
    }
    return f;
  }, [sp, defs]);

  const order = useMemo(() => {
    const keys = defs.map((d) => d.key);
    const seen = [];
    for (const [k] of sp.entries()) if (keys.includes(k) && !seen.includes(k)) seen.push(k);
    return seen;
  }, [sp, defs]);

  const update = useCallback((mutate) => {
    const next = new URLSearchParams(sp);
    mutate(next);
    setSp(next);
  }, [sp, setSp]);

  const setFilter = useCallback((key, values) => update((n) => {
    n.delete(key);
    (Array.isArray(values) ? values : [values]).filter((v) => v !== '' && v != null).forEach((v) => n.append(key, String(v)));
  }), [update]);

  /** Drill-down: narrow to the clicked value(s), e.g. drill({ thread: 'Intercity', function: 'Sales' }). */
  const drill = useCallback((pairs) => update((n) => {
    for (const [k, v] of Object.entries(pairs)) {
      if (!defs.some((d) => d.key === k)) continue;
      n.delete(k);
      n.append(k, String(v));
    }
  }), [update, defs]);

  const removeValue = useCallback((key, val) => update((n) => {
    const rest = n.getAll(key).filter((x) => x !== val);
    n.delete(key);
    rest.forEach((x) => n.append(key, x));
  }), [update]);

  const clearAll = useCallback(() => update((n) => defs.forEach((d) => n.delete(d.key))), [update, defs]);
  /** Breadcrumb: keep filters up to and including position i (i = -1 clears all). */
  const goToCrumb = useCallback((i) => update((n) => order.slice(i + 1).forEach((k) => n.delete(k))), [update, order]);

  const value = useMemo(() => ({ dashboard, defs, filters, order, setFilter, drill, removeValue, clearAll, goToCrumb }),
    [dashboard, defs, filters, order, setFilter, drill, removeValue, clearAll, goToCrumb]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useFilters = () => useContext(Ctx);
