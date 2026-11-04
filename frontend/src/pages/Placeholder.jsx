export default function Placeholder({ title, phase }) {
  return (
    <div className="mx-auto max-w-[1400px] p-4 lg:p-6">
      <h1 className="text-xl font-bold">{title}</h1>
      <div className="mt-4 rounded-xl border border-dashed border-border bg-surface p-10 text-center text-sm text-muted">
        This page is built in {phase}.
      </div>
    </div>
  );
}
