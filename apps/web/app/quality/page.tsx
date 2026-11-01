import { Suspense } from "react";

import { ErrorNote } from "@/components/kpi-strip";
import { QualityLab, type Summary } from "@/components/quality/quality-lab";
import { api } from "@/lib/api/server";
import { titled } from "@/lib/brand";
import { currentScenario } from "@/lib/scenario";

export const generateMetadata = () => titled("Quality Lab");

async function Lab() {
  const scenario = await currentScenario();
  const client = await api();
  const query = { scenario };
  const [summary, lots, lines, gallery] = await Promise.all([
    client.GET("/api/v1/quality/summary", { params: { query } }),
    client.GET("/api/v1/quality/batches", { params: { query } }),
    client.GET("/api/v1/quality/lines", { params: { query } }),
    client.GET("/api/v1/quality/gallery", { params: { query: { category: "stitch", limit: 24 } } }),
  ]);
  if (!summary.data || !lots.data || !lines.data || !gallery.data) return <ErrorNote what="quality data" />;
  return (
    <QualityLab
      key={scenario}
      summary={summary.data.data as unknown as Summary}
      lots={lots.data.data}
      lines={lines.data.data}
      gallery={gallery.data.data}
      scenario={scenario}
      meta={lots.data.meta}
    />
  );
}

export default function QualityLabPage() {
  return (
    <>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Quality Lab</h1>
      <p className="mb-4 text-sm text-muted">
        Is this lot OK, and what does a bad lot cost us? Anomaly heatmaps guide the inspectors, ISO 2859-1 decides the lot,
        and a failed lot becomes orders at risk with costed options.
      </p>
      <Suspense fallback={<div className="skeleton h-[600px] w-full" />}>
        <Lab />
      </Suspense>
    </>
  );
}
