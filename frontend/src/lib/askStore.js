// Per-browser conveniences for Ask the Data: last 10 questions and pinned answers.
// localStorage is wrapped in try/catch everywhere (private windows / blocked storage just disable these).
const HISTORY = 'pa-ask-history';
const PINS = 'pa-ask-pins';
const EVT = 'pa-ask-pins-changed';

const read = (k) => { try { return JSON.parse(localStorage.getItem(k) || '[]'); } catch { return []; } };
const write = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; } };

export const getHistory = () => read(HISTORY);
export function addHistory(q) {
  const h = [q, ...read(HISTORY).filter((x) => x !== q)].slice(0, 10);
  write(HISTORY, h);
  return h;
}

export const getPins = () => read(PINS);
export function addPin(pin) {
  const pins = [{ ...pin, id: `${Date.now()}`, pinnedAt: new Date().toISOString() }, ...read(PINS)].slice(0, 12);
  const ok = write(PINS, pins);
  window.dispatchEvent(new Event(EVT));
  return ok;
}
export function removePin(id) {
  write(PINS, read(PINS).filter((p) => p.id !== id));
  window.dispatchEvent(new Event(EVT));
}
export const onPinsChanged = (fn) => {
  window.addEventListener(EVT, fn);
  return () => window.removeEventListener(EVT, fn);
};
