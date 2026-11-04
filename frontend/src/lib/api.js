import axios from 'axios';
import { useEffect, useState } from 'react';

// Always relative: Vite proxies /api in dev; FastAPI serves both in production.
export const api = axios.create({ baseURL: '/api', timeout: 30000 });

/**
 * Fetch one metric endpoint. Every response is {data, sql, n}.
 * Keeps the previous data visible while a new request (new filters) is loading.
 */
export function useApi(path, { filters = {}, params = {}, method = 'post', enabled = true } = {}) {
  const key = `${method}|${path}|${JSON.stringify(params)}|${JSON.stringify(filters)}`;
  const [state, setState] = useState({ data: null, sql: '', n: null, loading: true, error: null });

  useEffect(() => {
    if (!enabled) return undefined;
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    const req = method === 'get'
      ? api.get(path, { params, signal: ctrl.signal })
      : api.post(path, { filters }, { params, signal: ctrl.signal });
    req
      .then((r) => setState({ data: r.data.data, sql: r.data.sql, n: r.data.n, loading: false, error: null }))
      .catch((e) => {
        if (axios.isCancel(e) || e.name === 'CanceledError') return;
        setState({ data: null, sql: '', n: null, loading: false, error: e.response?.data?.detail || e.message });
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled]);

  return state;
}

let optionsPromise = null;
/** Filter options from /api/filters/options, fetched once: { enps: {key: [values]}, hiring: {...} }. */
export function loadFilterOptions() {
  if (!optionsPromise) {
    optionsPromise = api.get('/filters/options').then((r) => {
      const out = { enps: {}, hiring: {} };
      for (const row of r.data.data) out[row.dashboard][row.key] = row.values;
      return out;
    }).catch((e) => { optionsPromise = null; throw e; });
  }
  return optionsPromise;
}
