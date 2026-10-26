import { CloudLightning, Factory, Flame, Pill, Ship, TriangleAlert, Waves } from "lucide-react";

import { Provenance } from "@/components/data-badge";
import { ErrorNote } from "@/components/kpi-strip";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { dhakaTime } from "@/lib/utils";

const ICON: Record<string, typeof Ship> = {
  CYCLONE_STORM: CloudLightning,
  FLOOD: Waves,
  FIRE_EXPLOSION: Flame,
  SUPPLIER_INCIDENT: Factory,
  PHARMA_REGULATORY_QUALITY: Pill,
  PORT_CONGESTION: Ship,
};

/** Active disruptions touching Bangladesh (C2 fuses and ranks them from M4). */
export async function AlertFeed({ scenario }: { scenario: string }) {
  const { data, error } = await (await api()).GET("/api/v1/events", {
    params: { query: { scenario, country: "BGD", status: "ongoing", limit: 8 } },
  });
  if (error || !data) return <ErrorNote what="events" />;
  const events = data.data;
  return (
    <Card>
      <CardHeader title="Disruptions" subtitle="Ongoing events in Bangladesh, newest first" />
      {events.length === 0 ? (
        <p className="text-sm text-muted">No ongoing disruptions in this view.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border" data-testid="alert-feed">
          {events.map((e) => {
            const Icon = ICON[e.type] ?? TriangleAlert;
            return (
              <li key={e.id} className="flex gap-3 py-2.5">
                <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-warn" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium" title={e.title}>{e.title}</p>
                  <p className="text-xs text-muted">
                    {e.type.replaceAll("_", " ").toLowerCase()}
                    {e.alert_level ? ` · ${e.alert_level} alert` : ""}
                    {e.start_est ? ` · from ${dhakaTime(e.start_est)}` : ""}
                    {` · ${e.data_mode}`}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <CardFooter>
        <Provenance meta={data.meta} />
      </CardFooter>
    </Card>
  );
}
