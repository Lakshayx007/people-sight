import { FadeIn } from '../lib/motion';

export default function PageHeader({ eyebrow, title, children }) {
  return (
    <FadeIn y={6}>
      {eyebrow && <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">{eyebrow}</div>}
      <h1 className="font-display text-2xl font-semibold leading-tight sm:text-[28px]">{title}</h1>
      {children && <p className="mt-1 max-w-3xl text-sm leading-6 text-muted">{children}</p>}
    </FadeIn>
  );
}
