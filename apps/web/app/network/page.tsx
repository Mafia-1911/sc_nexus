import { Suspense } from "react";

import { ErrorNote } from "@/components/kpi-strip";
import { NetworkWorkbench } from "@/components/network/workbench";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { titled } from "@/lib/brand";
import type { Metric } from "@/lib/c1";
import { currentScenario } from "@/lib/scenario";

export const generateMetadata = () => titled("Supplier Network");

type Params = Promise<{ industry?: string; metric?: string }>;

const METRIC_KEYS: Metric[] = ["dominance", "downstream", "tts_gap", "risk"];

async function Network({ searchParams }: { searchParams: Params }) {
  const params = await searchParams;
  const scenario = await currentScenario();
  if (!scenario) {
    return (
      <Card>
        <p className="text-sm">
          The supply network is synthetic: fictional firms at real Bangladeshi clusters. Pick a scenario in the top bar to see
          it; real-data-only mode has no network.
        </p>
      </Card>
    );
  }
  const industry = params.industry === "garments" || params.industry === "pharma" ? params.industry : null;
  const metric = METRIC_KEYS.includes(params.metric as Metric) ? (params.metric as Metric) : "dominance";
  const client = await api();
  const query = { scenario, ...(industry ? { industry } : {}) };
  const [graph, critical] = await Promise.all([
    client.GET("/api/v1/graph", { params: { query } }),
    client.GET("/api/v1/graph/critical", { params: { query: { ...query, metric, limit: 15 } } }),
  ]);
  if (!graph.data || !critical.data) return <ErrorNote what="the supply network" />;
  return (
    <NetworkWorkbench
      key={`${scenario}:${industry}:${metric}`}
      graph={graph.data.data}
      meta={graph.data.meta}
      critical={critical.data.data}
      scenario={scenario}
      industry={industry}
      metric={metric}
    />
  );
}

export default function SupplierNetworkPage({ searchParams }: { searchParams: Params }) {
  return (
    <>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Supplier Network</h1>
      <p className="mb-4 text-sm text-muted">
        Where are we fragile? Single points of failure, how long the network survives without each node, and what a disruption
        does to open orders.
      </p>
      <Suspense fallback={<div className="skeleton h-[640px] w-full" />}>
        <Network searchParams={searchParams} />
      </Suspense>
    </>
  );
}
