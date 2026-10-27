import { Suspense } from "react";

import { loadSnapshot } from "@/app/ports/actions";
import { ErrorNote } from "@/components/kpi-strip";
import { PortView } from "@/components/ports/port-view";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Ports & Vessels");

async function PortLoader() {
  const latest = await loadSnapshot("BDCGP");
  if (!latest.data) return <ErrorNote what="port predictions" />;
  // The latest snapshot's history doubles as "what happened" for earlier forecasts (replay).
  const actual = latest.data.forecast.history as [string, number][];
  return <PortView locode="BDCGP" initial={latest.data} actual={actual} />;
}

export default function PortsPage() {
  return (
    <>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Ports &amp; Vessels · Chattogram</h1>
      <p className="mb-4 text-sm text-muted">
        When will each vessel leave, and how crowded will the outer anchorage be? Dwell is anchorage wait plus berth time,
        with an 80 % window and the reasons behind it.
      </p>
      <Suspense fallback={<div className="skeleton h-40 w-full" />}>
        <PortLoader />
      </Suspense>
    </>
  );
}
