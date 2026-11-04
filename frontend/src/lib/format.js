// Display formatting only — no metric maths happens in the frontend.
export const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
export const fmtInt = (v) => (isNum(v) ? Math.round(v).toLocaleString('en-IN') : '—');
export const fmtNum = (v, d = 1) => (isNum(v) ? v.toFixed(d) : '—');
export const fmtSigned = (v, d = 1) => (isNum(v) ? `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(d)}` : '—');
export const fmtPct = (v, d = 1) => (isNum(v) ? `${v.toFixed(d)}%` : '—');
export const fmtINRLakh = (v) => (isNum(v) ? `₹${v.toFixed(2)} L` : '—');
export const truncate = (s, n = 18) => (s && s.length > n ? `${s.slice(0, n - 1)}…` : s ?? '');
