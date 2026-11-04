import { useState } from 'react';
import { Menu, Sparkles } from 'lucide-react';
import Sidebar from './Sidebar';
import AskPanel from './AskPanel';

export default function Layout({ children }) {
  const [open, setOpen] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  return (
    <div className="flex min-h-screen">
      <Sidebar open={open} onClose={() => setOpen(false)} onAsk={() => { setOpen(false); setAskOpen(true); }} />
      <div className="flex min-w-0 flex-1 flex-col">
        {/* mobile top bar */}
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-surface px-4 py-3 lg:hidden">
          <button onClick={() => setOpen(true)} aria-label="Open menu" className="rounded-md p-1 text-muted hover:text-primary">
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-sm font-semibold">People Analytics</span>
          <button onClick={() => setAskOpen(true)} className="ml-auto flex items-center gap-1.5 rounded-lg bg-accent px-2.5 py-1.5 text-xs font-medium text-white">
            <Sparkles className="h-3.5 w-3.5" /> Ask
          </button>
        </header>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
      <AskPanel open={askOpen} onClose={() => setAskOpen(false)} />
    </div>
  );
}
