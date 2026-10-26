import { Suspense } from "react";

import { ModelsCard } from "@/components/data/models-card";
import { ScenariosCard } from "@/components/data/scenarios-card";
import { SourcesTable } from "@/components/data/sources-table";
import { Card, CardHeader } from "@/components/ui/card";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Data & Models");

const ATTRIBUTION = [
  "Map data © OpenStreetMap contributors; tiles OpenFreeMap",
  "Global Fishing Watch (CC BY-NC 4.0): port visits, presence, SAR detections",
  "IMF PortWatch: daily port calls",
  "GDACS, European Commission JRC: hazard events",
  "ReliefWeb (UN OCHA) and each report's source",
  "UN/LOCODE (UNECE); GeoNames; UK DESNZ conversion factors (OGL)",
  "openFDA; World Bank WDI; NASA FIRMS; Open-Meteo (CC BY 4.0)",
  "Chittagong Port Authority berthing report (manual download)",
];

export default function DataPage() {
  return (
    <>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Data & Models</h1>
      <p className="mb-4 text-sm text-muted">Can I trust this? Sources, modes, freshness, licences and models.</p>
      <div className="flex flex-col gap-4">
        <Suspense fallback={<div className="skeleton h-96 w-full" />}>
          <SourcesTable />
        </Suspense>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Suspense fallback={<div className="skeleton h-48 w-full" />}>
            <ScenariosCard />
          </Suspense>
          <Suspense fallback={<div className="skeleton h-48 w-full" />}>
            <ModelsCard />
          </Suspense>
        </div>
        <Card>
          <CardHeader title="Attributions" subtitle="Credits required by the sources' terms" />
          <ul className="list-disc pl-5 text-sm text-muted">
            {ATTRIBUTION.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
