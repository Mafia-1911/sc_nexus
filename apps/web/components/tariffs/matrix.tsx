"use client";

import { Info } from "lucide-react";

import {
  boundWords,
  type TariffCell,
  type TariffMatrix,
  type TariffOverview,
  TIER_CLASS,
  TIERS,
  cellText,
  countryName,
  marketSource,
  tierOf,
} from "@/lib/c6";
import { cn } from "@/lib/utils";

export type Selection = { hs6: string; market: string; origin: string };

/** Hatched look for "no single number": the floor is shown, never a guess. */
export const UNRESOLVED = "border border-border-strong text-text [background:repeating-linear-gradient(135deg,var(--surface-2)_0_6px,var(--surface)_6px_12px)]";

export function cellClass(c: Pick<TariffCell, "is_resolved" | "effective_pct_max" | "n_lines">): string {
  if (c.n_lines === 0) return "border border-dashed border-border text-muted";
  if (!c.is_resolved || c.effective_pct_max === null || c.effective_pct_max === undefined) return UNRESOLVED;
  return TIER_CLASS[String(tierOf(c.effective_pct_max))];
}

export function Legend() {
  return (
    <ul className="flex flex-wrap items-center gap-2 text-xs text-muted" aria-label="Colour key" data-testid="tariff-legend">
      {TIERS.map((t) => (
        <li key={t.label} className="flex items-center gap-1">
          <span className={cn("inline-block h-3 w-5 rounded-sm", TIER_CLASS[String(t.tier)])} aria-hidden />
          {t.label}
        </li>
      ))}
      <li className="flex items-center gap-1">
        <span className={cn("inline-block h-3 w-5 rounded-sm", UNRESOLVED)} aria-hidden />no single number: ≥ at least, ≤ at most, a range, or varies (hover for why)
      </li>
      <li className="flex items-center gap-1">
        <span className="font-semibold text-text" aria-hidden>≤</span> at most: preferences not in the data
      </li>
      <li className="flex items-center gap-1">
        <span className="inline-block h-3 w-5 rounded-sm border border-dashed border-border" aria-hidden />— no tariff line
      </li>
    </ul>
  );
}

/** Products × markets (or × origins): the effective duty per cell, on the depth ramp. */
export function Matrix({
  matrix,
  overview,
  view,
  origin,
  market,
  selected,
  onSelect,
}: {
  matrix: TariffMatrix;
  overview: TariffOverview;
  view: "markets" | "origins";
  origin: string;
  market: string;
  selected: Selection | null;
  onSelect: (s: Selection) => void;
}) {
  const cols =
    view === "markets"
      ? overview.markets.map((m) => ({ key: m.code, label: m.name, chip: marketSource(m.code, m.live_source) }))
      : overview.origins.map((o) => ({ key: o.iso3, label: o.name, chip: null }));
  const hs6s = [...new Set(matrix.cells.map((c) => c.hs6))];
  const products = overview.products.filter((p) => hs6s.includes(p.hs6));
  const at = new Map(matrix.cells.map((c) => [`${c.hs6}:${view === "markets" ? c.market : c.origin}`, c]));
  const fixed = view === "markets" ? countryName(overview.origins, origin) : overview.markets.find((m) => m.code === market)?.name;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="tariff-matrix">
        <caption className="sr-only">
          Effective duty {view === "markets" ? `on goods from ${fixed}, by market` : `into ${fixed}, by origin`}
        </caption>
        <thead>
          <tr className="text-left text-xs text-muted">
            <th scope="col" className="sticky left-0 bg-surface py-2 pr-3 font-medium">Product (HS6)</th>
            {cols.map((c) => (
              <th key={c.key} scope="col" className="min-w-[7.5rem] px-1 py-2 font-medium">
                <span className="block text-text">{c.label}</span>
                {c.chip ? (
                  <span className="block text-[11px] font-normal" title={c.chip.title}>
                    {c.chip.label}
                  </span>
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {products.map((p) => (
            <tr key={p.hs6} className="border-t border-border">
              <th scope="row" className="sticky left-0 bg-surface py-1.5 pr-3 text-left font-normal">
                <span className="block">{p.name}</span>
                <span className="tabular text-xs text-muted">{p.hs6}</span>
              </th>
              {cols.map((col) => {
                const c = at.get(`${p.hs6}:${col.key}`);
                if (!c) return <td key={col.key} className="px-1 py-1.5 text-muted">—</td>;
                const sel: Selection = { hs6: p.hs6, market: c.market, origin: c.origin };
                const active = selected?.hs6 === sel.hs6 && selected.market === sel.market && selected.origin === sel.origin;
                const label = `${p.name} into ${view === "markets" ? col.label : fixed} from ${view === "markets" ? fixed : col.label}: ${
                  c.is_resolved ? `${c.is_ceiling ? "at most " : ""}${cellText(c).replace("≤ ", "")}` : boundWords(c.lower_pct, c.upper_pct)
                }`;
                return (
                  <td key={col.key} className="px-1 py-1.5">
                    <button
                      type="button"
                      onClick={() => onSelect(sel)}
                      aria-pressed={active}
                      aria-label={label}
                      title={matrix.notes.length && c.note_ids.length ? c.note_ids.map((i) => matrix.notes[i]).join("\n") : undefined}
                      data-cell={`${c.market}:${c.hs6}:${c.origin}`}
                      className={cn(
                        "tabular flex w-full items-center justify-between gap-1 rounded-[var(--radius-control)] px-2 py-1.5 text-left font-medium",
                        cellClass(c),
                        active && "outline outline-2 outline-offset-1 outline-[var(--focus)]",
                      )}
                    >
                      <span>{cellText(c)}</span>
                      {!c.is_resolved && c.n_lines > 0 ? <Info className="size-3.5 shrink-0" aria-hidden /> : null}
                      {c.is_stale ? <span className="text-[10px] font-normal">2023</span> : null}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
