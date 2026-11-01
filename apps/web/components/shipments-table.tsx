import { Provenance } from "@/components/data-badge";
import { ErrorNote } from "@/components/kpi-strip";
import { Badge } from "@/components/ui/badge";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api/server";
import { dhakaTime } from "@/lib/utils";

type Driver = { label?: string; hours?: number };

function onTimeTone(p: number): "ok" | "warn" | "danger" {
  return p >= 0.7 ? "ok" : p >= 0.4 ? "warn" : "danger";
}

/** Shipments in flight with the Nexus door ETA (08 §1, NX-AC02): P50 (P90), P(on time), top driver. */
export async function ShipmentsTable({ scenario }: { scenario: string }) {
  const { data, error } = await (await api()).GET("/api/v1/shipments", {
    params: { query: { scenario, limit: 12, active: true } },
  });
  if (error || !data) return <ErrorNote what="shipments" />;
  return (
    <Card>
      <CardHeader
        title="Shipments"
        subtitle="Door ETA: Monte Carlo over the remaining legs (C4 Chattogram stay, disruptions)"
      />
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="shipments">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="py-2 pr-3 font-medium">Reference</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 font-medium">Modes</th>
              <th className="py-2 pr-3 font-medium">Planned</th>
              <th className="py-2 pr-3 font-medium">Door ETA P50 (P90)</th>
              <th className="py-2 pr-3 font-medium">On time</th>
              <th className="py-2 pr-3 font-medium">Main driver</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.data.map((s) => {
              const eta = s.door_eta;
              const top = (eta?.drivers as Driver[] | undefined)?.find((d) => (d.hours ?? 0) > 0);
              return (
                <tr key={s.id} data-testid="shipment-row">
                  <td className="py-2 pr-3 font-mono text-xs">{s.reference}</td>
                  <td className="py-2 pr-3">
                    <Badge tone={s.status === "delayed" ? "danger" : s.status === "in_transit" ? "info" : "neutral"}>
                      {s.status.replace("_", " ")}
                    </Badge>
                  </td>
                  <td className="py-2 pr-3 text-xs text-muted">{s.mode_chain.join(" → ")}</td>
                  <td className="tabular py-2 pr-3 text-xs">{dhakaTime(s.planned_eta)}</td>
                  <td className="tabular py-2 pr-3 text-xs">
                    {eta ? (
                      <>
                        {dhakaTime(eta.p50)} <span className="text-muted">({dhakaTime(eta.p90)})</span>
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    {eta?.on_time_prob != null ? (
                      <Badge tone={onTimeTone(eta.on_time_prob)}>{Math.round(eta.on_time_prob * 100)} %</Badge>
                    ) : (
                      <span className="text-xs text-muted" title="No linked order due date">
                        —
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-xs text-muted">
                    {top ? `${top.label} +${((top.hours ?? 0) / 24).toFixed(1)} d` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <CardFooter>
        <Provenance meta={data.meta} />
      </CardFooter>
    </Card>
  );
}
