import { ErrorNote } from "@/components/kpi-strip";
import { Badge } from "@/components/ui/badge";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { fmt } from "@/lib/utils";

type Kpis = Record<string, number | string | null | string[]>;

/** Seeded scenarios and their port projection (with vs without the disruption). */
export async function ScenariosCard() {
  const client = await api();
  const { data, error } = await client.GET("/api/v1/scenarios");
  if (error || !data) return <ErrorNote what="scenarios" />;
  const results = await Promise.all(
    data.data.map((s) => client.GET("/api/v1/scenarios/{key}/results", { params: { path: { key: s.key } } })),
  );
  return (
    <Card>
      <CardHeader title="Scenarios" subtitle="Synthetic worlds; fictional firms at real infrastructure" />
      <ul className="flex flex-col divide-y divide-border">
        {data.data.map((s, i) => {
          const port = results[i].data?.data.find((r) => r.capability === "c4")?.kpis as
            | { scenario?: Kpis; without_disruption?: Kpis }
            | undefined;
          return (
            <li key={s.key} className="py-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{s.name}</span>
                {s.is_baseline ? <Badge tone="info">baseline</Badge> : null}
                <Badge tone="warn">synthetic</Badge>
              </div>
              {port?.scenario ? (
                <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
                  {(
                    [
                      ["Mean berth wait", "mean_wait_h", "h"],
                      ["P90 berth wait", "p90_wait_h", "h"],
                      ["Peak queue", "peak_waiting_for_berth", "vessels"],
                      ["Vessel-hours at port", "vessel_hours_at_port", "h"],
                    ] as const
                  ).map(([label, key, unit]) => {
                    const v = port.scenario?.[key];
                    const base = port.without_disruption?.[key];
                    return (
                      <div key={key}>
                        <dt className="text-muted">{label}, next 14 d</dt>
                        <dd className="tabular">
                          {fmt(typeof v === "number" ? v : null, 1)} {unit}
                          {typeof base === "number" && typeof v === "number" ? (
                            <span className="text-muted"> (without: {fmt(base, 1)})</span>
                          ) : null}
                        </dd>
                      </div>
                    );
                  })}
                </dl>
              ) : null}
            </li>
          );
        })}
      </ul>
      <CardFooter>Port projections come from the calibrated DES (docs/data-sources/CALIBRATION.md).</CardFooter>
    </Card>
  );
}
