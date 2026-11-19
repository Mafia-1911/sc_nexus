import { Suspense } from "react";

import { ErrorNote } from "@/components/kpi-strip";
import { TariffWorkbench } from "@/components/tariffs/workbench";
import { api } from "@/lib/api/server";
import { titled } from "@/lib/brand";
import { MARKETS } from "@/lib/c6";

export const generateMetadata = () => titled("Tariff Monitor");

type Params = Promise<{ industry?: string; view?: string; origin?: string; market?: string; hs6?: string }>;

const ORIGIN = /^[A-Z]{3}$/;

async function Tariffs({ searchParams }: { searchParams: Params }) {
  const p = await searchParams;
  const industry = p.industry === "pharma" ? "pharma" : "garments";
  const view = p.view === "origins" ? "origins" : "markets";
  const origin = p.origin && ORIGIN.test(p.origin) ? p.origin : "BGD";
  const market = MARKETS.some((m) => m.code === p.market) ? (p.market as string) : "USA";
  const client = await api();
  const matrixQuery = view === "markets" ? { industry, origin: [origin] } : { industry, market: [market] };
  const [overview, matrix, changes, notices, news] = await Promise.all([
    client.GET("/api/v1/tariffs/overview"),
    client.GET("/api/v1/tariffs/matrix", { params: { query: matrixQuery } }),
    client.GET("/api/v1/tariffs/changes", { params: { query: { limit: 40 } } }),
    client.GET("/api/v1/tariffs/notices", { params: { query: { limit: 25 } } }),
    client.GET("/api/v1/tariffs/news", { params: { query: { limit: 30 } } }),
  ]);
  if (!overview.data || !matrix.data) return <ErrorNote what="tariffs" />;
  const hs6 = p.hs6 && /^\d{6}$/.test(p.hs6) ? p.hs6 : null;
  const detail = hs6
    ? await client.GET("/api/v1/tariffs/products/{hs6}", { params: { path: { hs6 }, query: { market: [market] } } })
    : null;
  return (
    <TariffWorkbench
      key={`${industry}:${view}:${origin}:${market}:${p.hs6 ?? ""}`}
      overview={overview.data.data}
      overviewMeta={overview.data.meta}
      matrix={matrix.data.data}
      matrixMeta={matrix.data.meta}
      changes={changes.data?.data ?? []}
      notices={notices.data?.data ?? []}
      news={news.data?.data ?? []}
      industry={industry}
      view={view}
      origin={origin}
      market={market}
      initialDetail={detail?.data?.data ?? null}
    />
  );
}

export default function TariffMonitorPage({ searchParams }: { searchParams: Params }) {
  return (
    <>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Tariff Monitor</h1>
      <p className="mb-4 text-sm text-muted">
        What duty does each product pay where it is sold, and what changed? Official schedules, checked daily, with every rate
        traced to its legal line; news shows what is announced before the schedule moves.
      </p>
      <Suspense fallback={<div className="skeleton h-[720px] w-full" />}>
        <Tariffs searchParams={searchParams} />
      </Suspense>
    </>
  );
}
