import { Suspense } from "react";

import { loadSnapshot } from "@/app/ports/actions";
import { Glossary } from "@/components/glossary";
import { KpiStrip, ErrorNote } from "@/components/kpi-strip";
import { PortLive } from "@/components/port-live";
import { PortView } from "@/components/ports/port-view";
import { ScenarioPort } from "@/components/ports/scenario-port";
import { ShipsTable } from "@/components/ships-table";
import { Card, CardHeader } from "@/components/ui/card";
import { VesselMap } from "@/components/vessel-map";
import { titled } from "@/lib/brand";
import { currentScenario } from "@/lib/scenario";

export const generateMetadata = () => titled("Ports & Vessels");

function Skeleton({ h = "h-40" }: { h?: string }) {
  return <div className={`skeleton ${h} w-full`} />;
}

/** C4's model, replayed on the real GFW port visits it was trained on (real data only). */
async function C4Model() {
  const latest = await loadSnapshot("BDCGP");
  if (!latest.data) return <ErrorNote what="C4 predictions" />;
  const actual = latest.data.forecast.history as [string, number][];
  return <PortView locode="BDCGP" initial={latest.data} actual={actual} />;
}

/** One data source per view (A-111): the same KPIs, map and ships as the Control Tower. */
async function Ports() {
  const scenario = await currentScenario();
  return (
    <div className="flex flex-col gap-4">
      <Suspense fallback={<Skeleton h="h-28" />}>
        <KpiStrip scenario={scenario} />
      </Suspense>
      {scenario ? (
        <Card>
          <CardHeader title="Chattogram outer anchorage" subtitle="The scenario's simulated port: vessels at anchor, moored and under way" />
          <VesselMap scenario={scenario} />
        </Card>
      ) : (
        <Suspense fallback={<Skeleton h="h-96" />}>
          <PortLive />
        </Suspense>
      )}
      <Suspense fallback={<Skeleton />}>
        <ShipsTable scenario={scenario} rows={40} />
      </Suspense>
      {scenario ? (
        <Suspense fallback={<Skeleton h="h-72" />}>
          <ScenarioPort scenario={scenario} />
        </Suspense>
      ) : (
        <section className="flex flex-col gap-2" data-testid="c4-model">
          <h2 className="text-base font-semibold tracking-tight">C4 dwell and queue model · replay on GFW port visits</h2>
          <p className="text-sm text-muted">
            The forecast model as evaluated on real Global Fishing Watch port visits (its time-based holdout to 7 Sep 2026). It
            is retrained on CPA&apos;s schedule as our polling history grows; until then it describes that period, not today.
          </p>
          <Suspense fallback={<Skeleton h="h-96" />}>
            <C4Model />
          </Suspense>
        </section>
      )}
      <Glossary />
    </div>
  );
}

export default function PortsPage() {
  return (
    <>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Ports &amp; Vessels · Chattogram</h1>
      <p className="mb-4 text-sm text-muted">
        Who is waiting, who is alongside, who is coming, and how full the yards are; then the dwell model behind the
        estimates.
      </p>
      <Suspense fallback={<Skeleton h="h-[600px]" />}>
        <Ports />
      </Suspense>
    </>
  );
}
