import { UNRESOLVED } from "@/components/tariffs/matrix";
import { TIER_CLASS, type TariffCell, cellText, tierOf } from "@/lib/c6";
import { cn } from "@/lib/utils";


/** Origin → effective duty rows, each value on the same depth tier as the Tariff Monitor's cell. */
export function RateRows({ cells, names, highlight }: { cells: TariffCell[]; names: Record<string, string>; highlight?: string }) {
  return (
    <ul className="flex flex-col gap-1" data-testid="rate-rows">
      {cells.map((c) => {
        const tone = !c.is_resolved || c.effective_pct_max === null || c.effective_pct_max === undefined
          ? c.n_lines === 0 ? "border border-dashed border-border text-muted" : UNRESOLVED
          : TIER_CLASS[String(tierOf(c.effective_pct_max))];
        return (
          <li key={`${c.market}:${c.origin}`} className={cn("flex items-center justify-between gap-2", c.origin === highlight && "font-semibold")}>
            <span>{names[c.origin] ?? c.origin}</span>
            <span className={cn("tabular rounded px-1.5 py-0.5 text-xs font-medium", tone)} data-origin={c.origin}>
              {cellText(c)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
