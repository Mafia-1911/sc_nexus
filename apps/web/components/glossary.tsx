import { GLOSSARY } from "@/lib/glossary";

/** A collapsible list of the abbreviations a page uses, in plain words. */
export function Glossary() {
  return (
    <details className="rounded-[var(--radius-card)] border border-border bg-surface p-3 text-sm" data-testid="glossary">
      <summary className="cursor-pointer font-medium">Abbreviations</summary>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        {GLOSSARY.map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <dt className="w-24 shrink-0 font-semibold">{k}</dt>
            <dd className="text-muted">{v}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
