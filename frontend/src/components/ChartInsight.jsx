import { Sparkles } from 'lucide-react';

/**
 * From Onco-Sight's ChartInsight. Wired up in Phase 8: the blurb is written by Groq ONLY from the rows the
 * panel already returned (Hard rule 9 — the LLM never produces new numbers).
 */
export default function ChartInsight({ insight, loading, onGenerate }) {
  if (!insight && !loading) {
    return (
      <button onClick={onGenerate} className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-md border border-border py-1.5 text-xs text-accent hover:bg-accent-soft">
        <Sparkles className="h-3.5 w-3.5" /> Explain this chart
      </button>
    );
  }
  return (
    <div className="mt-3 rounded-md border border-border bg-subtle p-2.5 text-[11px] leading-relaxed text-muted">
      <div className="mb-1 flex items-center gap-1.5 font-medium text-accent"><Sparkles className="h-3.5 w-3.5" /> AI summary</div>
      {loading ? <span className="animate-pulse">Writing summary…</span> : <span>{insight}</span>}
    </div>
  );
}
