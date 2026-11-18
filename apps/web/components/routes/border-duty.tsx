"use client";

import { ChevronDown, ChevronUp, Landmark } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { DataBadge } from "@/components/data-badge";
import { RateRows } from "@/components/tariffs/rate-rows";
import { MARKET_NAME, type TariffMatrix, cellText } from "@/lib/c6";

export type BorderDuty =
  | { direction: "export"; hs6: string; product: string; market: string; matrix: TariffMatrix; meta: { mode: string; sources?: string[]; as_of?: string } }
  | { direction: "import"; hs6: string; product: string }
  | { direction: "error"; hs6: string; product: string; message: string };

const NAMES: Record<string, string> = { BGD: "Bangladesh", VNM: "Vietnam", KHM: "Cambodia", IND: "India", CHN: "China", PAK: "Pakistan", LKA: "Sri Lanka" };

/** "Duty at the border" on the route map (T3): the border this domestic leg leads to. Real
 *  reference data with its own badge, in every mode (Q-23). */
export function BorderDutyCard({ duty }: { duty: BorderDuty }) {
  const [open, setOpen] = useState(true);
  const bgd = duty.direction === "export" ? duty.matrix.cells.find((c) => c.origin === "BGD") : undefined;
  return (
    <section
      className="absolute bottom-2 right-2 z-10 flex w-[17rem] flex-col gap-2 rounded-[var(--radius-control)] border border-border bg-surface/95 p-2 text-xs shadow-sm"
      data-testid="border-duty"
      data-reference="tariffs"
      aria-label="Duty at the border"
    >
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex items-center justify-between gap-2 text-left font-semibold">
        <span className="flex items-center gap-1">
          <Landmark className="size-3.5" aria-hidden />
          Duty at the border{!open && bgd ? `: ${cellText(bgd)}` : ""}
        </span>
        {open ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronUp className="size-3.5" aria-hidden />}
      </button>
      {open ? (
        duty.direction === "export" ? (
          <>
            <p className="text-muted">
              {duty.product} sold into {MARKET_NAME[duty.market] ?? duty.market}, by origin (this export leg ends at the port)
            </p>
            <RateRows cells={duty.matrix.cells} names={NAMES} highlight="BGD" />
            {bgd?.note_ids.length ? (
              <ul className="flex flex-col gap-1 text-muted">
                {bgd.note_ids.slice(0, 2).map((i) => (
                  <li key={i}>• {duty.matrix.notes[i]}</li>
                ))}
              </ul>
            ) : null}
            <div className="flex items-center justify-between gap-2">
              <DataBadge mode={duty.meta.mode} sources={duty.meta.sources} asOf={duty.meta.as_of} />
              <Link href={`/tariffs?hs6=${duty.hs6}&market=${duty.market}&origin=BGD`} className="text-primary hover:underline">
                How it is made up →
              </Link>
            </div>
          </>
        ) : duty.direction === "import" ? (
          <>
            <p>
              This leg brings an import inland. Bangladesh&apos;s import duty on {duty.product.toLowerCase()} has no live feed yet: the NBR
              publishes its schedule as PDF.
            </p>
            <Link href="/tariffs" className="text-primary hover:underline">
              Feed status in the Tariff Monitor →
            </Link>
          </>
        ) : (
          <p className="text-danger" role="alert">{duty.message}</p>
        )
      ) : null}
    </section>
  );
}

/** Which border a domestic leg leads to, from the place kinds (UI_PLAN §1). */
export function legDirection(originKind?: string, destKind?: string): "export" | "import" | null {
  const gate = (k?: string) => k === "port" || k === "icd";
  if (gate(originKind) && destKind === "cluster") return "import";
  if (originKind === "cluster" && gate(destKind)) return "export";
  return null;
}
