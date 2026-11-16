import { Suspense } from "react";

import { ErrorNote } from "@/components/kpi-strip";
import { Provenance } from "@/components/data-badge";
import { HeatImage } from "@/components/quality/heat-image";
import { QualityLab, type Summary } from "@/components/quality/quality-lab";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { titled } from "@/lib/brand";
import { currentScenario } from "@/lib/scenario";

export const generateMetadata = () => titled("Quality Lab");

async function Lab() {
  const scenario = await currentScenario();
  const client = await api();
  if (!scenario) return <RealQuality />;
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

/** Real data (A-111): no plant publishes its QC lots, so only the real public images show. */
async function RealQuality() {
  const client = await api();
  const { data } = await client.GET("/api/v1/quality/gallery", { params: { query: { limit: 24 } } });
  const items = data?.data ?? [];
  return (
    <div className="flex flex-col gap-4" data-testid="quality-real">
      <Card>
        <CardHeader
          title="No real inspection lots"
          subtitle="Lots, lines and SPC need a plant's own QC data, which no Bangladeshi factory publishes. Pick a synthetic scenario in the top bar to see them. Below: the anomaly model on real public images (MVTec AD, StitchNet), with heatmaps."
        />
      </Card>
      <Card>
        <CardHeader title="Model on real public images" subtitle={`${items.length} images · red = where the model sees an anomaly`} />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6" data-testid="gallery">
          {items.map((it) => (
            <HeatImage key={it.id} item={it as Parameters<typeof HeatImage>[0]["item"]} opacity={0.55} />
          ))}
        </div>
        {data ? (
          <CardFooter>
            <Provenance meta={data.meta} />
          </CardFooter>
        ) : null}
      </Card>
    </div>
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
