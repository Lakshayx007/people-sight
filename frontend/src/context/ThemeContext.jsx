import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { PALETTE } from '../themes/themeConfig';

const Ctx = createContext(null);

function readSaved() {
  try { return localStorage.getItem('pa-theme') === 'dark' ? 'dark' : 'light'; } catch { return 'light'; }
}

/** Light theme by default; the choice is remembered per browser (wrapped in try/catch). */
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(readSaved);
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    try { localStorage.setItem('pa-theme', theme); } catch { /* storage unavailable */ }
  }, [theme]);
  const value = useMemo(() => ({
    theme, chartTheme: `pa-${theme}`, palette: PALETTE[theme],
    toggle: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')),
  }), [theme]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);
