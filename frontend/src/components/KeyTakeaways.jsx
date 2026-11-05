import { ArrowRight, CircleAlert, CircleCheck, Info } from 'lucide-react';
import { motion } from 'motion/react';
import { useFilters } from '../context/FilterContext';
import { useApi } from '../lib/api';
import { Stagger, item } from '../lib/motion';

const TONE = {
  bad: { icon: CircleAlert, cls: 'text-negative', ring: 'bg-negative/10' },
  good: { icon: CircleCheck, cls: 'text-accent', ring: 'bg-accent-soft' },
  neutral: { icon: Info, cls: 'text-accent', ring: 'bg-accent-soft' },
};

/** Three headline takeaways for a page, written by the backend from the metric SQL (with filters). */
export default function KeyTakeaways({ endpoint }) {
  const { filters, drill } = useFilters();
  const t = useApi(endpoint, { filters });
  const rows = t.data || [];
  return (
    <section aria-label="Key takeaways">
      <div className="mb-2 flex items-baseline gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">Key takeaways</h2>
        <span className="text-[11px] text-muted">updates with your filters</span>
      </div>
      {t.loading && !t.data ? (
        <div className="grid gap-3 md:grid-cols-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-24" />)}</div>
      ) : (
        <Stagger className="grid gap-3 md:grid-cols-3" key={JSON.stringify(rows).length}>
          {rows.map((r, i) => {
            const T = TONE[r.tone] || TONE.neutral;
            const clickable = r.link?.dim && r.link?.value;
            const Tag = clickable ? motion.button : motion.div;
            return (
              <Tag key={i} variants={item}
                onClick={clickable ? () => drill({ [r.link.dim]: r.link.value }) : undefined}
                className={`card flex gap-3 p-4 text-left ${clickable ? 'cursor-pointer transition-transform hover:-translate-y-0.5 hover:border-accent/50' : ''}`}>
                <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${T.ring}`}><T.icon className={`h-4 w-4 ${T.cls}`} /></span>
                <p className="text-[13.5px] leading-5">
                  {r.text}
                  {clickable && <ArrowRight className="ml-1 inline h-3.5 w-3.5 text-accent" />}
                </p>
              </Tag>
            );
          })}
        </Stagger>
      )}
    </section>
  );
}
