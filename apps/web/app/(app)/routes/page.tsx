import { Suspense } from "react";

import { ErrorNote } from "@/components/kpi-strip";
import { Planner } from "@/components/routes/planner";
import { api } from "@/lib/api/server";
import { titled } from "@/lib/brand";
import type { Place } from "@/lib/c3";

export const generateMetadata = () => titled("Route Planner");

type Params = Promise<{ origin?: string; dest?: string }>;

async function PlannerLoader({ searchParams }: { searchParams: Params }) {
  const params = await searchParams;
  const client = await api();
  const { data } = await client.GET("/api/v1/routes/places");
  if (!data) return <ErrorNote what="places" />;
  const places = data.data as unknown as Place[];
  const known = (k?: string) => (k && places.some((p) => p.key === k) ? k : undefined);
  return <Planner places={places} origin={known(params.origin)} dest={known(params.dest)} />;
}

/** `?origin=&dest=` prefill the form (Quality Lab's "Replan" opens it from a failed lot's plant). */
export default function RoutePlannerPage({ searchParams }: { searchParams: Params }) {
  return (
    <>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Route Planner</h1>
      <p className="mb-4 text-sm text-muted">
        How do I move this cargo best? Road, rail via Kamalapur or barge via Pangaon, traded off on time, cost and CO2e, with
        the chance of making the deadline.
      </p>
      <Suspense fallback={<div className="skeleton h-40 w-full" />}>
        <PlannerLoader searchParams={searchParams} />
      </Suspense>
    </>
  );
}
