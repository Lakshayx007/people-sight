import { NavLink } from 'react-router-dom';
import { Briefcase, ClipboardCheck, Moon, Smile, Sparkles, Sun, Users, X } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

// Adapted from Onco-Sight's Sidebar: same collapsible layout and mobile overlay, new navigation.
const NAV = [
  { name: 'Employee sentiment', icon: Smile, path: '/sentiment' },
  { name: 'Hiring', icon: Briefcase, path: '/hiring' },
  { name: 'Data quality', icon: ClipboardCheck, path: '/data-quality' },
];

export default function Sidebar({ open, onClose, onAsk }) {
  const { theme, toggle } = useTheme();
  return (
    <>
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-60 flex-col border-r border-border bg-surface transition-transform duration-200 lg:sticky lg:top-0 lg:h-screen lg:shrink-0 lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-5">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-white">
              <Users className="h-5 w-5" />
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">Porter</div>
              <div className="text-sm font-bold leading-tight">People Analytics</div>
            </div>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:text-primary lg:hidden" aria-label="Close menu">
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 px-3 py-4">
          <div className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">Dashboards</div>
          <div className="space-y-1">
            {NAV.map(({ name, icon: Icon, path }) => (
              <NavLink
                key={path}
                to={path}
                onClick={onClose}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive ? 'bg-accent-soft text-accent' : 'text-muted hover:bg-subtle hover:text-primary'}`}
              >
                <Icon className="h-4 w-4" />
                {name}
              </NavLink>
            ))}
          </div>
          <button onClick={onAsk}
            className="mt-4 flex w-full items-center gap-3 rounded-lg bg-accent px-3 py-2.5 text-sm font-medium text-white shadow-sm hover:opacity-90">
            <Sparkles className="h-4 w-4" /> Ask the data
          </button>
        </nav>

        <div className="space-y-3 border-t border-border p-4">
          <button
            onClick={toggle}
            className="flex w-full items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs font-medium text-muted hover:text-primary"
          >
            {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            {theme === 'dark' ? 'Light theme' : 'Dark theme'}
          </button>
          <p className="text-[11px] leading-5 text-muted">
            Data as of 31-Oct-2026. Survey waves: Apr (06–17 Apr) and Oct (05–16 Oct). Synthetic data.
          </p>
        </div>
      </aside>
      {open && <div onClick={onClose} className="fixed inset-0 z-40 bg-black/30 lg:hidden" />}
    </>
  );
}
