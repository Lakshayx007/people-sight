import { useEffect, useRef, useState } from 'react';
import { animate, motion, useInView, useReducedMotion } from 'motion/react';

/** Fade + rise into view once (respects "reduce motion"). */
export function FadeIn({ children, delay = 0, y = 12, className = '', as = 'div', ...rest }) {
  const reduce = useReducedMotion();
  const M = motion[as] || motion.div;
  return (
    <M className={className} initial={reduce ? false : { opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }} transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }} {...rest}>
      {children}
    </M>
  );
}

/** Children appear one after another. */
export function Stagger({ children, className = '', gap = 0.07 }) {
  const reduce = useReducedMotion();
  return (
    <motion.div className={className} initial={reduce ? false : 'hidden'} whileInView="show" viewport={{ once: true, margin: '-40px' }}
      variants={{ show: { transition: { staggerChildren: gap } } }}>
      {children}
    </motion.div>
  );
}

export const item = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } },
};

/**
 * Counts up the first number inside an already formatted string ("+3.3", "70.4%", "₹8.07 L", "1,665").
 * Display only: the final text is exactly the string the API-backed formatter produced.
 */
export function CountUp({ text, duration = 0.9 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(text);
  useEffect(() => {
    const m = typeof text === 'string' ? text.match(/^([^\d]*)([\d,]+(?:\.\d+)?)(.*)$/) : null;
    if (!m || reduce || !inView) { setShown(text); return undefined; }
    const [, pre, digits, post] = m;
    const target = parseFloat(digits.replace(/,/g, ''));
    const dec = (digits.split('.')[1] || '').length;
    const grouped = digits.includes(',');
    const ctl = animate(0, target, {
      duration, ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => {
        const s = grouped ? Math.round(v).toLocaleString('en-IN') : v.toFixed(dec);
        setShown(`${pre}${s}${post}`);
      },
      onComplete: () => setShown(text),
    });
    return () => ctl.stop();
  }, [text, inView, reduce, duration]);
  return <span ref={ref}>{shown}</span>;
}

/** Wraps a routed page: soft fade/slide between pages. */
export function PageTransition({ children, k }) {
  const reduce = useReducedMotion();
  return (
    <motion.div key={k} initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}>
      {children}
    </motion.div>
  );
}
