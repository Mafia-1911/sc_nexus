import { Suspense } from "react";

import { ErrorNote } from "@/components/kpi-strip";
import { RadarWorkbench } from "@/components/radar/workbench";
import { api } from "@/lib/api/server";
import { titled } from "@/lib/brand";
import { currentScenario } from "@/lib/scenario";

export const generateMetadata = () => titled("Disruption Radar");

type Params = Promise<{ source?: string }>;

async function Radar({ searchParams }: { searchParams: Params }) {
  const params = await searchParams;
  const source = params.source === "feeds" || params.source === "all" ? params.source : "news";
  const scenario = await currentScenario();
  const client = await api();
  const { data } = await client.GET("/api/v1/events", {
    params: { query: { scenario, limit: 80, ...(source === "all" ? {} : { source }) } },
  });
  if (!data) return <ErrorNote what="events" />;
  return <RadarWorkbench key={`${scenario}:${source}`} events={data.data} meta={data.meta} scenario={scenario} source={source} />;
}

export default function DisruptionRadarPage({ searchParams }: { searchParams: Params }) {
  return (
    <>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Disruption Radar</h1>
      <p className="mb-4 text-sm text-muted">
        What happened, and does it affect us? News and hazard feeds become grounded events: every field quotes its source.
      </p>
      <Suspense fallback={<div className="skeleton h-[560px] w-full" />}>
        <Radar searchParams={searchParams} />
      </Suspense>
    </>
  );
}
