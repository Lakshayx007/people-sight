import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import {
  ArrowRight, Briefcase, ClipboardCheck, Code2, Lightbulb, MessageSquareText, ShieldCheck, Smile, Sparkles, Users,
} from 'lucide-react';
import { useApi } from '../lib/api';
import { fmtInt, fmtPct, fmtSigned, isNum } from '../lib/format';
import { CountUp, FadeIn, Stagger, item } from '../lib/motion';

const AREA = {
  Sentiment: { icon: Smile, to: '/sentiment', label: 'Employee sentiment' },
  Hiring: { icon: Briefcase, to: '/hiring', label: 'Hiring' },
};

export default function Landing() {
  const reduce = useReducedMotion();
  const home = useApi('/home', { method: 'get' });
  const h = home.data?.[0] || {};
  const ready = !!home.data;

  const stats = [
    { label: 'eNPS, April → October', value: ready ? `${fmtSigned(h.enps_apr)} → ${fmtSigned(h.enps_oct)}` : '…', note: `${fmtInt(h.n_oct)} people answered in October` },
    { label: 'Days to fill a typical opening', value: ready ? fmtInt(h.h_median_ttf_days) : '…', note: `${fmtPct(h.h_pct_within_sla, 0)} filled within target` },
    { label: 'Offers accepted', value: ready ? fmtPct(h.h_offer_acceptance_pct) : '…', note: `${fmtInt(h.h_offers_accepted)} of ${fmtInt((h.h_offers_accepted || 0) + (h.h_offers_declined || 0))} offers` },
    { label: 'Data checks run', value: ready ? fmtInt(h.rules) : '…', note: `${fmtInt(h.issues_treated)} problems fixed before analysis` },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* ── hero ─────────────────────────────────────────────────────────── */}
      <section className="relative isolate flex min-h-[100svh] flex-col overflow-hidden bg-ink text-white">
        <div className="hero-grid pointer-events-none absolute inset-0 -z-10" />
        <motion.div aria-hidden className="pointer-events-none absolute -left-40 top-10 -z-10 h-[520px] w-[520px] rounded-full bg-[#2563EB]/30 blur-[120px]"
          animate={reduce ? undefined : { x: [0, 40, 0], y: [0, 30, 0] }} transition={{ duration: 18, repeat: Infinity, ease: 'easeInOut' }} />
        <motion.div aria-hidden className="pointer-events-none absolute -right-32 bottom-0 -z-10 h-[460px] w-[460px] rounded-full bg-[#60A5FA]/20 blur-[120px]"
          animate={reduce ? undefined : { x: [0, -30, 0], y: [0, -40, 0] }} transition={{ duration: 22, repeat: Infinity, ease: 'easeInOut' }} />

        <nav className="mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
          <Link to="/" className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-white/10 ring-1 ring-white/15"><Users className="h-5 w-5" /></span>
            <span className="leading-tight">
              <span className="block text-[10px] font-semibold uppercase tracking-[0.2em] text-white/60">Porter</span>
              <span className="block text-sm font-bold">People Sight</span>
            </span>
          </Link>
          <div className="flex items-center gap-1 text-sm">
            <Link to="/sentiment" className="hidden rounded-lg px-3 py-2 text-white/75 hover:text-white sm:block">Sentiment</Link>
            <Link to="/hiring" className="hidden rounded-lg px-3 py-2 text-white/75 hover:text-white sm:block">Hiring</Link>
            <Link to="/data-quality" className="hidden rounded-lg px-3 py-2 text-white/75 hover:text-white md:block">Data quality</Link>
            <Link to="/sentiment" className="ml-2 rounded-lg bg-white px-3.5 py-2 text-sm font-semibold text-ink hover:bg-white/90">Open dashboards</Link>
          </div>
        </nav>

        <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center px-5 pb-16 pt-6 sm:px-8">
          <Stagger gap={0.1}>
            <motion.div variants={item} className="mb-5 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs text-white/80 ring-1 ring-white/15">
              <Sparkles className="h-3.5 w-3.5 text-[#93C5FD]" /> Employee surveys and hiring, April–October 2026
            </motion.div>
            <motion.h1 variants={item} className="font-display max-w-4xl text-[40px] font-semibold leading-[1.05] sm:text-6xl lg:text-7xl">
              See how your people feel and <span className="text-[#93C5FD]">how well you hire.</span>
            </motion.h1>
            <motion.p variants={item} className="mt-6 max-w-2xl text-base leading-7 text-white/75 sm:text-lg">
              Employee sentiment and hiring performance in one place, built on cleaned and audited data. Every chart states its
              key takeaway, shows the query behind it, and can be summarised by AI on request.
            </motion.p>
            <motion.div variants={item} className="mt-8 flex flex-wrap gap-3">
              <Link to="/sentiment" className="group inline-flex items-center gap-2 rounded-xl bg-[#2563EB] px-5 py-3 text-sm font-semibold shadow-lg shadow-[#2563EB]/30 hover:bg-[#1D4ED8]">
                Explore employee sentiment <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
              <Link to="/hiring" className="inline-flex items-center gap-2 rounded-xl bg-white/10 px-5 py-3 text-sm font-semibold ring-1 ring-white/20 hover:bg-white/15">
                Explore hiring <ArrowRight className="h-4 w-4" />
              </Link>
            </motion.div>
          </Stagger>

          <Stagger className="mt-14 grid grid-cols-2 gap-3 lg:grid-cols-4" gap={0.08}>
            {stats.map((s) => (
              <motion.div key={s.label} variants={item} className="rounded-2xl bg-white/[0.06] p-4 ring-1 ring-white/10 backdrop-blur">
                <div className="text-[11px] font-medium uppercase tracking-wide text-white/55">{s.label}</div>
                <div className="mt-1 text-2xl font-bold tabular-nums sm:text-3xl">{ready ? <CountUp text={s.value} /> : <span className="text-white/40">…</span>}</div>
                <div className="mt-1 text-xs text-white/55">{ready ? s.note : ' '}</div>
              </motion.div>
            ))}
          </Stagger>
        </div>
      </section>

      {/* ── findings ─────────────────────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
        <FadeIn>
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Key findings</div>
          <h2 className="font-display mt-2 max-w-3xl text-3xl font-semibold leading-tight sm:text-4xl">What the data shows</h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
            Generated from the same data as the dashboards, so they always match. Open a dashboard to see the evidence behind each one.
          </p>
        </FadeIn>
        {home.loading && !home.data ? (
          <div className="mt-8 grid gap-4 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-32" />)}</div>
        ) : (
          <Stagger className="mt-8 grid gap-4 md:grid-cols-2">
            {(h.findings || []).map((f, i) => {
              const A = AREA[f.area] || AREA.Sentiment;
              return (
                <motion.div key={i} variants={item}>
                  <Link to={A.to} className="card group flex h-full gap-4 p-5 transition-transform hover:-translate-y-0.5 hover:border-accent/50">
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent-soft"><A.icon className="h-5 w-5 text-accent" /></span>
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{A.label}</div>
                      <p className="mt-1 text-[15px] leading-6">{f.text.replace(' Click to see their full picture.', '')}</p>
                      <span className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent">See the evidence <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" /></span>
                    </div>
                  </Link>
                </motion.div>
              );
            })}
          </Stagger>
        )}
      </section>

      {/* ── how it works ─────────────────────────────────────────────────── */}
      <section className="border-y border-border bg-surface">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
          <FadeIn>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">How it works</div>
            <h2 className="font-display mt-2 text-3xl font-semibold leading-tight sm:text-4xl">Built to be trusted and easy to act on</h2>
          </FadeIn>
          <Stagger className="mt-10 grid gap-4 md:grid-cols-3">
            {[
              { icon: ShieldCheck, t: 'Cleaned and audited', d: `${isNum(h.rules) ? fmtInt(h.rules) : 'Every'} checks ran on the raw spreadsheets before any number was calculated. Every fix is logged.`, to: '/data-quality', cta: 'See what we fixed' },
              { icon: Lightbulb, t: 'Clear takeaways', d: 'Each chart opens with its key takeaway. “What does this chart say?” adds a short AI summary based on the same numbers.', to: '/sentiment', cta: 'Open a dashboard' },
              { icon: Code2, t: 'Fully transparent', d: 'Every chart shows the exact SQL behind it, and small groups (under 5 people) are hidden to protect anonymity.', to: '/hiring', cta: 'Try it on hiring' },
            ].map((c) => (
              <motion.div key={c.t} variants={item} className="card flex flex-col p-6">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-accent-soft"><c.icon className="h-5 w-5 text-accent" /></span>
                <h3 className="mt-4 text-lg font-semibold">{c.t}</h3>
                <p className="mt-2 flex-1 text-sm leading-6 text-muted">{c.d}</p>
                <Link to={c.to} className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent">{c.cta} <ArrowRight className="h-4 w-4" /></Link>
              </motion.div>
            ))}
          </Stagger>

          <FadeIn className="mt-10">
            <div className="flex flex-col items-start gap-4 rounded-2xl bg-ink p-6 text-white shadow-lg sm:flex-row sm:items-center sm:justify-between sm:p-8">
              <div className="flex gap-4">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-white/10"><MessageSquareText className="h-5 w-5" /></span>
                <div>
                  <h3 className="text-lg font-semibold">Ask the data a question</h3>
                  <p className="mt-1 max-w-xl text-sm leading-6 text-white/70">
                    “Which teams are least positive?” “How long does hiring take by grade?” Get a chart, a one-line summary and the query behind it. Queries are read-only and survey answers stay anonymous.
                  </p>
                </div>
              </div>
              <Link to="/sentiment#ask" className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-ink hover:bg-white/90">
                <Sparkles className="h-4 w-4" /> Ask the data
              </Link>
            </div>
          </FadeIn>
        </div>
      </section>

      <footer className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-8 text-xs text-muted sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <span className="flex items-center gap-2"><ClipboardCheck className="h-4 w-4" /> People Sight · Porter People Analytics · data as of 31-Oct-2026 (synthetic case data)</span>
        <a href="https://github.com/Lakshayx007/people-sight" className="hover:text-primary">Source code on GitHub</a>
      </footer>
    </div>
  );
}
