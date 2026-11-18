"use client";

import { Landmark } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { loadTariffCheck } from "@/app/(app)/tariffs/actions";
import { DataBadge } from "@/components/data-badge";
import { RateRows } from "@/components/tariffs/rate-rows";
import { Badge } from "@/components/ui/badge";
import { DIRECTION, MARKET_NAME, pct } from "@/lib/c6";

type Loaded = Awaited<ReturnType<typeof loadTariffCheck>>;
const NAMES: Record<string, string> = { BGD: "Bangladesh", VNM: "Vietnam", KHM: "Cambodia", IND: "India", CHN: "China", PAK: "Pakistan", LKA: "Sri Lanka" };
const PRODUCT: Record<string, string> = { "610910": "Cotton T-shirts", "620342": "Cotton denim trousers", "300490": "Medicaments" };

/** "Tariff check" on a trade-policy event (T5): the story's reading next to today's schedule. */
export function TariffCheck({ eventId }: { eventId: string }) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  useEffect(() => {
    let live = true;
    loadTariffCheck(eventId).then((r) => live && setLoaded(r));
    return () => {
      live = false;
    };
  }, [eventId]);
  const n = loaded?.news;
  const look = n ? (DIRECTION[n.direction] ?? DIRECTION.unknown) : null;
  return (
    <section className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-border p-3" data-testid="tariff-check" data-reference="tariffs">
      <h3 className="flex items-center gap-1 text-sm font-semibold">
        <Landmark className="size-4" aria-hidden />
        Tariff check
      </h3>
      {loaded === null ? (
        <p className="text-xs text-muted">Reading the story and the schedule…</p>
      ) : loaded.error && !loaded.data ? (
        <p className="text-xs text-danger" role="alert">{loaded.error}</p>
      ) : (
        <>
          {n && look ? (
            <div className="flex flex-col gap-1 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-muted">The news says:</span>
                <Badge tone={look.tone}>{look.label}{n.status === "threatened" ? " (threatened)" : ""}</Badge>
                {n.markets.length ? <span>{n.markets.map((m) => MARKET_NAME[m] ?? m).join(", ")}</span> : null}
                {n.origins.length ? <span>on {n.origins.map((o) => NAMES[o] ?? o).join(", ")}</span> : null}
                {n.rate_pct !== null && n.rate_pct !== undefined ? (
                  <span className="tabular">{n.previous_pct !== null && n.previous_pct !== undefined ? `${pct(n.previous_pct)} → ` : ""}{pct(n.rate_pct)}</span>
                ) : null}
              </div>
              <Badge tone={n.confirmed ? "ok" : "info"} className="self-start">{n.confirmed ? "In the schedule" : "Announced, not in the schedule yet"}</Badge>
              {n.quote ? <span className="italic text-muted">Read from: “{n.quote}”</span> : null}
            </div>
          ) : (
            <p className="text-xs text-muted">The story names no tariff move the rules can read; matching by country and industry only.</p>
          )}
          {loaded.data && loaded.scope ? (
            <div className="flex flex-col gap-2 text-xs">
              <span className="text-muted">The schedule says today:</span>
              {loaded.scope.markets.map((m) =>
                loaded.scope!.hs6.map((h) => (
                  <div key={`${m}:${h}`}>
                    <p className="mb-1 font-medium">{PRODUCT[h] ?? h} into {MARKET_NAME[m] ?? m}</p>
                    <RateRows cells={loaded.data!.cells.filter((c) => c.market === m && c.hs6 === h)} names={NAMES} highlight="BGD" />
                  </div>
                )),
              )}
              <div className="flex items-center justify-between gap-2">
                {loaded.meta ? <DataBadge mode={loaded.meta.mode} sources={loaded.meta.sources} asOf={loaded.meta.as_of} /> : null}
                <Link href="/tariffs" className="text-primary hover:underline">Tariff Monitor →</Link>
              </div>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
