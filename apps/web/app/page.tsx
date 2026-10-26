import { Suspense } from "react";

import { AlertFeed } from "@/components/alert-feed";
import { KpiStrip } from "@/components/kpi-strip";
import { ShipmentsTable } from "@/components/shipments-table";
import { Card, CardHeader } from "@/components/ui/card";
import { VesselMap } from "@/components/vessel-map";
import { currentScenario } from "@/lib/scenario";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Control Tower");

function Skeleton({ h = "h-40" }: { h?: string }) {
  return <div className={`skeleton ${h} w-full`} />;
}

async function Tower() {
  const scenario = await currentScenario();
  return (
    <div className="flex flex-col gap-4">
      <Suspense fallback={<Skeleton h="h-28" />}>
        <KpiStrip scenario={scenario} />
      </Suspense>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Chattogram outer anchorage"
            subtitle="Vessels at anchor, moored and under way; replayed from the scenario's port simulation"
          />
          <VesselMap scenario={scenario} />
        </Card>
        <Suspense fallback={<Skeleton h="h-96" />}>
          <AlertFeed scenario={scenario} />
        </Suspense>
      </div>
      <Suspense fallback={<Skeleton />}>
        <ShipmentsTable scenario={scenario} />
      </Suspense>
    </div>
  );
}

export default function ControlTowerPage() {
  return (
    <>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Control Tower</h1>
      <p className="mb-4 text-sm text-muted">What needs attention now, with the data mode behind every number.</p>
      <Suspense fallback={<Skeleton h="h-[600px]" />}>
        <Tower />
      </Suspense>
    </>
  );
}
