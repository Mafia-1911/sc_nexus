"use client";

import { Landmark } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { loadNodeTariffs } from "@/app/(app)/tariffs/actions";
import { DataBadge } from "@/components/data-badge";
import { RateRows } from "@/components/tariffs/rate-rows";
import { productName } from "@/lib/c1";
import { MARKET_NAME, type TariffMatrix, marketOf } from "@/lib/c6";

const ORIGINS = ["BGD", "VNM", "CHN"];
const NAMES: Record<string, string> = { BGD: "Bangladesh", VNM: "Vietnam", CHN: "China" };

type Loaded = Awaited<ReturnType<typeof loadNodeTariffs>>;

/** Tariff card in the node drawer (T4): only where the node's flow crosses a border. The firm is
 *  fictional (synthetic); the tariffs are real reference data with their own badge (Q-23). */
export function NodeTariffs({
  type,
  kind,
  country,
  ordered,
  supplied,
}: {
  type: string;
  kind: string;
  country: string | null | undefined;
  ordered: string[]; // SKUs a buyer orders
  supplied: string[]; // SKUs a supplier supplies
}) {
  const market = marketOf(country);
  const buyer = type === "customer_site" && market && market !== "BGD";
  // an overseas *supplier* ships into Bangladesh; customers abroad and transshipment hubs do not
  const overseas =
    !buyer && type !== "customer_site" && type !== "hub" && kind !== "port" && !!country && country.toUpperCase() !== "BD";
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const key = `${ordered.join(",")}|${market}`;
  useEffect(() => {
    if (!buyer || !market) return;
    let live = true;
    loadNodeTariffs(ordered, market, ORIGINS).then((r) => live && setLoaded(r));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` captures ordered + market
  }, [key, buyer]);

  if (!buyer && !overseas) return null;
  return (
    <section className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-border p-3" data-testid="node-tariffs" data-reference="tariffs">
      <h3 className="flex items-center gap-1 text-xs font-semibold text-muted">
        <Landmark className="size-3.5" aria-hidden />
        {buyer ? `Duty into ${MARKET_NAME[market as string] ?? market} on what this buyer orders` : "Duty on what this supplier sends to Bangladesh"}
      </h3>
      {buyer ? (
        loaded === null ? (
          <p className="text-xs text-muted">Loading tariffs…</p>
        ) : loaded.error ? (
          <p className="text-xs text-danger" role="alert">{loaded.error}</p>
        ) : !loaded.products?.length || !loaded.data ? (
          <p className="text-xs text-muted">None of its products is on the tariff watchlist.</p>
        ) : (
          <>
            {loaded.products.map((p) => (
              <div key={p.hs6} className="text-xs">
                <p className="mb-1 font-medium">
                  {p.name} <span className="tabular text-muted">HS {p.hs6}</span>
                </p>
                <RateRows cells={(loaded.data as TariffMatrix).cells.filter((c) => c.hs6 === p.hs6)} names={NAMES} highlight="BGD" />
              </div>
            ))}
            <div className="flex items-center justify-between gap-2 text-xs">
              {loaded.meta ? <DataBadge mode={loaded.meta.mode} sources={loaded.meta.sources} asOf={loaded.meta.as_of} /> : null}
              <Link href={`/tariffs?market=${market}&origin=BGD&view=markets`} className="text-primary hover:underline">
                Tariff Monitor →
              </Link>
            </div>
          </>
        )
      ) : (
        <p className="text-xs">
          Bangladesh&apos;s import duty on {supplied.length ? supplied.map((s) => productName(s).toLowerCase()).join(", ") : "its products"} has no live
          feed yet (the NBR publishes its schedule as PDF).{" "}
          <Link href="/tariffs" className="text-primary hover:underline">
            Feed status →
          </Link>
        </p>
      )}
    </section>
  );
}
